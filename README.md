# Gmonster App

Gmonster is a PyQt5 desktop application for email outreach and follow-up automation.

It combines:

- GUI flows (authentication and campaign management)
- SMTP sending and IMAP inbox handling
- SQLite persistence through SQLAlchemy
- Background scheduling using APScheduler

## Requirements

- Python 3.10 recommended
- macOS, Linux, or Windows

## Repository

- Public repository: https://github.com/moeezmujahid70/Gmonster-App

## Quick Start

1. Clone and enter the project directory

   git clone https://github.com/moeezmujahid70/Gmonster-App.git
   cd Gmonster-App

2. Create and activate a virtual environment

   macOS or Linux:
   python -m venv .venv
   source .venv/bin/activate

   Windows (PowerShell):
   python -m venv .venv
   .venv\Scripts\Activate.ps1

3. Install dependencies

   pip install -r requirements.txt

4. Run the app

   python var.py

## Configuration

Runtime config is loaded from:

- data/gmonster_config/config.json

The root-level config.json is not used by runtime and is intentionally excluded.

Use the tracked template to create local config:

- config.example.json

Then copy values into:

- data/gmonster_config/config.json

## Data and Logs

Application data is stored under:

- data/

Key subfolders include:

- data/gmonster_config/
- data/email/
- data/logs/
- data/sheets/

These folders contain local state and are not intended for source control.

## Build Windows Executable

1. Install build dependencies

   pip install -r requirements-updated.txt
   pip install pyinstaller

2. Build

   pyinstaller --clean Gmonster.spec

CI workflow for Windows build:

- .github/workflows/build-windows-exe.yml

## Project Structure

- var.py: global app state, scheduler startup, config bootstrap
- dialog.py: authentication and app startup flow
- main.py: main desktop UI and campaign logic
- database.py: SQLAlchemy models and migration logic
- smtp.py and imap.py: email operations

## Security Notes

- Do not commit personal API keys, email credentials, or webhook URLs.
- Keep local environment and runtime files in data/ only.
- If a secret was ever committed locally, rotate or revoke it immediately.

## Testing

This repository currently has no automated test suite.

## License

See LICENSE.
