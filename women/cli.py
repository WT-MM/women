"""CLI entry point for sending messages to women in contacts."""

import argparse
import sys

import gender_guesser.detector as gender

from women.contacts import get_contacts
from women.logger import get_logger
from women.messenger import send_imessage

log = get_logger()


def load_exclude_list(path: str) -> set[str]:
    """Load excluded names from a file (one full name per line)."""
    try:
        with open(path) as f:
            names = {line.strip().lower() for line in f if line.strip()}
            log.info("Loaded %d excluded names from %s", len(names), path)
            return names
    except FileNotFoundError:
        log.error("Exclude file not found: %s", path)
        sys.exit(1)


def classify_contacts(
    contacts: list[dict[str, str]], exclude: set[str]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split contacts into confirmed women and ambiguous ones."""
    detector = gender.Detector()
    women: list[dict[str, str]] = []
    ambiguous: list[dict[str, str]] = []

    for contact in contacts:
        full_name = f"{contact['first_name']} {contact['last_name']}".lower()
        if full_name in exclude:
            log.debug("Excluding %s", full_name)
            continue

        guess = detector.get_gender(contact["first_name"])
        if guess == "female":
            women.append(contact)
        elif guess in ("mostly_female", "andy"):
            ambiguous.append(contact)

    log.info("Classified %d female, %d ambiguous", len(women), len(ambiguous))
    return women, ambiguous


def resolve_ambiguous(ambiguous: list[dict[str, str]]) -> list[dict[str, str]]:
    """Ask the user about ambiguous contacts."""
    resolved: list[dict[str, str]] = []
    for contact in ambiguous:
        name = f"{contact['first_name']} {contact['last_name']}"
        answer = input(f"Is '{name}' a woman? [y/N]: ").strip().lower()
        if answer == "y":
            resolved.append(contact)
    return resolved


def main() -> None:
    """Run the CLI."""
    if sys.platform != "darwin":
        log.error("This tool only works on macOS.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Send an iMessage to all women in your contacts.")
    parser.add_argument("message", nargs="?", default="\U0001f4aa\U0001f478", help="The message to send.")
    parser.add_argument("--exclude", help="Path to a file with names to exclude (one per line).")
    parser.add_argument("--live", action="store_true", help="Actually send messages (default is dry run).")
    args = parser.parse_args()

    exclude = load_exclude_list(args.exclude) if args.exclude else set()

    log.info("Reading contacts...")
    contacts = get_contacts()
    log.info("Found %d contacts with phone numbers", len(contacts))

    women, ambiguous = classify_contacts(contacts, exclude)

    if ambiguous:
        log.warning("%d contact(s) with ambiguous names", len(ambiguous))
        women.extend(resolve_ambiguous(ambiguous))

    if not women:
        log.warning("No matching contacts found.")
        sys.exit(0)

    log.info("Will message %d contact(s):", len(women))
    for c in women:
        log.info("  %s %s (%s)", c["first_name"], c["last_name"], c["phone"])

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
