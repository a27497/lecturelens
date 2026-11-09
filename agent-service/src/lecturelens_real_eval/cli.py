"""LectureLens experiment entry point. Experiment adapters own their domain gates."""

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

EXPERIMENTS = {"e3": "lecturelens_real_eval.experiments.e3"}
RUN_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,23}")
MAX_REVIEW_BYTES = 256 * 1024


class CLIError(Exception):
    exit_code = 2


def json_file(path):
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None


def write_json_once(path, value):
    # Publish complete records to a polling worker and never replace a prior decision.
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", delete=False) as stream:
        scratch = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.link(scratch, path)
        except FileExistsError:
            raise CLIError("RECORD_ALREADY_EXISTS") from None
        finally:
            scratch.unlink(missing_ok=True)


def workspace(path):
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=path, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise CLIError("LECTURELENS_WORKSPACE_REQUIRED")
    root = Path(result.stdout.strip())
    if not (root / "scripts/dev/run_check.py").is_file():
        raise CLIError("LECTURELENS_WORKSPACE_REQUIRED")
    return root


def run_id(value):
    if not RUN_ID.fullmatch(value):
        raise argparse.ArgumentTypeError("use 1–24 lowercase letters, digits or hyphens")
    return value


def run_dir(root, args, *, create=False):
    base = root / ".data/ll-eval" / args.experiment
    if create:
        directory = base / (args.run_id or uuid.uuid4().hex[:12])
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            raise CLIError("RUN_ID_ALREADY_EXISTS") from None
        return directory
    if args.run_id:
        directory = base / args.run_id
        if (directory / "manifest.json").is_file():
            return directory
    elif base.is_dir():
        manifests = list(base.glob("*/manifest.json"))
        if manifests:
            return max(manifests, key=lambda path: path.stat().st_mtime_ns).parent
    raise CLIError("NO_RUN_RECORD")


def process_identity(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def summary(directory, *, detailed=False):
    manifest = json_file(directory / "manifest.json") or {}
    process = json_file(directory / "supervisor" / "run.json") or json_file(directory / "terminal.json") or {}
    if not process and manifest.get("mode") == "live":
        ticks = manifest.get("runner_start_ticks")
        running = ticks is not None and process_identity(manifest.get("runner_pid")) == ticks
        process = {"status": "RUNNING" if running else "INTERRUPTED_NO_TERMINAL_RECORD"}
    outcome = json_file(directory / "evidence" / "result.json") or {}
    evidence = directory / "evidence"
    packets = sorted((evidence / "review-packets").glob("*.json"))
    report = {
        **manifest,
        "status": process.get("status", "STARTING_OR_INTERRUPTED"),
        "exit_code": process.get("exit_code") if process.get("finished_at_utc") else None,
        "outcome": outcome.get("status"),
        "reviews": [
            {
                "case": packet.stem,
                "packet": str(packet),
                "received": (evidence / "review-decisions" / packet.name).exists(),
            }
            for packet in packets
        ],
        "evidence": str(evidence),
    }
    if detailed:
        report.update(
            retrieval=outcome.get("retrieval_preflight"),
            positions=outcome.get("positions"),
            phase_usage=outcome.get("phase_usage"),
            generation_requests=outcome.get("generation_requests"),
            review_requests=outcome.get("review_requests"),
            offline_mock_requests=outcome.get("offline_mock_requests"),
            stages={name: row["status"] for name, row in outcome.get("stages", {}).items()},
            cleanup=process.get("cleanup", {}).get("complete"),
            result_path=str(evidence / "result.json"),
        )
    return report


def add_review(directory, adapter, args):
    evidence = directory / "evidence"
    packet = json_file(evidence / "review-packets" / f"{args.case}.json")
    if not isinstance(packet, dict) or packet.get("case_id") != args.case:
        raise CLIError("REVIEW_PACKET_NOT_FOUND")
    try:
        with args.decision.open("rb") as stream:
            raw = stream.read(MAX_REVIEW_BYTES + 1)
        if len(raw) > MAX_REVIEW_BYTES:
            raise CLIError("REVIEW_FILE_TOO_LARGE")
        reviews = json.loads(raw)
    except (OSError, ValueError):
        raise CLIError("REVIEW_FILE_INVALID") from None
    adapter.validate_reviews(packet, reviews)
    target = evidence / "review-decisions" / f"{args.case}.json"
    target.parent.mkdir(mode=0o700, exist_ok=True)
    write_json_once(target, reviews)
    print(target)


def launch(root, adapter, args):
    # Live admission occurs before allocating a run or accessing the provider credential.
    if args.dev_ssh and not (args.live and args.batch):
        raise CLIError("E3_DEV_SSH_REQUIRES_LIVE_BATCH")
    context = adapter.live_admission(root, args) if args.live else None
    source = root / "scripts/dev/run_check.py"
    supervisor = args.check_supervisor or source
    if args.check_supervisor and (args.live or supervisor.read_bytes() != source.read_bytes()):
        raise CLIError("CHECK_SUPERVISOR_MUST_MATCH_WORKSPACE")
    options = adapter.options(root, args)
    directory = run_dir(root, args, create=True)
    write_json_once(
        directory / "manifest.json",
        {
            "run_id": directory.name,
            "experiment": args.experiment,
            "operation": args.action,
            "mode": "live" if args.live else "offline",
            "operator_mode": "dev-ssh" if args.dev_ssh else "systemd" if args.live else "offline",
            "collection": "batch" if args.batch else "sequential",
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "runner_pid": os.getpid() if args.live else None,
            "runner_start_ticks": process_identity(os.getpid()) if args.live else None,
            "commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        },
    )
    print(f"LL_RUN_ID={directory.name} EVIDENCE={directory / 'evidence'}", flush=True)
    if args.live:
        code = 125
        try:
            code = adapter.execute(root, directory, args.action, options, context)
            return code
        except KeyboardInterrupt:
            code = 130
            return code
        finally:
            write_json_once(
                directory / "terminal.json",
                {
                    "status": "CANCELLED" if code == 130 else "SUCCEEDED" if code == 0 else "FAILED",
                    "exit_code": code,
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                },
            )
    write_json_once(directory / "options.json", options)
    os.execv(
        sys.executable,
        [
            sys.executable,
            str(supervisor.resolve()),
            "--name",
            "supervisor",
            "--cwd",
            str(root),
            "--output-root",
            str(directory),
            "--timeout",
            str(adapter.OFFLINE_TIMEOUT),
            "--",
            sys.executable,
            "-c",
            "from lecturelens_real_eval.cli import main; raise SystemExit(main())",
            "_offline",
            str(root),
            args.experiment,
            str(directory),
        ],
    )


def offline_worker(argv):
    root, experiment, directory = argv
    root, directory = Path(root), Path(directory)
    manifest = json_file(directory / "manifest.json")
    options = json_file(directory / "options.json")
    if not manifest or manifest["mode"] != "offline" or options is None:
        raise CLIError("OFFLINE_MANIFEST_REQUIRED")
    return importlib.import_module(EXPERIMENTS[experiment]).execute(
        root, directory, manifest["operation"], options, None
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["_offline"]:
            return offline_worker(argv[1:])
        parser = argparse.ArgumentParser(prog="ll", description=__doc__)
        parser.add_argument("--workspace", type=Path, default=Path.cwd())
        area = parser.add_subparsers(dest="area", required=True)
        commands = area.add_parser("eval").add_subparsers(dest="action", required=True)
        for name in ("preflight", "run", "status", "report", "review"):
            command = commands.add_parser(name)
            command.add_argument("experiment", choices=EXPERIMENTS)
            command.add_argument("--run-id", type=run_id)
            if name in {"preflight", "run"}:
                command.set_defaults(live=False, dev_ssh=False, batch=False, confirmed_price_id=None)
                command.add_argument("--check-supervisor", type=Path)
                command.add_argument("--assets", type=Path, help="experiment input paths in JSON")
                command.add_argument("--review-wait", type=int, default=600, metavar="0..1200")
                if name == "run":
                    command.add_argument("--live", action="store_true")
                    command.add_argument("--dev-ssh", action="store_true")
                    command.add_argument("--batch", action="store_true")
                    command.add_argument("--confirmed-price-id")
            if name == "review":
                command.add_argument("--case", required=True, type=run_id)
                command.add_argument("--decision", required=True, type=Path)
        args = parser.parse_args(argv)
        root = workspace(args.workspace)
        adapter = importlib.import_module(EXPERIMENTS[args.experiment])
        if args.action in {"preflight", "run"}:
            return launch(root, adapter, args)
        directory = run_dir(root, args)
        if args.action == "review":
            add_review(directory, adapter, args)
        else:
            print(
                json.dumps(summary(directory, detailed=args.action == "report"), ensure_ascii=False, indent=2)
            )
        return 0
    except (CLIError, OSError, subprocess.CalledProcessError) as error:
        print(f"ll: {error if isinstance(error, CLIError) else type(error).__name__}", file=sys.stderr)
        return error.exit_code if isinstance(error, CLIError) else 2


if __name__ == "__main__":
    raise SystemExit(main())
