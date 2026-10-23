from __future__ import annotations

from datetime import datetime
from typing import Optional


def next_source_health(
    prev: Optional[dict],
    result: dict,
    now: datetime,
) -> tuple[dict, str | None]:
    status = result.get("status")
    if status not in {"ok", "empty", "error"}:
        raise ValueError("status must be ok, empty, or error")

    previous = prev or {}
    consecutive_errors = int(previous.get("consecutive_errors") or 0)
    consecutive_empty = int(previous.get("consecutive_empty") or 0)
    last_success_at = previous.get("last_success_at")

    if status == "ok":
        consecutive_errors = 0
        consecutive_empty = 0
        last_success_at = now
    elif status == "empty":
        consecutive_errors = 0
        consecutive_empty += 1
    else:
        consecutive_errors += 1

    status_code = result.get("status_code")
    try:
        status_code = int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        status_code = None

    state = {
        "last_run_at": now,
        "last_status": status,
        "last_success_at": last_success_at,
        "last_job_count": max(0, int(result.get("job_count") or 0)),
        "last_berlin_engineering_count": max(0, int(result.get("berlin_engineering_count") or 0)),
        "consecutive_errors": consecutive_errors,
        "consecutive_empty": consecutive_empty,
        "last_error": (str(result.get("error") or "")[:300] or None) if status == "error" else None,
        "last_status_code": status_code,
        "disabled_at": previous.get("disabled_at"),
        "disabled_reason": previous.get("disabled_reason"),
    }

    disable_reason = None
    if status == "error" and previous.get("disabled_at") is None:
        if (consecutive_errors >= 7 and status_code in {404, 410}) or consecutive_errors >= 21:
            code_detail = f" (HTTP {status_code})" if status_code is not None else ""
            disable_reason = f"auto: {consecutive_errors} consecutive errors{code_detail}"
            state["disabled_at"] = now
            state["disabled_reason"] = disable_reason

    return state, disable_reason
