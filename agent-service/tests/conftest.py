import json
import tarfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def historical_eval_inputs(tmp_path_factory):
    """Restore historical input bytes for Mock eval tests of the current runtime."""
    tests = Path(__file__).resolve().parent
    checkout = tests.parents[1]
    inputs = tmp_path_factory.mktemp("historical-eval-inputs")
    # The archive contains frozen source inputs changed by E3 and Tutor, from
    # 300be51515867f7ece4f3a9224a484e825219ee0. The real runners still verify
    # their unmodified manifests against their own checkout.
    with tarfile.open(tests / "fixtures/p7-p8-prior-source.tar.gz") as archive:
        archive.extractall(inputs, filter="data")
    (inputs / "eval").symlink_to(checkout / "eval", target_is_directory=True)
    for suite in ("p7-real", "p8-tutor"):
        manifest = json.loads((inputs / "eval" / suite / "frozen.json").read_bytes())
        for path in manifest["files"]:
            if path.startswith("agent-service/") and not (inputs / path).exists():
                target = inputs / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(checkout / path)
    return inputs
