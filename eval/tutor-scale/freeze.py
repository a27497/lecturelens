"""One-time freeze for this new candidate; never rewrites historical manifests."""

from dataset import HERE, ROOT, VERSION, digest, write

if __name__ == "__main__":
    files = [p for p in HERE.iterdir() if p.suffix == ".py"] + [
        HERE / "dataset-lock.json",
        HERE / "README.md",
        HERE / "compose.yaml",
    ]
    write(
        HERE / "candidate.json",
        dict(
            candidate="tutor-scale-preparation-v1",
            dataset_version=VERSION,
            data_kind="SYNTHETIC_EVAL_ASSETS",
            base_sha="300be51515867f7ece4f3a9224a484e825219ee0",
            historical_manifest_sha256=digest(ROOT / "eval/p8-tutor/frozen.json"),
            files={str(p.relative_to(ROOT)): digest(p) for p in sorted(files)},
            note="New evaluation tooling identity; historical P8 v9 and AU pins unchanged. "
            "Runtime modules remain pinned by original P8 verify_inputs(). No real quality result.",
        ),
    )
