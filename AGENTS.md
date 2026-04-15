# AGENTS.md

This file provides project context for coding agents working in this repository.

## Project Overview

Gmonster is a PyQt5 desktop application for email outreach and follow-up automation. It combines:

- GUI flows for sign-in, sign-up, campaign management, inbox handling, and configuration
- SMTP and IMAP operations, including optional SOCKS5 proxy support
- SQLite persistence through SQLAlchemy
- Background scheduling through APScheduler
- Packaging support for PyInstaller-based desktop builds

Primary runtime target is Python 3.10.

## Setup And Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python var.py
```

Build the Windows executable with:

```bash
pip install -r requirements-updated.txt
pip install pyinstaller
pyinstaller --clean Gmonster.spec
```

There is currently no automated test suite in the repo.

## Recommended Reading Order

Read modules in this order before making non-trivial changes:

1. `var.py`
2. `dialog.py`
3. `database.py`
4. `main.py`
5. `smtp_base.py` and `imap_base.py`
6. `smtp.py`, `imap.py`, `followup_smtp.py`, and `campaign_reply.py`

## Architecture Map

- `var.py`: global state, data directories, config paths, scheduler startup, queues, single-instance lock, frozen-app SSL overrides
- `dialog.py`: authentication flow, startup dialogs, platform/device identification
- `main.py`: main window logic, campaign controls, AI compose prompt flow, inbox and account UI behavior
- `database.py`: SQLAlchemy models, engine/session setup, lightweight migration logic
- `smtp_base.py` and `imap_base.py`: connection/auth abstractions and provider resolution
- `smtp.py`, `imap.py`, `followup_smtp.py`: threaded send, follow-up, and inbox work
- `campaign_reply.py`: progress dialogs for campaign send/reply operations
- `gui.py`, `p_gui.py`, `authentication.py`, `sign_in.py`, `sign_up.py`, `email_input_gui.py`: generated PyQt UI wrappers and dialog code
- `proxy_smtplib.py` and `proxy_imaplib.py`: proxy-aware mail transport
- `utils.py` and `logger.py`: shared helpers and logging

## Working Conventions

- Use the existing `var` module as the source of shared runtime state. Do not introduce a parallel configuration layer.
- Keep threading patterns consistent with the current design: `threading.Thread`, Qt timers, and queues defined in `var.py`.
- Reuse the logging setup from `var.logger` or `logger.logger`. Keep logs actionable and avoid leaking secrets.
- Preserve the SQLite setup in `database.py`, including `check_same_thread=False` and the `targets.STATUS` migration behavior.
- Keep UI signal-slot wiring consistent with the current PyQt structure instead of introducing a second event model.
- Treat generated UI files as generated artifacts. Edit `.ui` files when possible, then regenerate Python wrappers.

## UI Notes

- `gui.py` is generated from `ui/gui.ui`; avoid manual edits unless regeneration is not practical.
- Other UI wrapper modules in the repo are also generated or tightly coupled to `.ui` files.
- After editing a `.ui` file, regenerate the matching Python file with PyQt's `pyuic`.

## Operational Pitfalls

- The frozen-app SSL certificate override in `var.py` is intentional. Do not remove it without replacing the packaging strategy for bundled certificates.
- The app writes runtime state under `data/`. Keep local state, logs, and generated files there.
- The runtime config path is `data/gmonster_config/config.json`. `config.example.json` is the template.
- Platform-specific code paths exist for Windows and Unix-like systems. Preserve both when changing startup, locking, subprocess, or update logic.
- `main.py` is large and tightly coupled to the GUI. Prefer scoped edits over broad refactors unless explicitly requested.
- Some modules interact through global variables and background threads. Verify side effects carefully when changing campaign, inbox, follow-up, or scheduler logic.
- This repository may contain local credentials in config or data files. Do not print, log, or commit secrets.

## Practical Guardrails

- Prefer minimal diffs.
- If changing mail flow, review both SMTP and IMAP consequences.
- If changing packaging or startup behavior, review `Gmonster.spec`, `GMonster2.spec`, `scripts/updater.bat`, and the frozen-app branches in `var.py`.
- If changing persistence, verify model definitions and migration behavior together.
