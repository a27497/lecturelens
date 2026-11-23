"""Optional offline query translation for Light Tutor's signed Evidence search."""

import json
import os
import re
import subprocess
from pathlib import Path

from .light_retrieval import QUERY_CHARS

TRANSLATION_TIMEOUT_SECONDS = 1.5
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]")
_KANA_OR_HANGUL = re.compile(r"[\u3040-\u30ff\uac00-\ud7af]")
_TERM = re.compile(
    r"`[^`\r\n]+`|[A-Za-z0-9\u0370-\u03ff_([][A-Za-z0-9\u0370-\u03ff_ .,+:/%$()[\]<>=≤≥≠±×*/^&|!\\-]*"
)


def _chinese(text):
    return _HAN.search(text) is not None and _KANA_OR_HANGUL.search(text) is None


def _retain_terms(original, translated):
    terms = dict.fromkeys(term.strip(" .,") for term in _TERM.findall(original))
    missing = [term for term in terms if term not in translated]
    return " ".join([translated, *missing])


class QueryLanguage:
    def __init__(self, mode, python, model):
        self.mode = mode
        self.python = Path(python)
        self.model = Path(model)

    def translate(self, queries):
        if not self.python.is_absolute() or not self.model.is_absolute():
            return None
        worker = Path(__file__).with_name("query_translation_worker.py")
        try:
            result = subprocess.run(
                [str(self.python), "-I", str(worker), str(self.model), str(QUERY_CHARS)],
                input=json.dumps(queries, ensure_ascii=False).encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={},
                check=True,
                timeout=TRANSLATION_TIMEOUT_SECONDS,
            )
            return json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None

    def rewrite(self, question, queries):
        if not _chinese(question):
            return queries
        local = [query for query in queries if _chinese(query)]
        if not local:
            return queries
        translated = self.translate(local)
        if not isinstance(translated, list) or len(translated) != len(local):
            return queries
        replacements = {}
        for original, english in zip(local, translated, strict=True):
            if not isinstance(english, str) or not english.strip() or _HAN.search(english):
                return queries
            try:
                replacement = _retain_terms(original, english.strip())
                if self.mode == "bilingual":
                    replacement = f"{original}\n{replacement}"
                if len(replacement.encode("utf-16-le")) > 2 * QUERY_CHARS:
                    return queries
            except UnicodeError:
                return queries
            replacements[original] = replacement
        return [replacements.get(query, query) for query in queries]


def configured_query_language():
    mode = os.environ.get("TUTOR_QUERY_LANGUAGE", "original")
    if mode == "original":
        return None
    if mode not in {"english", "bilingual"}:
        raise RuntimeError("TUTOR_QUERY_LANGUAGE_INVALID")
    return QueryLanguage(
        mode,
        os.environ.get("TUTOR_TRANSLATION_PYTHON", ""),
        os.environ.get("TUTOR_TRANSLATION_MODEL_DIR", ""),
    )
