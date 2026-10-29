"""Emergency Compose cleanup after SIGKILL; ordinary runs clean up automatically."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def cleanup(directory):
    result = json.loads((directory / "result.json").read_text())
    projects = result["projects"]
    if (
        len(projects) != 2
        or not all(
            re.fullmatch(r"lecturelens-perf-p0-[0-9a-f]{12}-(infra|pg)", p)
            for p in projects
        )
        or projects[0].rsplit("-", 1)[0] != projects[1].rsplit("-", 1)[0]
    ):
        raise ValueError("Refuse projects outside this harness namespace")
    # Down needs interpolation, not the original password or an authenticated database connection.
    env = {k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ}
    env["SMOKE_POSTGRES_PASSWORD"] = "unused-cleanup-only"
    for project in projects:
        if project.endswith("-pg"):
            files = ["-f", str(HERE / "compose.yaml")]
        else:
            files = ["-f", str(ROOT / "compose.yaml")]
            if result["config"]["minio_source_build"]:
                files += ["-f", str(ROOT / "compose.ci-minio.yml")]
            files += ["-f", str(directory / "loopback.compose.yaml")]
        subprocess.run(
            [
                "docker",
                "compose",
                *files,
                "-p",
                project,
                "--env-file",
                str(directory / "public.env"),
                "down",
                "-v",
                "--remove-orphans",
                "--timeout",
                "5",
            ],
            env=env,
            check=True,
            timeout=120,
        )
        for kind in ("container", "volume", "network"):
            found = subprocess.check_output(
                [
                    "docker",
                    kind,
                    "ls",
                    "-q",
                    "--filter",
                    f"label=com.docker.compose.project={project}",
                ],
                env=env,
                text=True,
            )
            if found.strip():
                raise RuntimeError("Owned resources remain")
    print(
        "Owned Compose resources removed; this does not terminate Java/Agent processes"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    cleanup(parser.parse_args().directory.resolve())
