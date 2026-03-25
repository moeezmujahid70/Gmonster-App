# Gmonster Copilot Instructions

## Project Snapshot

Gmonster is a PyQt5 desktop application for email outreach and follow-up automation. The app coordinates:

- GUI flows (auth + main app windows)
- SMTP and IMAP operations (with optional proxy support)
- SQLite persistence through SQLAlchemy
- Background scheduling with APScheduler

Primary runtime target is Python 3.10.

## Setup, Run, and Build

Use these commands unless a task says otherwise.

### Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run app

```bash
python var.py
```

### Build Windows executable

```bash
pip install -r requirements-updated.txt
pip install pyinstaller
pyinstaller --clean Gmonster.spec
```

Notes:

- CI workflow for Windows build is defined in `.github/workflows/build-windows-exe.yml`.
- If `requirements-updated.txt` is unavailable for a task, use `requirements.txt`.
- This repository currently has no automated test suite. Do not claim tests passed unless you ran specific checks.

## Architecture and Boundaries

Use this module map when making changes.

- `var.py`: global app state, config bootstrap, scheduler startup, queues, single-instance locking, SSL cert override in frozen mode
- `dialog.py`: authentication flow and app startup orchestration
- `main.py`: main UI and campaign/follow-up behavior (large, tightly coupled)
- `database.py`: SQLAlchemy models, engine/session setup, and migration logic
- `smtp_base.py` and `imap_base.py`: protocol auth/connect abstractions and domain server resolution
- `smtp.py`, `imap.py`, `followup_smtp.py`: threaded email send/download/follow-up operations
- `proxy_smtplib.py`, `proxy_imaplib.py`: proxy-aware transport behavior

Keep responsibilities in their current layer. Prefer small, localized edits over moving logic between core modules.

## Repository Conventions

Follow these project-specific patterns.

- Global state pattern: import and use values from `var` module instead of introducing parallel config systems.
- Threading pattern: many operations subclass `threading.Thread` and communicate using `queue.Queue` or `LifoQueue` objects defined in `var.py`.
- Logging pattern: use configured logger (`from var import logger` or `from logger import logger`) and keep error context actionable.
- DB pattern: use existing SQLAlchemy session/model conventions in `database.py`; preserve migration behavior for the `targets.STATUS` column.
- UI pattern: keep Qt signal/slot structure and avoid broad UI rewrites unless explicitly requested.
- UI regeneration rule: whenever `ui/gui.ui` is modified, regenerate `gui.py` using `python3 -m PyQt5.uic.pyuic ui/gui.ui -o gui.py` so Python UI code stays in sync.

## Pitfalls and Safety Checks

Watch for these issues during edits.

- Frozen app SSL handling in `var.py` is intentional. Do not remove cert override logic without a replacement strategy.
- SQLite engine uses `check_same_thread=False`. Be careful with concurrent writes and shared sessions.
- Some config and source files include secrets or credentials. Do not add new secrets, and avoid logging sensitive values.
- Platform-specific behavior exists for Windows (`msvcrt`, updater batch generation) and Unix/macOS (`fcntl`). Preserve compatibility branches.

## File Entry Points for Fast Context

Read in this order when starting complex tasks:

1. `README.md`
2. `var.py`
3. `dialog.py`
4. `database.py`
5. `main.py`
6. `smtp_base.py` and `imap_base.py`

## Change Strategy for Agents

- Prefer minimal diffs and preserve existing APIs.
- Do not perform broad refactors in `main.py` unless requested.
- Validate syntax for edited Python files before finishing.
- For behavior changes in email flow, verify both SMTP and IMAP side effects are considered.
- If a task touches packaging, confirm spec/workflow consistency (`Gmonster.spec`, `.github/workflows/build-windows-exe.yml`).
