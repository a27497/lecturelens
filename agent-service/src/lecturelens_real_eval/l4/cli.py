"""L4 benchmark campaign commands. Private state lives under --root (mode 0700), never in Git.

freeze    --audit FILE [--audit FILE]   write FREEZE.json after the gold audits (citation check included)
snapshot                                 save each lecture's authoritative Evidence
run       --split S --rep N [--paths]    one repetition, serial, resumable, never replaces a record
packet    --split S --label L            build the blind judge packet and the separate mapping
judge     --split S --label L            judge every packet entry (<= 4 in flight, <= 2 retries)
score     --split S --label L            reveal, compute metrics, write summary.json
agreement --split S --label L            seeded 20% review packet for an independent reviewer
ledger                                   print spend totals
"""

import argparse
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from . import blind, judge, scoring
from .ledger import BudgetExceeded, Ledger
from .normalize import normalize
from .questions import load_frozen, write_freeze

ROOT = Path("/home/ubuntu/projects/lecturelens-private/l4")
SEED = 20261118
PATHS = ("rag", "tutor", "study")
RAG_MIN_INTERVAL = 7.0  # Java QA allows 10 requests per user per minute.
JUDGE_URL = "https://api.deepseek.com/chat/completions"
JUDGE_ATTEMPTS = 3
JUDGE_TIMEOUT = 600


def private_write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("x") as out:
        json.dump(value, out, ensure_ascii=False, indent=1, default=str)
        out.write("\n")
    path.chmod(0o600)


def ledger_for(root):
    plan = json.loads((root / "PLAN.json").read_bytes())
    return Ledger(
        root / "ledger.jsonl",
        hard_stop_usd=plan["budget"]["hard_stop_usd"],
        request_cap_usd=plan["budget"]["per_request_cap_usd"],
    )


def tasks(root):
    return json.loads((root / "ingest/tasks.json").read_text())


def evidence_map(root, lecture):
    data = json.loads((root / "evidence" / f"{lecture}.json").read_text())
    return {e["evidenceId"]: e.get("normalizedText") or e.get("rawText") or "" for e in data["items"]}, data


def cmd_snapshot(args):
    from .runner import Java

    java = Java(args.java, args.root / "ingest/session.local.json")
    for lecture, task in tasks(args.root).items():
        items = java.evidence(task["task_id"])
        revisions = {e["revision"] for e in items}
        if len(revisions) != 1:
            sys.exit(f"{lecture}: mixed revisions {revisions}")
        private_write(
            args.root / "evidence" / f"{lecture}.json",
            {
                "task_id": task["task_id"],
                "revision": revisions.pop(),
                "owner_id": items[0]["ownerId"],
                "items": items,
            },
        )
        print(lecture, len(items))


def schedule(items, rep):
    """Per lecture, a seeded item order; per item, a seeded rotation of the three paths."""
    rng = random.Random(f"{SEED}|rep{rep}")
    order = []
    for lecture in sorted({i["lecture_id"] for i in items}):
        group = [i for i in items if i["lecture_id"] == lecture]
        rng.shuffle(group)
        for item in group:
            start = rng.randrange(3)
            order += [(item, PATHS[(start + k) % 3]) for k in range(3)]
    return order


def cmd_run(args):
    from .runner import Java, run_rag, run_study, run_tutor, tutor_runtime

    items = load_frozen(args.root, args.split)
    if args.items:
        wanted = set(args.items.split(","))
        items = [i for i in items if i["item_id"] in wanted]
    paths = set(args.paths.split(","))
    ledger = ledger_for(args.root)
    java = Java(args.java, args.root / "ingest/session.local.json")
    out = args.root / "runs" / args.split / f"rep{args.rep}"
    phase = f"{args.split}-rep{args.rep}"
    runtime = None
    if "tutor" in paths:
        runtime = tutor_runtime(
            os.environ["AGENT_DATABASE_URL"],
            args.java,
            os.environ["AGENT_SERVICE_SECRET"],
            os.environ["TUTOR_FLASH_API_KEY"],
            ledger,
        )
    last_rag = 0.0
    try:
        for item, path in schedule(items, args.rep):
            if path not in paths:
                continue
            target = out / path / f"{item['item_id']}.json"
            if target.exists():
                continue
            ev = json.loads((args.root / "evidence" / f"{item['lecture_id']}.json").read_text())
            task = ev["task_id"]
            try:
                if path == "rag":
                    time.sleep(max(0.0, RAG_MIN_INTERVAL - (time.monotonic() - last_rag)))
                    record = run_rag(java, ledger, phase, item, args.rep, task)
                    last_rag = time.monotonic()
                elif path == "study":
                    record = run_study(
                        java, ledger, phase, item, args.rep, task, os.environ["AGENT_DATABASE_URL"]
                    )
                else:
                    scope = {"owner_id": ev["owner_id"], "course_id": task, "revision": ev["revision"]}
                    record = run_tutor(runtime, phase, item, args.rep, scope)
            except BudgetExceeded as error:
                print("STOP budget", error, flush=True)
                return 3
            private_write(target, record)
            print(
                phase,
                path,
                item["item_id"],
                record["status"],
                record.get("error_code"),
                record.get("abstained"),
                record.get("latency_ms"),
                flush=True,
            )
    finally:
        if runtime:
            runtime.close()
    print("ledger", json.dumps(ledger.summary()))
    return 0


def study_text(artifact):
    """Learner-visible explanation and reference answers of a Study artifact, in artifact order."""
    parts = []
    for key in ("explanation", "summary", "human_guidance", "reason"):
        if isinstance(artifact.get(key), str):
            parts.append(artifact[key])
    for question in artifact.get("questions") or []:
        for key in ("reference_answer", "answer", "explanation"):
            if isinstance(question.get(key), str):
                parts.append(question[key])
    return "\n\n".join(parts)


def reported_citations(record):
    """Evidence ids the product reports for one ok record (Tutor inline markers are added by normalize)."""
    if record["path"] == "study":
        return [c["evidence_id"] for c in (record["artifact"] or {}).get("citations") or []]
    return list(record["cited"])


def records(root, split, reps):
    """Run records of the given repetitions. Repetition 0 is the smoke run and is scored only on request."""
    for record_path in sorted((root / "runs" / split).glob("rep*/*/*.json")):
        record = json.loads(record_path.read_text())
        if record["rep"] in reps:
            yield record


def responses(root, split, label, reps):
    out = []
    for record in records(root, split, reps):
        if record["status"] != "ok":
            continue
        evidence, _ = evidence_map(root, record["lecture_id"])
        cited = reported_citations(record)
        if record["path"] == "study":
            norm = normalize(study_text(record["artifact"] or {}), cited, evidence)
        else:
            norm = normalize(record["text"], cited, evidence, inline=record["path"] == "tutor")
        out.append(
            {
                "path": record["path"],
                "rep": record["rep"],
                "item_id": record["item_id"],
                "abstained": record["abstained"],
                **norm,
            }
        )
    return out


def cmd_packet(args):
    items = load_frozen(args.root, args.split)
    packet, mapping = blind.build(responses(args.root, args.split, args.label, args.reps), items, seed=SEED)
    base = args.root / "judge" / args.split / args.label
    private_write(base / "packet.json", packet)
    private_write(base / "judge-only-mapping.json", mapping)
    print(len(packet["entries"]), mapping["packet_sha256"])


def judge_one(entry, ledger, phase, key, raw_dir):
    body = judge.request_body(entry)
    reason = "NO_ATTEMPT"
    for attempt in range(1, JUDGE_ATTEMPTS + 1):
        reservation = ledger.reserve(
            phase=phase,
            arm="judge",
            unit=f"{entry['response_id']}#{attempt}",
            model=judge.MODEL,
            upper_nano=judge.reservation_nano(body),
        )
        sent = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        try:
            response = httpx.post(
                JUDGE_URL, json=body, timeout=JUDGE_TIMEOUT, headers={"Authorization": "Bearer " + key}
            )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            ledger.uncertain(reservation, type(error).__name__)
            reason = "TRANSPORT"
            continue
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if usage:
            ledger.settle(reservation, [{"model": judge.MODEL, "at": sent, "usage": usage}])
        else:
            ledger.uncertain(reservation, f"HTTP_{response.status_code}")
        (raw_dir / f"{entry['response_id']}.{attempt}.json").write_text(
            json.dumps(payload, ensure_ascii=False)
        )
        if response.status_code in (401, 402, 403):
            raise RuntimeError(f"JUDGE_PROVIDER_REFUSED_{response.status_code}")
        try:
            choice = payload["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError(f"finish_reason {choice.get('finish_reason')}")
            return {**judge.validate(entry, choice["message"]["content"]), "attempts": attempt}
        except (KeyError, IndexError, TypeError, ValueError) as error:
            reason = f"INVALID: {str(error)[:120]}"
    return {**judge.undetermined(entry, reason), "attempts": JUDGE_ATTEMPTS}


def cmd_judge(args):
    base = args.root / "judge" / args.split / args.label
    packet = json.loads((base / "packet.json").read_text())
    decisions_path = base / "decisions.json"
    decisions = json.loads(decisions_path.read_text()) if decisions_path.exists() else {}
    raw_dir = base / "raw"
    raw_dir.mkdir(mode=0o700, exist_ok=True)
    ledger = ledger_for(args.root)
    key = os.environ["L4_JUDGE_API_KEY"]
    todo = [e for e in packet["entries"] if e["response_id"] not in decisions]
    lock = threading.Lock()

    def work(entry):
        decision = judge_one(entry, ledger, f"judge-{args.split}-{args.label}", key, raw_dir)
        with lock:
            decisions[entry["response_id"]] = decision
            tmp = decisions_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(decisions, ensure_ascii=False))
            tmp.chmod(0o600)
            tmp.replace(decisions_path)
        print(entry["response_id"], decision["verdict"], decision.get("attempts"), flush=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(work, todo))
    print("ledger", json.dumps(ledger.summary()))


def rows(root, split, label, reps):
    base = root / "judge" / split / label
    packet = json.loads((base / "packet.json").read_text())
    mapping = json.loads((base / "judge-only-mapping.json").read_text())
    decisions = json.loads((base / "decisions.json").read_text())
    joined = {
        (r["path"], r["rep"], r["item_id"]): r["decision"] for r in blind.reveal(packet, mapping, decisions)
    }
    items = {i["item_id"]: i for i in load_frozen(root, split)}
    spans = {}
    out = []
    for record in records(root, split, reps):
        item = items[record["item_id"]]
        decision = joined.get((record["path"], record["rep"], record["item_id"]), {})
        hit = None
        if record["status"] == "ok" and item["answerable"]:
            if item["lecture_id"] not in spans:
                _, snapshot = evidence_map(root, item["lecture_id"])
                spans[item["lecture_id"]] = {e["evidenceId"]: e for e in snapshot["items"]}
            ids = reported_citations(record)
            if record["path"] == "tutor":
                ids += re.findall(r"\[([^\[\]\s]+)\]", record.get("text") or "")
            hit = scoring.gold_evidence_hit(item, ids, spans[item["lecture_id"]])
        out.append(
            {
                "path": record["path"],
                "rep": record["rep"],
                "item_id": item["item_id"],
                "lecture_id": item["lecture_id"],
                "language": item["language"],
                "category": item["category"],
                "answerable": item["answerable"],
                "status": record["status"],
                "error_code": record.get("error_code"),
                "abstained": bool(record.get("abstained")),
                "verdict": decision.get("verdict"),
                "vital_lenient": decision.get("vital_lenient", 0.0),
                "vital_supported": decision.get("vital_supported", 0),
                "vital_total": decision.get("vital_total", 0),
                "all_lenient": decision.get("all_lenient", 0.0),
                "material_error": decision.get("material_error"),
                "claims_supported": decision.get("claims_supported", 0),
                "claims_total": decision.get("claims_total", 0),
                "citation_pairs_precise": decision.get("citation_pairs_precise", 0),
                "citation_pairs_total": decision.get("citation_pairs_total", 0),
                "citations_relevant": decision.get("citations_relevant", 0),
                "citations_distinct": decision.get("citations_distinct", 0),
                "gold_evidence_hit": hit,
                "abstention_leak": decision.get("abstention_leak"),
                "cost_nano": record.get("cost_nano"),
                "latency_ms": record.get("latency_ms"),
            }
        )
    return out


def cmd_score(args):
    data = rows(args.root, args.split, args.label, args.reps)
    summary = {
        "split": args.split,
        "label": args.label,
        "rows": len(data),
        "metrics": scoring.summarize(data),
        "repetition_range": {m: scoring.repetition_range(data, m) for m in scoring.METRICS},
        "mcnemar_rep1": scoring.mcnemar_pairs(data),
        "latency_cost": scoring.latency_cost(data),
    }
    base = args.root / "judge" / args.split / args.label
    private_write(base / f"rows-{time.strftime('%Y%m%dT%H%M%S')}.json", data)
    private_write(base / f"summary-{time.strftime('%Y%m%dT%H%M%S')}.json", summary)
    for metric, value in summary["metrics"]["metrics"].items():
        print(metric, {p: v["estimate"] for p, v in value["paths"].items()})


def cmd_agreement(args):
    base = args.root / "judge" / args.split / args.label
    packet = json.loads((base / "packet.json").read_text())
    mapping = json.loads((base / "judge-only-mapping.json").read_text())
    decisions = json.loads((base / "decisions.json").read_text())
    review, key = blind.agreement_sample(packet, mapping, decisions, seed=SEED)
    target = args.root / "runs" / args.split / "agreement"
    private_write(target / "review-packet.json", review)
    private_write(base / "agreement" / "judge-only-key.json", key)
    print(len(review["entries"]), key["packet_sha256"])


def cmd_freeze(args):
    print(write_freeze(args.root, audit_paths=args.audit, note=args.note))


def cmd_ledger(args):
    print(json.dumps(ledger_for(args.root).summary()))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--java", default="http://127.0.0.1:38080")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot")
    sub.add_parser("ledger")
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--audit", type=Path, action="append", required=True)
    freeze.add_argument("--note", default="")
    run = sub.add_parser("run")
    run.add_argument("--split", choices=["dev", "holdout"], required=True)
    run.add_argument("--rep", type=int, required=True)
    run.add_argument("--paths", default=",".join(PATHS))
    run.add_argument("--items")
    for name in ("packet", "judge", "score", "agreement"):
        p = sub.add_parser(name)
        p.add_argument("--split", choices=["dev", "holdout"], required=True)
        p.add_argument("--label", required=True)
        p.add_argument("--reps", type=lambda v: {int(r) for r in v.split(",")}, default={1, 2, 3})
    args = parser.parse_args(argv)
    return {
        "snapshot": cmd_snapshot,
        "ledger": cmd_ledger,
        "freeze": cmd_freeze,
        "run": cmd_run,
        "packet": cmd_packet,
        "judge": cmd_judge,
        "score": cmd_score,
        "agreement": cmd_agreement,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
