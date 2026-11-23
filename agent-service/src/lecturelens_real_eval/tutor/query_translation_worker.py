"""Isolated worker run by a separately provisioned Python environment."""

import ctypes
import errno
import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path

COMPONENTS = {
    "sentencepiece.model": "72600ea476b3e3b76763919c3a30ef5104d9b473b19567d45251f56034264f54",
    "model/config.json": "b28e3136fc7a103e29585c10c8124849fb01d649531f58e00cbe240111560cd7",
    "model/model.bin": "edd8c8a6863d36959613ff291074627a1635fab2f51b872ef437e924d238921a",
    "model/shared_vocabulary.json": "c980413009e8041fc42c81730ad4b72ab6cb1313b3b89b1ced261fe5e177b024",
}


def deny_sockets():
    lib = ctypes.CDLL("libseccomp.so.2")
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    context = lib.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not context:
        raise RuntimeError("Local translation isolation is unavailable")
    try:
        for name in (b"socket", b"socketpair"):
            number = lib.seccomp_syscall_resolve_name(name)
            if number < 0 or lib.seccomp_rule_add(context, 0x00050000 | errno.EPERM, number, 0):
                raise RuntimeError("Local translation could not disable sockets")
        if lib.seccomp_load(context):
            raise RuntimeError("Local translation could not load its socket filter")
    finally:
        lib.seccomp_release(context)


def main():
    deny_sockets()
    root = Path(sys.argv[1])
    for name, expected in COMPONENTS.items():
        with (root / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise RuntimeError("Local translation model integrity mismatch")
    if version("ctranslate2") != "4.6.0" or version("sentencepiece") != "0.2.1":
        raise RuntimeError("Local translation dependency version mismatch")

    import ctranslate2
    import sentencepiece

    tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(root / "sentencepiece.model"))
    model = ctranslate2.Translator(str(root / "model"), device="cpu", inter_threads=1, intra_threads=2)
    queries = json.load(sys.stdin)
    encoded = tokenizer.encode(queries, out_type=str)
    # The wire limit also bounds decoding work for outputs that would not fit a query.
    rows = model.translate_batch(
        encoded, beam_size=4, max_decoding_length=int(sys.argv[2]), replace_unknowns=True
    )
    # The model can emit a literal SentencePiece boundary as an unknown replacement.
    json.dump([tokenizer.decode(result.hypotheses[0]).replace("▁", " ") for result in rows], sys.stdout)


if __name__ == "__main__":
    main()
