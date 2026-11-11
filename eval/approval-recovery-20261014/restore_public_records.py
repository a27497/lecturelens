#!/usr/bin/env python3
"""Restore frozen JSONL bytes from bounded public parts before offline verification."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / "public-record-parts.json").read_text())
    for record in manifest["records"]:
        chunks = []
        for part in record["parts"]:
            data = (ROOT / part["path"]).read_bytes()
            if len(data) != part["bytes"] or hashlib.sha256(data).hexdigest() != part["sha256"]:
                raise ValueError("public part identity mismatch")
            chunks.append(data)
        data = b"".join(chunks)
        if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("frozen record identity mismatch")
        target = ROOT / record["path"]
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError("refusing to replace a different existing record")
        else:
            with target.open("xb") as output:
                output.write(data)
        print(f"verified {record['path']}")


if __name__ == "__main__":
    main()
