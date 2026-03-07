"""Send iMessages via AppleScript."""

import subprocess


def _escape_applescript(s: str) -> str:
    """Escape a string for use inside AppleScript double quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def send_imessage(phone: str, message: str) -> None:
    """Send an iMessage to a phone number."""
    safe_phone = _escape_applescript(phone)
    safe_message = _escape_applescript(message)
    script = f"""
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{safe_phone}" of targetService
        send "{safe_message}" to targetBuddy
    end tell
    """
    subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
