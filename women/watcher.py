"""Watch for replies in iMessage and auto-respond."""

import json
import plistlib
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from women.logger import get_logger
from women.messenger import send_imessage

log = get_logger()

JOBS_DIR = Path.home() / ".women" / "scheduled"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PREFIX = "com.women.watcher"
CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"

# Apple's Core Data epoch: 2001-01-01 00:00:00 UTC
_APPLE_EPOCH_OFFSET = 978307200


def _watcher_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.watcher.json"


def _plist_label(job_id: str) -> str:
    return f"{PLIST_PREFIX}.{job_id}"


def _plist_path(job_id: str) -> Path:
    return PLIST_DIR / f"{_plist_label(job_id)}.plist"


def _normalize_phone(phone: str) -> str:
    """Strip non-digit chars for comparison (keep leading +)."""
    return (
        "+" + "".join(c for c in phone if c.isdigit())
        if phone.startswith("+")
        else "".join(c for c in phone if c.isdigit())
    )


def _unix_to_apple_ns(ts: float) -> int:
    """Convert a Unix timestamp to Apple nanosecond timestamp."""
    return int((ts - _APPLE_EPOCH_OFFSET) * 1_000_000_000)


def _get_replies_since(phones: list[str], since_ns: int) -> dict[str, str]:
    """Query chat.db for incoming messages from the given phone numbers since a timestamp.

    Returns a dict of {normalized_phone: first_message_text} for contacts that replied.
    """
    if not CHAT_DB.exists():
        log.error("Messages database not found: %s", CHAT_DB)
        return {}

    conn = sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True)
    try:
        # Build lookup of normalized phone -> original handle IDs
        cursor = conn.execute("SELECT ROWID, id FROM handle")
        handle_map: dict[int, str] = {}
        for rowid, handle_id in cursor:
            handle_map[rowid] = handle_id

        # Find handles that match our target phones
        phone_set = {_normalize_phone(p) for p in phones}
        target_handles: dict[int, str] = {}
        for rowid, handle_id in handle_map.items():
            if _normalize_phone(handle_id) in phone_set:
                target_handles[rowid] = _normalize_phone(handle_id)

        if not target_handles:
            return {}

        # Query for incoming messages from those handles after the send time
        placeholders = ",".join("?" * len(target_handles))
        rows = conn.execute(
            f"""
            SELECT handle_id, text FROM message
            WHERE handle_id IN ({placeholders})
              AND is_from_me = 0
              AND date > ?
              AND text IS NOT NULL
            ORDER BY date ASC
            """,
            [*target_handles.keys(), since_ns],
        ).fetchall()

        # First reply per phone number
        replies: dict[str, str] = {}
        for handle_id, text in rows:
            norm = target_handles[handle_id]
            if norm not in replies:
                replies[norm] = text

        return replies
    finally:
        conn.close()


def start(job_id: str, contacts: list[dict[str, str]], reply_message: str) -> None:
    """Start a watcher that polls for replies and auto-responds."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)

    # Build phone -> contact mapping
    phone_map = {}
    for c in contacts:
        phone_map[_normalize_phone(c["phone"])] = c

    watcher_data = {
        "job_id": job_id,
        "reply_message": reply_message,
        "phone_map": {phone: contact for phone, contact in phone_map.items()},
        "replied": [],
        "sent_at_ns": _unix_to_apple_ns(datetime.now(tz=timezone.utc).timestamp()),
        "started_at": datetime.now().isoformat(),
    }
    _watcher_path(job_id).write_text(json.dumps(watcher_data, indent=2))

    # Create a launchd plist that runs every 60 seconds
    plist: dict[str, object] = {
        "Label": _plist_label(job_id),
        "ProgramArguments": [sys.executable, "-m", "women.watcher", "check", job_id],
        "StartInterval": 60,
        "StandardOutPath": str(JOBS_DIR / f"{job_id}.watcher.log"),
        "StandardErrorPath": str(JOBS_DIR / f"{job_id}.watcher.log"),
    }

    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    plist_path = _plist_path(job_id)
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)

    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    log.info("Watcher started for job %s — polling every 60s", job_id)


def check(job_id: str) -> None:
    """Check for new replies and auto-respond. Called periodically by launchd."""
    path = _watcher_path(job_id)
    if not path.exists():
        log.error("Watcher data not found: %s", job_id)
        return

    data = json.loads(path.read_text())
    reply_message: str = data["reply_message"]
    phone_map: dict[str, dict[str, str]] = data["phone_map"]
    replied: list[str] = data["replied"]
    since_ns: int = data["sent_at_ns"]

    # Phones we still need to watch
    pending_phones = [p for p in phone_map if p not in replied]
    if not pending_phones:
        log.info("All contacts have been replied to. Stopping watcher.")
        stop(job_id)
        return

    # Check for new replies — use original phone format for the query
    original_phones = [phone_map[p]["phone"] for p in pending_phones]
    new_replies = _get_replies_since(original_phones, since_ns)

    for norm_phone, _reply_text in new_replies.items():
        if norm_phone in replied:
            continue

        contact = phone_map.get(norm_phone)
        if not contact:
            continue

        name = f"{contact['first_name']} {contact['last_name']}"
        log.info("Reply from %s — auto-responding", name)
        try:
            send_imessage(contact["phone"], reply_message)
            replied.append(norm_phone)
        except Exception as e:
            log.error("Failed to auto-reply to %s: %s", name, e)

    # Update state
    data["replied"] = replied
    path.write_text(json.dumps(data, indent=2))

    remaining = len(phone_map) - len(replied)
    log.info("Watcher %s: %d/%d replied", job_id, len(replied), len(phone_map))

    if remaining == 0:
        log.info("All contacts replied. Stopping watcher.")
        stop(job_id)


def stop(job_id: str) -> None:
    """Stop and clean up a watcher."""
    plist_path = _plist_path(job_id)
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, check=False)
        plist_path.unlink()

    watcher_path = _watcher_path(job_id)
    if watcher_path.exists():
        watcher_path.unlink()

    log_path = JOBS_DIR / f"{job_id}.watcher.log"
    if log_path.exists():
        log_path.unlink()

    log.info("Watcher stopped for job %s", job_id)


def list_watchers() -> list[dict[str, str]]:
    """Return a list of active watchers."""
    if not JOBS_DIR.exists():
        return []

    watchers: list[dict[str, str]] = []
    for f in sorted(JOBS_DIR.glob("*.watcher.json")):
        try:
            data = json.loads(f.read_text())
            total = len(data["phone_map"])
            replied = len(data["replied"])
            watchers.append(
                {
                    "job_id": data["job_id"],
                    "started_at": data["started_at"],
                    "reply_message": data["reply_message"],
                    "progress": f"{replied}/{total}",
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue
    return watchers


# Allow running as: python -m women.watcher check <job_id>
if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        check(sys.argv[2])
    else:
        print(f"Usage: {sys.argv[0]} check <job_id>", file=sys.stderr)
        sys.exit(1)
