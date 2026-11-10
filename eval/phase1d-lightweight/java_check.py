"""Bounded JVM memory for the unchanged gateway/authority regression subset."""

import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[2]
env = {
    k: os.environ[k]
    for k in ("PATH", "HOME", "USER", "LANG", "JAVA_HOME")
    if k in os.environ
}
env["MAVEN_OPTS"] = "-Xmx512m -XX:ActiveProcessorCount=2"
raise SystemExit(
    subprocess.run(
        [
            "bash",
            "mvnw",
            "-o",
            "-B",
            "-Dtest=TutorControllerTest,TutorTransportTest,StudyAuthorityTest",
            "-DargLine=-Xmx256m -XX:ActiveProcessorCount=2",
            "test",
        ],
        check=False,
        cwd=root / "backend",
        env=env,
    ).returncode
)
