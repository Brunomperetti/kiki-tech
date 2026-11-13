"""One status vocabulary for supervisor/UI, without changing editorial states."""

TERMINAL_ITEMS = {"COMPLETED", "BLOCKED", "CONFLICT", "ERROR"}


def public_state(state, counts, cancelling=False):
    if state == "CANCELLED":
        return "CANCELLED"
    if cancelling:
        return "CANCELLING"
    if state in {"PREPARING", "PREVIEW"}:
        return state
    if counts.get("RUNNING"):
        return "RUNNING"
    if counts.get("PENDING"):
        return "PENDING"
    if counts.get("ERROR"):
        return "FAILED"
    if counts.get("COMPLETED") and (counts.get("BLOCKED") or counts.get("CONFLICT")):
        return "COMPLETED_WITH_BLOCKS"
    if counts.get("BLOCKED") or counts.get("CONFLICT"):
        return "BLOCKED"
    return "COMPLETED"


def progress(counts, total, preparing=False):
    prepared = total - counts.get("PREPARING", 0)
    completed = counts.get("COMPLETED", 0)
    blocked = counts.get("BLOCKED", 0) + counts.get("CONFLICT", 0)
    return {
        "total": total,
        "prepared": prepared,
        "processed": sum(counts.get(k, 0) for k in TERMINAL_ITEMS),
        "completed": completed,
        "blocked": blocked,
        "failed": counts.get("ERROR", 0),
        "pending": counts.get("PENDING", 0) + counts.get("PREPARING", 0),
        "running": counts.get("RUNNING", 0),
        "cancelled": counts.get("CANCELLED", 0),
    }
