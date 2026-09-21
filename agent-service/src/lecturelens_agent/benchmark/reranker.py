"""Eval-only multilingual cross encoder. Never imported by the production app."""

import math
from pathlib import Path

from .core import digest


class CrossEncoder:
    def __init__(self, config, cache=None):
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        path = Path(
            snapshot_download(
                config["repo"],
                revision=config["revision"],
                cache_dir=cache,
                allow_patterns=list(config["files_sha256"]),
            )
        )
        actual = {name: digest(path / name) for name in config["files_sha256"]}
        if actual != config["files_sha256"]:
            raise ValueError("Cross-Encoder weights/tokenizer differ from frozen model")
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True).eval()
        self.max_length = config["max_length"]

    def rerank(self, query, documents, batch_size=32):
        with self.torch.inference_mode():
            for start in range(0, len(documents), batch_size):
                batch = documents[start : start + batch_size]
                features = self.tokenizer(
                    [query] * len(batch),
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                scores = self.model(**features).logits.reshape(-1).tolist()
                if len(scores) != len(batch) or not all(math.isfinite(v) for v in scores):
                    raise ValueError("Invalid Cross-Encoder scores")
                yield from scores
