# women

Send iMessages to all the women in your macOS contacts.

## Install

```bash
git clone https://github.com/WT-MM/women.git
cd women
uv sync --extra dev
```

## Usage

```bash
# List all women contacts
women.contacts

# Preview recipients (dry run by default)
women

# Actually send the default message (💪👸)
women --live

# Send a custom message
women "Happy International Women's Day!" --live

# Exclude specific contacts (one full name per line)
women --exclude exclude.txt --live
```
