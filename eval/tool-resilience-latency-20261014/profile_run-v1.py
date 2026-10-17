"""Instrument actual healthy Runs; timings are inclusive, never added twice."""
import cProfile
import functools
import importlib.util
import json
import pstats
import threading
import time
from contextvars import ContextVar
from pathlib import Path

from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyStore

ROOT = Path(__file__).resolve().parent
active = None
operation = ContextVar("profile_store_operation", default="other")
lock = threading.Lock()


def observe(kind, name, elapsed):
    if active is not None:
        with lock:
            record = active.setdefault(kind, {}).setdefault(name, {"calls": 0, "ms": 0.0})
            record["calls"] += 1
            record["ms"] += elapsed * 1000


class ObservedConnection:
    def __init__(self, delegate):
        self.delegate = delegate

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def __enter__(self):
        self.delegate.__enter__()
        return self

    def __exit__(self, *args):
        return self.delegate.__exit__(*args)

    def execute(self, query, *args, **kwargs):
        started = time.perf_counter()
        try:
            return self.delegate.execute(query, *args, **kwargs)
        finally:
            text = str(query)
            category = "retry_event_scan" if "operation_key" in text else "active_run" if "FOR UPDATE" in text else "event_insert" if "INSERT INTO study_event" in text else "other"
            observe("sql", category, time.perf_counter() - started)


def wrap_method(name):
    original = getattr(StudyStore, name)

    @functools.wraps(original)
    def call(self, *args, **kwargs):
        label = name + (":" + args[2] if name == "event" else "")
        context = operation.set(label)
        started = time.perf_counter()
        try:
            return original(self, *args, **kwargs)
        finally:
            observe("methods", label, time.perf_counter() - started)
            operation.reset(context)

    setattr(StudyStore, name, call)


for method in ("guard", "reserve", "event", "reserve_read_attempt", "save_tool", "tool_result", "claim", "finish"):
    if hasattr(StudyStore, method):
        wrap_method(method)

original_connect = StudyStore.connect


def connect(self, **kwargs):
    started = time.perf_counter()
    try:
        connection = original_connect(self, **kwargs)
        return ObservedConnection(connection)
    finally:
        observe("connections", operation.get(), time.perf_counter() - started)


StudyStore.connect = connect
original_execute = StudyRuntime.execute
sequence = 0


def execute(self, run):
    global active, sequence
    profiler = cProfile.Profile()
    active = {}
    started = time.perf_counter()
    try:
        profiler.enable()
        return original_execute(self, run)
    finally:
        profiler.disable()
        elapsed = (time.perf_counter() - started) * 1000
        details, active = active, None
        label = self.provider.scenario
        output = ROOT / f"profile-{LABEL}-{sequence}.pstats"
        profiler.dump_stats(output)
        stats = pstats.Stats(profiler)
        top = [{"file": key[0], "line": key[1], "function": key[2], "primitive_calls": value[0],
                "calls": value[1], "self_ms": value[2] * 1000, "cumulative_ms": value[3] * 1000}
               for key, value in sorted(stats.stats.items(), key=lambda pair: pair[1][3], reverse=True)[:45]]
        record = {"label": LABEL, "trial": sequence, "scenario": label, "run_id": run["run_id"],
                  "elapsed_ms": elapsed, "inclusive_timings_not_additive": True,
                  **details, "cprofile_top": top, "pstats": output.name}
        with (ROOT / f"profile-{LABEL}.jsonl").open("a") as out:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
        sequence += 1


StudyRuntime.execute = execute
spec = importlib.util.spec_from_file_location("fault_run", ROOT / "run.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
import sys
LABEL = sys.argv[sys.argv.index("--label") + 1]
if (ROOT / f"profile-{LABEL}.jsonl").exists():
    raise SystemExit("Never overwrite profiling records")
module.main()
