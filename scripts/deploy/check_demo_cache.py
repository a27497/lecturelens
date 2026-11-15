#!/usr/bin/env python3
"""Read-only check of the demo's disposable assembled cache against trusted media."""

import hashlib
import json
from pathlib import Path


def main():
    path = Path("/tmp/courselingo/chunks/9/up_d69077ad31e2414384b9dc3e2c7d6701/assembled/source.mp4")
    expected_size = 5438854
    expected_md5 = "bf06e334a26a5a15c419d62619e077fd"
    expected_sha256 = "912abfda246ad20d6f35b1c9ef4237bd0f8a68eac3fe871563584f735770f342"
    if not path.is_file() or path.is_symlink():
        print(json.dumps({"path": str(path), "pass": False, "reason": "MISSING_OR_SYMLINK"}))
        return 1
    with path.open("rb") as source:
        md5 = hashlib.file_digest(source, "md5").hexdigest()
    with path.open("rb") as source:
        sha256 = hashlib.file_digest(source, "sha256").hexdigest()
    passed = path.stat().st_size == expected_size and md5 == expected_md5 and sha256 == expected_sha256
    print(json.dumps({"path": str(path), "size_bytes": path.stat().st_size, "md5": md5, "sha256": sha256, "pass": passed}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
