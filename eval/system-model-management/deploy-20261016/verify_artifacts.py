"""Verify deployment files and private backups without printing credentials."""

import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

PUBLIC = Path(__file__).resolve().parent
ROOT = PUBLIC.parents[2]
PRIVATE = ROOT / ".data/system-model-management/deploy-20261016"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    for line in (PUBLIC / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert digest(ROOT / name) == expected, name
    for record in json.loads((PUBLIC / "artifacts.json").read_text()):
        path = ROOT / record["path"]
        assert digest(path) == record["sha256"], record["path"]
        assert path.stat().st_size == record["bytes"], record["path"]
    for line in (PRIVATE / "BACKUP_SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert digest(PRIVATE / name) == expected, name
    with gzip.open(PRIVATE / "mysql-before.sql.gz", "rb") as stream:
        while stream.read(1024 * 1024):
            pass
    with (
        zipfile.ZipFile(PRIVATE / "backend-before.jar") as before,
        zipfile.ZipFile(PRIVATE / "backend.jar") as after,
    ):
        changes = []
        old_names, new_names = set(before.namelist()), set(after.namelist())
        for name in sorted(old_names | new_names):
            if not name.startswith("BOOT-INF/classes/"):
                continue
            old = hashlib.sha256(before.read(name)).hexdigest() if name in old_names else None
            new = hashlib.sha256(after.read(name)).hexdigest() if name in new_names else None
            if old != new:
                changes.append({"path": name, "before_sha256": old, "after_sha256": new})
        assert changes == json.loads((PUBLIC / "jar-differences.json").read_text())
    pid = subprocess.check_output(
        ["systemctl", "show", "lecturelens-live-backend", "-p", "MainPID", "--value"], text=True
    ).strip()
    environment = dict(
        value.split(b"=", 1)
        for value in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        if b"=" in value
    )
    keys = [value for name, value in environment.items() if name.endswith(b"API_KEY") and len(value) >= 8]
    for directory in (PUBLIC, PRIVATE):
        for path in directory.rglob("*"):
            if path.is_file():
                assert not any(key in path.read_bytes() for key in keys), "Credential in artifact; details withheld"
    assert not (PRIVATE / "before-environment.private.json").exists()
    assert not (PRIVATE / "runtime.private.json").exists()
    print(json.dumps({"artifacts": "verified", "backup_gzip": "verified", "jar_differences": len(changes), "plaintext_api_key_matches": 0}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Artifact verification failed: " + type(error).__name__ + "; details withheld")
        raise SystemExit(1)
