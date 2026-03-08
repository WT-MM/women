"""Read contacts from the macOS Contacts app via AppleScript."""

import argparse
import subprocess
import sys

import gender_guesser.detector as gender

from women.logger import get_logger

log = get_logger()


def get_contacts() -> list[dict[str, str]]:
    """Return a list of contacts with first name and phone number."""
    script = """
    tell application "Contacts"
        set output to ""
        repeat with p in people
            set firstName to first name of p as text
            set lastName to last name of p as text
            try
                set phoneNum to value of first phone of p as text
                set output to output & firstName & "\\t" & lastName & "\\t" & phoneNum & "\\n"
            end try
        end repeat
        return output
    end tell
    """
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
    contacts = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            contacts.append({"first_name": parts[0], "last_name": parts[1], "phone": parts[2]})
    return contacts


def load_name_list(path: str) -> set[str]:
    """Load a set of names from a file (one full name per line)."""
    try:
        with open(path) as f:
            names = {line.strip().lower() for line in f if line.strip()}
            log.info("Loaded %d names from %s", len(names), path)
            return names
    except FileNotFoundError:
        log.error("File not found: %s", path)
        sys.exit(1)


def classify_contacts(
    contacts: list[dict[str, str]],
    exclude: set[str] | None = None,
    include: set[str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split contacts into confirmed women and ambiguous ones.

    Args:
        contacts: Raw contact list.
        exclude: Names to skip entirely.
        include: Names to always include, bypassing gender detection.
    """
    detector = gender.Detector()
    women: list[dict[str, str]] = []
    ambiguous: list[dict[str, str]] = []

    for contact in contacts:
        full_name = f"{contact['first_name']} {contact['last_name']}".lower()
        if exclude and full_name in exclude:
            log.debug("Excluding %s", full_name)
            continue

        guess = detector.get_gender(contact["first_name"])
        if guess == "female" or (include and full_name in include):
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


def add_filter_args(parser: argparse.ArgumentParser) -> None:
    """Add --exclude and --include arguments to a parser."""
    parser.add_argument("--exclude", help="Path to a file with names to exclude (one per line).")
    parser.add_argument(
        "--include", help="Path to a file with names to always include, bypassing gender detection (one per line)."
    )


def load_filters(args: argparse.Namespace) -> tuple[set[str] | None, set[str] | None]:
    """Load exclude and include sets from parsed args."""
    exclude = load_name_list(args.exclude) if args.exclude else None
    include = load_name_list(args.include) if args.include else None
    return exclude, include


def main() -> None:
    """Print women contacts in a formatted table."""
    if sys.platform != "darwin":
        log.error("This tool only works on macOS.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="List women in your contacts.")
    add_filter_args(parser)
    args = parser.parse_args()
    exclude, include = load_filters(args)

    log.info("Reading contacts...")
    all_contacts = get_contacts()
    if not all_contacts:
        log.warning("No contacts found.")
        return

    women, ambiguous = classify_contacts(all_contacts, exclude=exclude, include=include)
    contacts = women + ambiguous

    if not contacts:
        log.warning("No women contacts found.")
        return

    # Tag gender for display
    detector = gender.Detector()
    for c in contacts:
        c["gender"] = detector.get_gender(c["first_name"])

    contacts.sort(key=lambda c: (c["last_name"].lower(), c["first_name"].lower()))

    name_width = max(len(f"{c['first_name']} {c['last_name']}") for c in contacts)
    name_width = max(name_width, 4)
    label_map = {"female": "female", "mostly_female": "likely female", "andy": "ambiguous"}

    print(f"{'Name':<{name_width}}  {'Phone':<16}  Gender")
    print(f"{'─' * name_width}  {'─' * 16}  {'─' * 13}")
    for c in contacts:
        name = f"{c['first_name']} {c['last_name']}"
        print(f"{name:<{name_width}}  {c['phone']:<16}  {label_map.get(c['gender'], c['gender'])}")

    log.info("%d contacts", len(contacts))


def dump() -> None:
    """Dump all women contacts into an exclude file (one name per line)."""
    if sys.platform != "darwin":
        log.error("This tool only works on macOS.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Dump women contacts into an exclude file.")
    parser.add_argument("output", nargs="?", default="exclude.txt", help="Output file path (default: exclude.txt).")
    parser.add_argument("--all", action="store_true", help="Dump all contacts.")
    add_filter_args(parser)
    args = parser.parse_args()
    exclude, include = load_filters(args)

    log.info("Reading contacts...")
    all_contacts = get_contacts()
    if not all_contacts:
        log.warning("No contacts found.")
        return

    if args.all:
        contacts = all_contacts
        if exclude:
            contacts = [c for c in contacts if f"{c['first_name']} {c['last_name']}".lower() not in exclude]
        if include:
            contacts = [c for c in contacts if f"{c['first_name']} {c['last_name']}".lower() in include]
    else:
        women, ambiguous = classify_contacts(all_contacts, exclude=exclude, include=include)
        contacts = women + ambiguous

    names = [f"{c['first_name']} {c['last_name']}" for c in contacts]
    names.sort(key=str.lower)

    with open(args.output, "w") as f:
        for name in names:
            f.write(name + "\n")

    log.info("Wrote %d names to %s", len(names), args.output)
