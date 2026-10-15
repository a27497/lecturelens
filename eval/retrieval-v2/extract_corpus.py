"""Pre-freeze extraction from cached licensed source PDFs; normalized offsets are not media times."""

import hashlib
import json
import unicodedata
from pathlib import Path

from pypdf import PdfReader

assert not Path("eval/retrieval-v2/freeze.json").exists(), "Frozen corpus is immutable"
sources = json.loads(Path("eval/retrieval-v2/source-downloads.json").read_text())
corpus = {
    "id": "retrieval-v2",
    "license": "CC-BY-NC-SA-4.0",
    "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    "courses": {},
}
for ci, name in enumerate(
    ["algorithms", "linear", "calculus", "probability", "economics", "quantum"]
):
    rows = []
    for source in [s for s in sources if s["course"] == name]:
        lect = source["lecture_order"]
        pdf = Path(f".data/retrieval-v2/sources/{name}-{lect}.pdf")
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == source["sha256"], (
            "Source PDF changed"
        )
        pages = [page.extract_text() or "" for page in PdfReader(pdf).pages]
        for pi, page in enumerate(pages, 1):
            text = " ".join(unicodedata.normalize("NFKC", page).split())
            if text.startswith("MIT OpenCourseWare") and len(text) < 500:
                continue
            offset = 0
            ordinal = 0
            while offset < len(text):
                end = min(offset + 600, len(text))
                if end < len(text):
                    end = text.rfind(" ", offset + 400, end)
                if len(text) - end < 80:
                    end = len(text)
                fragment = text[offset:end].strip()
                if len(fragment) >= 60:
                    eid = f"v2-{name}-l{lect}-p{pi:02d}-e{ordinal:02d}"
                    rows.append(
                        {
                            "evidence_id": eid,
                            "text": fragment,
                            "content_hash": hashlib.sha256(
                                fragment.encode()
                            ).hexdigest(),
                            "start_ms": 0,
                            "end_ms": 0,
                            "retrievable": True,
                            "lecture_id": f"{name}-l{lect}",
                            "page": pi,
                            "normalized_character_range": [offset, end],
                            "source_url": source["pdf_url"],
                            "source_sha256": source["sha256"],
                            "language": "en",
                            "equivalence_group": eid,
                        }
                    )
                offset = end + 1
                ordinal += 1
    corpus["courses"][name] = {
        "scope": {
            "owner_id": 987654,
            "course_id": "retrieval-v2-" + name,
            "revision": 1,
        },
        "evidence": rows,
    }
Path("eval/retrieval-v2/corpus.json").write_text(
    json.dumps(corpus, ensure_ascii=False, indent=2) + "\n"
)
print("evidence", sum(len(c["evidence"]) for c in corpus["courses"].values()))
for name, c in corpus["courses"].items():
    print(name, len(c["evidence"]))
