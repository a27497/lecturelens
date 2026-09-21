import math
from importlib.metadata import version
from pathlib import Path

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REPO = "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
MODEL_REVISION = "faf4aa4225822f3bc6376869cb1164e8e3feedd0"


def validate_vectors(vectors: list[list[float]], count: int, dimensions: int):
    if len(vectors) != count:
        raise ValueError("Embedding result count mismatch")
    for row in vectors:
        if len(row) != dimensions or not all(math.isfinite(v) for v in row):
            raise ValueError("Invalid embedding dimensions or nonfinite value")
        if sum(v * v for v in row) <= 0:
            raise ValueError("Zero embedding")


class LocalEmbedding:
    dimensions = 384
    # Weights, inference library, and chunker all participate in the cache version.
    index_version = f"minilm-multi:{MODEL_REVISION}:fastembed-{version('fastembed')}:chars240-overlap40-v1"

    def __init__(self, cache_dir: str):
        from fastembed import TextEmbedding
        from huggingface_hub import snapshot_download

        path = snapshot_download(
            MODEL_REPO,
            revision=MODEL_REVISION,
            cache_dir=str(Path(cache_dir) / "models"),
            allow_patterns=["*.json", "model_optimized.onnx"],
        )
        self.model = TextEmbedding(
            MODEL, specific_model_path=path, threads=2, providers=["CPUExecutionProvider"]
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = [row.tolist() for row in self.model.embed(texts, batch_size=32)]
        validate_vectors(vectors, len(texts), self.dimensions)
        return vectors
