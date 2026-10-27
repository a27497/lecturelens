"""P7 hardening entry point; no network without both explicit switches."""

from lecturelens_real_eval.hardening_runner import main

if __name__ == "__main__":
    raise SystemExit(main())
