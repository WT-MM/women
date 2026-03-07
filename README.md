# women

identify and interact with women

## Install

```bash
pip install women
```

or install from source:
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
women "wowie" --live

# Exclude specific contacts (one full name per line)
women --exclude exclude.txt --live
```
