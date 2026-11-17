"""Content identity for Java artifacts reused between fresh isolated stacks."""

import hashlib
import json
from pathlib import Path


def fingerprint(directory):
    directory = Path(directory)
    files = {}
    for name in ("java-build.jar", "java-app", "java-addon"):
        path = directory / name
        if not path.exists() or path.is_symlink():
            raise RuntimeError(f"Missing or linked Java build artifact: {name}")
        entries = [path] if path.is_file() else sorted(path.rglob("*"))
        found = False
        for entry in entries:
            if entry.is_symlink():
                raise RuntimeError("Linked Java build artifacts are not reusable")
            if entry.is_file():
                found = True
                with entry.open("rb") as stream:
                    files[str(entry.relative_to(directory))] = hashlib.file_digest(
                        stream, "sha256"
                    ).hexdigest()
        if not found:
            raise RuntimeError(f"Empty Java build artifact: {name}")
    return {
        "sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True).encode()
        ).hexdigest(),
        "file_count": len(files),
    }


def validate_reuse(previous, current, directory, java_version, javac_version):
    """Source, toolchain and artifact checks precede any service startup."""
    if (
        previous.get("success") is not True
        or previous.get("valid_clean_source_evidence") is not True
        or current["source"]["source_dirty"]
        or previous.get("source") != current["source"]
        or previous.get("end_source") != current["source"]
        or previous.get("repository_root") != current["repository_root"]
        or previous.get("output_directory") != str(directory)
        or previous.get("java_build", {}).get("mode") != "fresh"
        or previous.get("java_version") != java_version
        or previous.get("javac_version") != javac_version
        or previous.get("file_sha256") != current["file_sha256"]
    ):
        raise RuntimeError(
            "Java build reuse requires a successful clean build of this checkout/toolchain"
        )
    identity = fingerprint(directory)
    if identity != previous["java_build"]["artifacts"]:
        raise RuntimeError("Cached Java build artifacts changed")
    return identity
