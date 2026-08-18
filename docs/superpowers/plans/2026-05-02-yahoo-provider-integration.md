# Yahoo Provider Integration And Test Account Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Yahoo as a first-class provider and append three Yahoo test accounts into the existing group A/B spreadsheets.

**Architecture:** Reuse the existing domain-based provider routing through `var.mail_server`. Yahoo uses implicit SSL for IMAP and SMTP, so it uses the same `require_ssl: true` SMTP path added for Mail.ru.

**Tech Stack:** Python 3.10, PyQt5, smtplib, PySocks, pandas/openpyxl, JSON config.

---

## Implementation Tasks

- [x] Confirm Yahoo account source format in `docs/accounts/order8071399.txt` is `email:mail_password:phone:app_password`.
- [x] Use the fourth field as `EMAIL_PASS`, because direct Yahoo IMAP/SMTP auth succeeds with that value.
- [x] Update `config.example.json`, `data/gmonster_config/config.json`, and `data/gmonster_config/gmonster_config.json` so provider key `yahoo` uses IMAP `imap.mail.yahoo.com:993`, SMTP `smtp.mail.yahoo.com:465`, `require_ssl: true`, and `sent_folder: "Sent"`.
- [x] Append/update first two parsed Yahoo accounts in `data/sheets/group_a.xlsx` and final Yahoo account in `data/sheets/group_b.xlsx`.
- [x] Preserve the existing seven sheet columns: `FIRSTFROMNAME`, `LASTFROMNAME`, `EMAIL`, `EMAIL_PASS`, `PROXY:PORT`, `PROXY_USER`, `PROXY_PASS`.
- [x] Copy valid proxy settings from existing Gmail rows into the Yahoo rows for parity with current account setup.

## Verification Plan

- [x] Run `python3 -m py_compile smtp_base.py smtp.py imap_base.py imap.py proxy_smtplib.py main.py database.py var.py utils.py`.
- [x] Validate Yahoo provider config with `jq '.config.mail_server.yahoo' config.example.json data/gmonster_config/config.json data/gmonster_config/gmonster_config.json`.
- [x] Validate group sheets with pandas/openpyxl:
  - `data/sheets/group_a.xlsx` has two `@yahoo.com` rows with copied valid proxy fields.
  - `data/sheets/group_b.xlsx` has one `@yahoo.com` row with copied valid proxy fields.
- [x] Run direct Yahoo login-only checks for all three accounts:
  - IMAP `imap.mail.yahoo.com:993` login succeeds.
  - SMTP SSL `smtp.mail.yahoo.com:465` login succeeds.
  - `INBOX` and `Sent` select successfully.
- [x] Run proxy Yahoo login-only checks after copying Gmail proxies:
  - IMAP through copied SOCKS5 proxies fails with `SSLEOFError`.
  - SMTP SSL through copied SOCKS5 proxies fails with `SSLEOFError`.
  - Direct IMAP/SMTP still succeeds, so the remaining issue is proxy compatibility with Yahoo SSL mail ports rather than account credentials.

## Notes

- Yahoo official settings require IMAP SSL on port `993` and SMTP SSL on port `465` or `587`, with an app password for third-party clients.
- The copied Gmail proxies are not suitable for Yahoo SSL IMAP/SMTP even though they are valid proxy rows.
