"""Schedule iMessage sends via macOS launchd."""

import json
import plistlib
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from women.logger import get_logger
from women.messenger import send_imessage
from women.watcher import start as start_watcher

log = get_logger()

JOBS_DIR = Path.home() / ".women" / "scheduled"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PREFIX = "com.women.schedule"


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _plist_label(job_id: str) -> str:
    return f"{PLIST_PREFIX}.{job_id}"


def _plist_path(job_id: str) -> Path:
    return PLIST_DIR / f"{_plist_label(job_id)}.plist"


def schedule(
    contacts: list[dict[str, str]],
    message: str,
    dt: datetime,
    reply_message: str | None = None,
) -> str:
    """Schedule a message send at the given datetime. Returns the job ID."""
    job_id = uuid.uuid4().hex[:8]

    # Save job data
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job_data: dict[str, object] = {
        "id": job_id,
        "message": message,
        "contacts": contacts,
        "scheduled_at": dt.isoformat(),
        "created_at": datetime.now().isoformat(),
    }
    if reply_message:
        job_data["reply_message"] = reply_message
    _job_path(job_id).write_text(json.dumps(job_data, indent=2))

    # Build plist — use current Python interpreter to run the fire command
    plist: dict[str, object] = {
        "Label": _plist_label(job_id),
        "ProgramArguments": [sys.executable, "-m", "women.scheduler", "fire", job_id],
        "StartCalendarInterval": {
            "Month": dt.month,
            "Day": dt.day,
            "Hour": dt.hour,
            "Minute": dt.minute,
        },
        "StandardOutPath": str(JOBS_DIR / f"{job_id}.log"),
        "StandardErrorPath": str(JOBS_DIR / f"{job_id}.log"),
    }

    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    plist_path = _plist_path(job_id)
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)

    # Load the job into launchd
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)

    log.info("Scheduled job %s for %s", job_id, dt.strftime("%Y-%m-%d %H:%M"))
    return job_id


def fire(job_id: str) -> None:
    """Execute a scheduled send, then clean up the job."""
    path = _job_path(job_id)
    if not path.exists():
        log.error("Job not found: %s", job_id)
        sys.exit(1)

    job = json.loads(path.read_text())
    message: str = job["message"]
    contacts: list[dict[str, str]] = job["contacts"]

    log.info("Firing scheduled job %s — sending to %d contact(s)", job_id, len(contacts))

    for c in contacts:
        name = f"{c['first_name']} {c['last_name']}"
        log.info("Sending to %s...", name)
        try:
            send_imessage(c["phone"], message)
        except Exception as e:
            log.error("Failed to send to %s: %s", name, e)

    # Start reply watcher if configured
    reply_message = job.get("reply_message")
    if reply_message:
        log.info("Starting reply watcher for job %s", job_id)
        start_watcher(job_id, contacts, reply_message)

    log.info("Done! Cleaning up send job %s", job_id)
    cancel(job_id)


def list_jobs() -> list[dict[str, str]]:
    """Return a list of pending scheduled jobs."""
    if not JOBS_DIR.exists():
        return []

    jobs: list[dict[str, str]] = []
    for f in sorted(JOBS_DIR.glob("*.json")):
        if f.name.endswith(".watcher.json"):
            continue
        try:
            data = json.loads(f.read_text())
            jobs.append(
                {
                    "id": data["id"],
                    "scheduled_at": data["scheduled_at"],
                    "message": data["message"],
                    "recipients": str(len(data["contacts"])),
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue
    return jobs


def cancel(job_id: str) -> None:
    """Unload and remove a scheduled job and its watcher (if any)."""
    from women.watcher import stop as stop_watcher

    plist_path = _plist_path(job_id)
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, check=False)
        plist_path.unlink()

    job_path = _job_path(job_id)
    if job_path.exists():
        job_path.unlink()

    log_path = JOBS_DIR / f"{job_id}.log"
    if log_path.exists():
        log_path.unlink()

    # Also stop the reply watcher if one exists
    watcher_path = JOBS_DIR / f"{job_id}.watcher.json"
    if watcher_path.exists():
        stop_watcher(job_id)

    log.info("Cancelled job %s", job_id)


# --- CLI entry points ---


def jobs_main() -> None:
    """List all scheduled sends and active watchers."""
    from women.watcher import list_watchers

    jobs = list_jobs()
    watchers = list_watchers()

    if not jobs and not watchers:
        log.info("No scheduled jobs or active watchers.")
        return

    if jobs:
        print("Scheduled sends:")
        id_w = max(len(j["id"]) for j in jobs)
        print(f"  {'ID':<{id_w}}  {'Scheduled':<20}  {'Recipients':<10}  Message")
        print(f"  {'─' * id_w}  {'─' * 20}  {'─' * 10}  {'─' * 20}")
        for j in jobs:
            dt = datetime.fromisoformat(j["scheduled_at"]).strftime("%Y-%m-%d %H:%M")
            msg_preview = j["message"][:30] + ("..." if len(j["message"]) > 30 else "")
            print(f"  {j['id']:<{id_w}}  {dt:<20}  {j['recipients']:<10}  {msg_preview}")

    if watchers:
        if jobs:
            print()
        print("Active reply watchers:")
        id_w = max(len(w["job_id"]) for w in watchers)
        print(f"  {'ID':<{id_w}}  {'Started':<20}  {'Progress':<10}  Reply message")
        print(f"  {'─' * id_w}  {'─' * 20}  {'─' * 10}  {'─' * 20}")
        for w in watchers:
            dt = datetime.fromisoformat(w["started_at"]).strftime("%Y-%m-%d %H:%M")
            msg_preview = w["reply_message"][:30] + ("..." if len(w["reply_message"]) > 30 else "")
            print(f"  {w['job_id']:<{id_w}}  {dt:<20}  {w['progress']:<10}  {msg_preview}")


def cancel_main() -> None:
    """Cancel a scheduled send."""
    import argparse

    parser = argparse.ArgumentParser(description="Cancel a scheduled women send.")
    parser.add_argument("job_id", help="The job ID to cancel.")
    args = parser.parse_args()

    job_path = _job_path(args.job_id)
    watcher_path = JOBS_DIR / f"{args.job_id}.watcher.json"
    if not job_path.exists() and not watcher_path.exists():
        log.error("Job not found: %s", args.job_id)
        sys.exit(1)

    cancel(args.job_id)


# Allow running as: python -m women.scheduler fire <job_id>
if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "fire":
        # Remove the module-level args so fire() works cleanly
        fire(sys.argv[2])
    else:
        print(f"Usage: {sys.argv[0]} fire <job_id>", file=sys.stderr)
        sys.exit(1)
