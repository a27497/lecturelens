"""Validate historical single-request observations without upgrading their evidence level."""


def single_turn_evidence(value, version):
    if not isinstance(value, dict) or type(version) is not int or not 1 <= version <= 2147483647:
        return None
    checked_at = value.get("checked_at")
    recorded_version = value.get("version")
    code = value.get("code")
    if (
        type(recorded_version) is not int
        or recorded_version != version
        or type(checked_at) is not int
        or not 1 <= checked_at <= 253402300799
        or type(value.get("ok")) is not bool
        or code not in (None, "MODEL_CHECK_FAILED", "MODEL_CHECK_TIMEOUT", "MODEL_TOOL_CONTRACT")
        or (value["ok"] and code is not None)
    ):
        return None
    return {"ok": value["ok"], "code": code, "checked_at": checked_at, "version": recorded_version}
