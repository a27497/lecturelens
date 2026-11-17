"""Append-only spending ledger for the L4 benchmark.

Every paid unit (one product request, one Study Run, one judge call, one ingestion batch) reserves
its peak-price upper bound before dispatch, under an exclusive file lock, and later settles from
provider usage. A unit whose outcome is unknown stays charged at its upper bound (UNCERTAIN). An
unresolved reservation keeps counting against the cap, so a crash can never free budget.
"""

import fcntl
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .pricing import NANO, PRICE_ID, cost_nano

TERMINAL = {"settle", "uncertain", "release"}


class LedgerError(RuntimeError):
    pass


class BudgetExceeded(LedgerError):
    pass


def now():
    return datetime.now(timezone.utc)


class Ledger:
    def __init__(self, path, *, hard_stop_usd, request_cap_usd):
        self.path = Path(path)
        self.hard_stop = round(hard_stop_usd * NANO)
        self.request_cap = round(request_cap_usd * NANO)

    @contextmanager
    def locked(self):
        flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
        fd = os.open(self.path, flags, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield fd
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def events(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    @staticmethod
    def state(events):
        units = {}
        for event in events:
            if event["event"] == "reserve":
                if event["id"] in units:
                    raise LedgerError("duplicate reservation")
                units[event["id"]] = {**event, "status": "reserved", "cost_nano": None}
            else:
                unit = units.get(event["id"])
                if unit is None or unit["status"] != "reserved" or event["event"] not in TERMINAL:
                    raise LedgerError(f"invalid ledger transition for {event['id']}")
                unit["status"] = {"settle": "settled", "uncertain": "uncertain", "release": "released"}[
                    event["event"]
                ]
                unit["cost_nano"] = (
                    event["cost_nano"]
                    if event["event"] == "settle"
                    else unit["upper_nano"]
                    if event["event"] == "uncertain"
                    else 0
                )
                unit["calls"] = event.get("calls", [])
        return units

    @staticmethod
    def totals(units):
        settled = sum(u["cost_nano"] for u in units.values() if u["status"] == "settled")
        uncertain = sum(u["cost_nano"] for u in units.values() if u["status"] == "uncertain")
        outstanding = sum(u["upper_nano"] for u in units.values() if u["status"] == "reserved")
        return {
            "settled_nano": settled,
            "uncertain_nano": uncertain,
            "outstanding_nano": outstanding,
            "committed_nano": settled + uncertain + outstanding,
        }

    def summary(self):
        return self.totals(self.state(self.events()))

    def _append(self, fd, event):
        os.write(fd, (json.dumps(event, sort_keys=True) + "\n").encode())
        os.fsync(fd)

    def reserve(self, *, phase, arm, unit, model, upper_nano):
        if type(upper_nano) is not int or upper_nano <= 0:
            raise LedgerError("reservation must be a positive integer")
        if upper_nano > self.request_cap:
            raise BudgetExceeded("PER_REQUEST_CAP")
        with self.locked() as fd:
            totals = self.totals(self.state(self.events()))
            if totals["committed_nano"] + upper_nano > self.hard_stop:
                raise BudgetExceeded("HARD_STOP")
            event = {
                "event": "reserve",
                "id": uuid.uuid4().hex,
                "at": now().isoformat(),
                "phase": phase,
                "arm": arm,
                "unit": unit,
                "model": model,
                "upper_nano": upper_nano,
                "price_id": PRICE_ID,
            }
            self._append(fd, event)
            return event["id"]

    def settle(self, reservation, calls):
        """calls: [{"model", "usage", "at" (ISO time)}]. Any unpriceable call makes the unit UNCERTAIN."""
        priced, total = [], 0
        for call in calls:
            cost = cost_nano(call["model"], call.get("usage"), datetime.fromisoformat(call["at"]))
            if cost is None:
                return self.uncertain(reservation, "USAGE_MISSING", calls)
            priced.append({**call, "cost_nano": cost})
            total += cost
        with self.locked() as fd:
            unit = self.state(self.events()).get(reservation)
            if unit is None or unit["status"] != "reserved":
                raise LedgerError("settle without an open reservation")
            if total > unit["upper_nano"]:
                # The bound was wrong; keep the real figure and flag it rather than hiding it.
                priced.append({"note": "COST_ABOVE_RESERVATION"})
            self._append(
                fd,
                {
                    "event": "settle",
                    "id": reservation,
                    "at": now().isoformat(),
                    "cost_nano": total,
                    "calls": priced,
                },
            )
        return total

    def uncertain(self, reservation, reason, calls=()):
        with self.locked() as fd:
            unit = self.state(self.events()).get(reservation)
            if unit is None or unit["status"] != "reserved":
                raise LedgerError("uncertain without an open reservation")
            self._append(
                fd,
                {
                    "event": "uncertain",
                    "id": reservation,
                    "at": now().isoformat(),
                    "reason": reason,
                    "calls": list(calls),
                },
            )
        return unit["upper_nano"]

    def release(self, reservation, reason):
        """Only for a unit known not to have reached the provider (e.g. product skipped the call)."""
        with self.locked() as fd:
            unit = self.state(self.events()).get(reservation)
            if unit is None or unit["status"] != "reserved":
                raise LedgerError("release without an open reservation")
            self._append(
                fd, {"event": "release", "id": reservation, "at": now().isoformat(), "reason": reason}
            )
