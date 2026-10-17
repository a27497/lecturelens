"""Start an isolated local copy of a frozen production artifact with response tee."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parent
EXPECTED_JAR = "a6148f8aad454f506f644102c793690871dce5d2f34036c1a30f5b5d56dd6a08"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pid", type=int, required=True)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--asr-config", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if hashlib.file_digest(args.jar.open("rb"), "sha256").hexdigest() != EXPECTED_JAR:
        raise ValueError("Artifact differs from frozen production JAR")
    private = ROOT / ".data/baseline-asr-20261015"
    env = dict(
        item.split("=", 1)
        for item in Path(f"/proc/{args.source_pid}/environ").read_text().split("\0")
        if "=" in item
    )
    expected = json.loads((REPORT / "runtime-identity.json").read_text())[
        "production_settings"
    ]
    if any(env.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "Current source process configuration differs from the frozen baseline"
        )
    if args.check_only:
        print(
            json.dumps(
                {
                    "jar_sha256": EXPECTED_JAR,
                    "source_process_readable": True,
                    "credentials_printed": False,
                    "models_called": 0,
                }
            )
        )
        return
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 8089)) == 0:
            raise ValueError(
                "Evaluation port 8089 occupied; never stop another process automatically"
            )
    unpacked, extra = private / "unpacked", private / "observer-classes"
    unpacked.mkdir(exist_ok=True)
    extra.mkdir(exist_ok=True)
    with zipfile.ZipFile(args.jar) as archive:
        for name in archive.namelist():
            if name.startswith(
                ("BOOT-INF/classes/", "BOOT-INF/lib/")
            ) and not name.endswith("/"):
                destination = unpacked / name
                if not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.read(name))
                if destination.read_bytes() != archive.read(name):
                    raise ValueError("Extracted production class/library changed")
    classpath = os.pathsep.join(
        map(str, (extra, unpacked / "BOOT-INF/classes", unpacked / "BOOT-INF/lib/*"))
    )
    subprocess.run(
        [
            "javac",
            "-cp",
            classpath,
            "-d",
            str(extra),
            str(REPORT / "BaselineBootstrap.java"),
        ],
        check=True,
    )
    args.batch.mkdir(parents=True, exist_ok=True)
    env.update(
        APP_PORT="8089",
        MYSQL_JDBC_URL="jdbc:mysql://127.0.0.1:13306/baseline_asr_20261015?useUnicode=true&characterEncoding=utf8&useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC",
        ROCKETMQ_PRODUCER_GROUP="baseline-asr-20261015-producer",
        ROCKETMQ_CONSUMER_GROUP="baseline-asr-20261015-consumer",
        ROCKETMQ_ANALYSIS_TOPIC="baseline-asr-20261015",
        AGENT_SERVICE_URL="http://127.0.0.1:18099",
        ASR_BASELINE_PRIVATE=str(private),
        ASR_BASELINE_CALLS=str(args.batch.resolve() / "http-calls.jsonl"),
    )
    process = subprocess.Popen(
        [
            "java",
            "-Djava.io.tmpdir=" + str(private / "tmp"),
            "-cp",
            classpath,
            "baseline.measurement.BaselineBootstrap",
            "--spring.config.additional-location=file:"
            + str(args.asr_config.resolve()),
        ],
        cwd=private,
        env=env,
        stdout=(private / "backend-reproduction.log").open("a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    (private / "reproduction-process.json").write_text(
        json.dumps({"evaluation_pid": process.pid, "source_pid": args.source_pid})
        + "\n"
    )
    print("Local evaluation backend PID", process.pid)


if __name__ == "__main__":
    main()
