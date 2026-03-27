# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Gmonster is a PyQt5 desktop application for email outreach and follow-up automation. It coordinates GUI flows, SMTP/IMAP operations (with optional SOCKS5 proxy), SQLite persistence via SQLAlchemy, and background scheduling via APScheduler. Primary runtime target is Python 3.10.

## Setup and Run

```bash
# Local setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run app
python var.py

# Build Windows executable
pip install -r requirements-updated.txt  # use requirements.txt if unavailable
pip install pyinstaller
pyinstaller --clean Gmonster.spec
```

CI for Windows builds: `.github/workflows/build-windows-exe.yml`. No automated test suite exists — do not claim tests passed unless specific checks were run.

## Architecture

| Module | Responsibility |
|--------|---------------|
| `var.py` | Global app state, config bootstrap, scheduler startup, queues, single-instance lock, SSL cert override in frozen mode |
| `dialog.py` | Authentication flow and app startup orchestration |
| `main.py` | Main UI and campaign/follow-up behavior (large, tightly coupled) |
| `database.py` | SQLAlchemy models, engine/session setup, migration logic |
| `smtp_base.py` / `imap_base.py` | Protocol auth/connect abstractions and domain server resolution |
| `smtp.py` / `imap.py` / `followup_smtp.py` | Threaded email send/download/follow-up operations |
| `proxy_smtplib.py` / `proxy_imaplib.py` | SOCKS5 proxy-aware transport |
| `gui.py` | Auto-generated PyQt5 UI code — **do not edit directly** |

Read in this order when starting complex tasks: `var.py` → `dialog.py` → `database.py` → `main.py` → `smtp_base.py` / `imap_base.py`.

## Conventions

- **Global state:** import from `var` module; do not introduce parallel config systems.
- **Threading:** operations subclass `threading.Thread` and communicate via `queue.Queue` / `LifoQueue` objects defined in `var.py`.
- **Logging:** use `from var import logger` or `from logger import logger`; keep error context actionable.
- **DB:** use existing SQLAlchemy session/model conventions in `database.py`; preserve migration behavior for `targets.STATUS` column.
- **UI:** keep Qt signal/slot structure; avoid broad UI rewrites unless explicitly requested.
- **UI regeneration:** after editing `ui/gui.ui`, regenerate with `python3 -m PyQt5.uic.pyuic ui/gui.ui -o gui.py`.

## Pitfalls

- Frozen app SSL cert override in `var.py` is intentional — do not remove without a replacement strategy.
- SQLite engine uses `check_same_thread=False` — be careful with concurrent writes and shared sessions.
- Platform-specific branches exist for Windows (`msvcrt`, updater batch) and Unix/macOS (`fcntl`) — preserve both.
- Config/source files may contain credentials — avoid logging sensitive values and do not add new secrets.
- For email flow changes, verify both SMTP and IMAP side effects.
- For packaging changes, confirm `Gmonster.spec` and `.github/workflows/build-windows-exe.yml` stay consistent.
- Prefer minimal diffs; do not perform broad refactors in `main.py` unless requested.
