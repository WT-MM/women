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

# Dump all contacts into an exclude file
women.dump                # writes to exclude.txt
women.dump my_ignore.txt  # writes to custom file

# Schedule a send for later
women "asdqwe" --schedule "2026-03-14 09:00"

# Schedule with auto-reply on first response
women "wqewqeqwe!" --schedule "2026-03-14 09:00" --reply "`pip install women` today"

# Send now with auto-reply
women "wqewqe" --live --reply "`pip install women` today"

# View scheduled jobs and active reply watchers
women.jobs

# Cancel a scheduled job or watcher
women.cancel <job_id>
```
