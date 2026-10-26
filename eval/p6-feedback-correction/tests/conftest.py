from pathlib import Path


def pytest_addoption(parser):
    parser.addoption(
        "--p6-manifest",
        default=str(
            Path(__file__).resolve().parents[1] / "evidence/trial-05/manifest.json"
        ),
        help="Fresh Mock replay manifest in this isolated test database",
    )
