"""Read contacts from the macOS Contacts app via AppleScript."""

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


def main() -> None:
    """Print women contacts in a formatted table."""
    if sys.platform != "darwin":
        log.error("This tool only works on macOS.")
        sys.exit(1)

    log.info("Reading contacts...")
    all_contacts = get_contacts()
    if not all_contacts:
        log.warning("No contacts found.")
        return

    detector = gender.Detector()
    contacts = []
    for c in all_contacts:
        guess = detector.get_gender(c["first_name"])
        if guess in ("female", "mostly_female", "andy"):
            c["gender"] = guess
            contacts.append(c)

    if not contacts:
        log.warning("No women contacts found.")
        return

    contacts.sort(key=lambda c: (c["last_name"].lower(), c["first_name"].lower()))

    name_width = max(len(f"{c['first_name']} {c['last_name']}") for c in contacts)
    name_width = max(name_width, 4)
    label_map = {"female": "female", "mostly_female": "likely female", "andy": "ambiguous"}

    print(f"{'Name':<{name_width}}  {'Phone':<16}  Gender")
    print(f"{'─' * name_width}  {'─' * 16}  {'─' * 13}")
    for c in contacts:
        name = f"{c['first_name']} {c['last_name']}"
        print(f"{name:<{name_width}}  {c['phone']:<16}  {label_map[c['gender']]}")

    log.info("%d contacts", len(contacts))
