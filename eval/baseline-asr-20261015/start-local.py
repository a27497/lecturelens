"""Run the unchanged online JAR in a separate local evaluation namespace."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pid", type=int, required=True)
    parser.add_argument("--jar", type=Path, required=True)
    args = parser.parse_args()
    private = ROOT / ".data/baseline-asr-20261015"
    private.mkdir(exist_ok=True)
    env = dict(
        item.split("=", 1)
        for item in Path(f"/proc/{args.source_pid}/environ").read_text().split("\0")
        if "=" in item
    )
    env.update(
        APP_PORT="8089",
        MYSQL_JDBC_URL="jdbc:mysql://127.0.0.1:13306/baseline_asr_20261015?useUnicode=true&characterEncoding=utf8&useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC",
        ROCKETMQ_PRODUCER_GROUP="baseline-asr-20261015-producer",
        ROCKETMQ_CONSUMER_GROUP="baseline-asr-20261015-consumer",
        ROCKETMQ_ANALYSIS_TOPIC="baseline-asr-20261015",
        AGENT_SERVICE_URL="http://127.0.0.1:18099",
        BAILIAN_ASR_ENDPOINT="https://127.0.0.1:18443/api/v1/services/aigc/multimodal-generation/generation",
    )
    args.jar = args.jar.resolve()
    service = subprocess.Popen(
        [
            "java",
            "-Djavax.net.ssl.trustStore=" + str(private / "truststore"),
            "-Djavax.net.ssl.trustStorePassword=changeit",
            "-Djava.io.tmpdir=" + str(private / "tmp"),
            "-jar",
            str(args.jar),
            "--spring.config.additional-location=file:/home/dev/projects/lecturelens-asr-b/.data/asr-b-deploy/asr-bailian.yml",
        ],
        cwd=private,
        env=env,
        stdout=(private / "backend.log").open("a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    (private / "process.json").write_text(
        json.dumps({"evaluation_pid": service.pid, "source_pid": args.source_pid})
        + "\n"
    )
    allowed = [
        "ASR_PROVIDER",
        "ASR_CHUNK_DURATION",
        "ASR_CHUNK_CONCURRENCY",
        "ASR_MAX_AUDIO_FILE_SIZE",
        "ASR_CHUNK_MAX_FILE_SIZE",
        "BAILIAN_ASR_MODEL",
        "OPENAI_COMPATIBLE_MODEL",
        "COURSELINGO_SUBTITLE_TRANSLATION_FULL_TEXT_ENABLED",
        "COURSELINGO_SUBTITLE_TRANSLATION_FULL_TEXT_BATCH_CONCURRENCY",
        "DENSE_RETRIEVAL_ENABLED",
        "COURSELINGO_VISION_KEYFRAME_ENABLED",
        "COURSELINGO_VISION_OCR_ENABLED",
        "COURSELINGO_VISION_ANALYSIS_ENABLED",
        "COURSELINGO_FUSION_VIDEO_SEGMENT_ENABLED",
    ]
    identity = {
        "jar_sha256": hashlib.file_digest(args.jar.open("rb"), "sha256").hexdigest(),
        "production_settings": {k: env[k] for k in allowed if k in env},
        "isolation_overrides": [
            "loopback port",
            "separate MySQL schema",
            "separate RocketMQ topic/groups",
            "separate temp/workspace",
            "transparent ASR/index meters and local TLS truststore",
        ],
        "source_process_unchanged": True,
    }
    (ROOT / "eval/baseline-asr-20261015/runtime-identity.json").write_text(
        json.dumps(identity, indent=2) + "\n"
    )
    print("Evaluation backend PID", service.pid)


if __name__ == "__main__":
    main()
