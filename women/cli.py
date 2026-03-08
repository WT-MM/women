"""CLI entry point for sending messages to women in contacts."""

import argparse
import sys
from datetime import datetime

from women.contacts import (
    add_filter_args,
    classify_contacts,
    get_contacts,
    load_filters,
    resolve_ambiguous,
)
from women.logger import get_logger
from women.messenger import send_imessage
from women.scheduler import schedule
from women.watcher import start as start_watcher

log = get_logger()


def main() -> None:
    """Run the CLI."""
    if sys.platform != "darwin":
        log.error("This tool only works on macOS.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Send an iMessage to all women in your contacts.")
    parser.add_argument("message", nargs="?", default="\U0001f4aa\U0001f478", help="The message to send.")
    add_filter_args(parser)
    parser.add_argument("--live", action="store_true", help="Actually send messages (default is dry run).")
    parser.add_argument("--schedule", metavar="DATETIME", help='Schedule send for later (e.g. "2026-03-14 09:00").')
    parser.add_argument("--reply", metavar="MESSAGE", help="Auto-reply to first response from each contact.")
    args = parser.parse_args()

    exclude, include = load_filters(args)

    log.info("Reading contacts...")
    contacts = get_contacts()
    log.info("Found %d contacts with phone numbers", len(contacts))

    women, ambiguous = classify_contacts(contacts, exclude=exclude, include=include)

    if ambiguous:
        log.warning("%d contact(s) with ambiguous names", len(ambiguous))
        women.extend(resolve_ambiguous(ambiguous))

    if not women:
        log.warning("No matching contacts found.")
        sys.exit(0)

    log.info("Will message %d contact(s):", len(women))
    for c in women:
        log.info("  %s %s (%s)", c["first_name"], c["last_name"], c["phone"])

    if args.schedule:
        try:
            dt = datetime.strptime(args.schedule, "%Y-%m-%d %H:%M")
        except ValueError:
            log.error('Invalid datetime format. Use "YYYY-MM-DD HH:MM".')
            sys.exit(1)
        if dt <= datetime.now():
            log.error("Scheduled time must be in the future.")
            sys.exit(1)
        job_id = schedule(women, args.message, dt, reply_message=args.reply)
        log.info("Use `women.jobs` to view or `women.cancel %s` to cancel.", job_id)
        return

    if not args.live:
        log.warning("Dry run - no messages sent. Use --live to send.")
        return

    confirm = input("\nSend messages? [y/N]: ").strip().lower()
    if confirm != "y":
        log.warning("Aborted.")
        return

    for c in women:
        name = f"{c['first_name']} {c['last_name']}"
        log.info("Sending to %s...", name)
        try:
            send_imessage(c["phone"], args.message)
        except Exception as e:
            log.error("Failed to send to %s: %s", name, e)

    log.info("Done!")

    if args.reply:
        import uuid

        job_id = uuid.uuid4().hex[:8]
        start_watcher(job_id, women, args.reply)
        log.info("Watching for replies. Use `women.jobs` to check status.")


def reply_main() -> None:
    """Start an auto-responder for women contacts without sending a message."""
    if sys.platform != "darwin":
        log.error("This tool only works on macOS.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Auto-respond to incoming messages from women in your contacts.")
    parser.add_argument("message", help="The auto-reply message to send.")
    add_filter_args(parser)
    args = parser.parse_args()

    exclude, include = load_filters(args)

    log.info("Reading contacts...")
    contacts = get_contacts()
    log.info("Found %d contacts with phone numbers", len(contacts))

    women, ambiguous = classify_contacts(contacts, exclude=exclude, include=include)

    if ambiguous:
        log.warning("%d contact(s) with ambiguous names", len(ambiguous))
        women.extend(resolve_ambiguous(ambiguous))

    if not women:
        log.warning("No matching contacts found.")
        sys.exit(0)

    log.info("Watching %d contact(s) for replies:", len(women))
    for c in women:
        log.info("  %s %s (%s)", c["first_name"], c["last_name"], c["phone"])

    import uuid

    job_id = uuid.uuid4().hex[:8]
    start_watcher(job_id, women, args.message)
    log.info("Auto-responder started. Use `women.jobs` to check status.")
