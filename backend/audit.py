"""Append-only audit trail for the Campus Customs agent team.

Every agent-loop step is written to output/audit_trail.json as a JSON array.
The file is appended to, never wiped, so runs accumulate and can be audited
later. Each entry records which agent acted, who asked it to, how deep the
delegation went, which tool was called with which arguments, and what came
back.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from pydantic import BaseModel

from models import audit_entry

audit_path = Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"

# Writes come from several agents during one run, so serialise them.
write_lock = Lock()


def read_audit_trail() -> list[dict[str, Any]]:
    """Return every audit entry recorded so far, oldest first."""
    if not audit_path.exists():
        return []
    try:
        with audit_path.open(encoding="utf-8") as handle:
            entries = json.load(handle)
        return entries if isinstance(entries, list) else []
    except json.JSONDecodeError:
        # A half-written file should not take the whole run down.
        return []


def append_audit_entry(entry: audit_entry) -> dict[str, Any]:
    """Append one step to the audit trail and return what was written."""
    if not entry.timestamp:
        entry.timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    record = entry.to_dict()
    with write_lock:
        entries = read_audit_trail()
        entries.append(record)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2)
    return record


def next_step_number(run_id: str) -> int:
    """Return the next step number within a run."""
    steps = [e["step"] for e in read_audit_trail() if e.get("run_id") == run_id]
    return max(steps, default=0) + 1


def recent_events(
    limit: int = 50,
    run_id: str | None = None,
    ticket_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return the most recent audit entries, newest last.

    Filtering happens before the limit is applied, so asking for one ticket
    returns that ticket's latest steps even when later runs on other tickets
    have pushed them well down the file.

    Args:
        limit: How many entries to return.
        run_id: Limit to a single run, or leave out for all runs.
        ticket_id: Limit to a single ticket, or leave out for all tickets.
    """
    entries = read_audit_trail()
    if run_id is not None:
        entries = [e for e in entries if e.get("run_id") == run_id]
    if ticket_id is not None:
        entries = [e for e in entries if e.get("ticket_id") == ticket_id]
    return entries[-limit:]


def summarise_value(value: Any, max_length: int = 600) -> Any:
    """Make a value safe to store: JSON-friendly and not too long.

    Tool results can come back as pydantic models (a delegated agent's report),
    so those are converted to plain dictionaries before anything is written.
    """
    if isinstance(value, BaseModel):
        return summarise_value(value.model_dump(), max_length)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, str) and len(value) > max_length:
        return value[:max_length] + f"... [truncated, {len(value)} chars]"
    if isinstance(value, dict):
        return {key: summarise_value(item, max_length) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        shortened = [summarise_value(item, max_length) for item in value[:10]]
        if len(value) > 10:
            shortened.append(f"... [{len(value) - 10} more items]")
        return shortened
    if isinstance(value, str):
        return value
    # Anything else (dates, custom objects) is stored as readable text.
    return summarise_value(str(value), max_length)
