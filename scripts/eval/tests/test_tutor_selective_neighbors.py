"""Synthetic checks for the LL-P15 live vector receipt fence."""

from types import SimpleNamespace

import pytest
from tutor_selective_neighbors import INPUTS, LockedVector, check_vector_receipts


def test_locked_vector_fences_each_live_page(tmp_path):
    scope = {"owner_id": 1, "course_id": "example", "revision": 7}
    key = (1, "example", 7)
    expected = {key: "frozen-snapshot"}
    version = INPUTS["index_version"]
    response = SimpleNamespace(
        **scope, index_version=version, snapshot_id=expected[key]
    )
    retriever = SimpleNamespace(
        embedder=SimpleNamespace(index_version=version), search=lambda _: response
    )
    path = tmp_path / "vector.jsonl"
    with path.open("w") as out, path.open() as receipts:
        wrapped = LockedVector(retriever, expected, out)
        for _ in range(2):
            assert wrapped.search(None) is response
        assert check_vector_receipts(receipts, scope, expected, 1) == expected[key]
        assert wrapped.search(None) is response
        assert check_vector_receipts(receipts, scope, expected, 1) == expected[key]
        with pytest.raises(
            ValueError, match="Missing or mismatched live vector receipts"
        ):
            check_vector_receipts(receipts, scope, expected, 1)

        response.index_version = "wrong-version"
        with pytest.raises(ValueError, match="Vector response"):
            wrapped.search(None)
        response.index_version = version
        response.snapshot_id = "other-snapshot"
        with pytest.raises(ValueError, match="Vector response"):
            wrapped.search(None)
        assert receipts.read() == ""
