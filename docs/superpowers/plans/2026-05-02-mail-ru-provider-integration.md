# Mail.ru Provider Integration And Test Account Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Mail.ru as a first-class provider and append five Mail.ru test accounts into the existing group A/B spreadsheets.

**Architecture:** Reuse the existing domain-based provider routing through `var.mail_server`. Add SSL-capable SMTP proxy support for providers that require implicit TLS, then route Mail.ru through that path with `smtp.mail.ru:465`.

**Tech Stack:** Python 3.10, PyQt5, smtplib, PySocks, pandas/openpyxl, JSON config.

---

## Implementation Tasks

- [x] Add an `SmtpProxySSL` class in `proxy_smtplib.py` based on `smtplib.SMTP_SSL`, reusing `Proxifier.get_socket(...)` before wrapping the socket with the SSL context.
- [x] Update `smtp_base.py` follow-up sending to import `SmtpProxySSL` and choose it when `proxy_on` is enabled and provider config has `require_ssl: true`.
- [x] Update `smtp.py` campaign sending with the same `proxy + require_ssl` branch, keeping STARTTLS behavior for non-SSL providers.
- [x] Update `config.example.json`, `data/gmonster_config/config.json`, and `data/gmonster_config/gmonster_config.json` so provider key `mail` uses IMAP `imap.mail.ru:993`, SMTP `smtp.mail.ru:465`, `require_ssl: true`, and Mail.ru's encoded sent folder name.
- [x] Parse `docs/accounts/order8071357.txt` as `email:mail_password:app_password_or_secret:phone`.
- [x] Use the third field as `EMAIL_PASS`, because live IMAP/SMTP auth succeeds with that value.
- [x] Append first three parsed Mail.ru accounts to `data/sheets/group_a.xlsx` and final two parsed Mail.ru accounts to `data/sheets/group_b.xlsx`.
- [x] Preserve the existing seven sheet columns: `FIRSTFROMNAME`, `LASTFROMNAME`, `EMAIL`, `EMAIL_PASS`, `PROXY:PORT`, `PROXY_USER`, `PROXY_PASS`.
- [x] Initially leave `PROXY:PORT`, `PROXY_USER`, and `PROXY_PASS` blank for these Mail.ru rows because the source file does not contain proxy data.
- [x] Copy valid proxy settings from existing Gmail rows into the Mail.ru rows after confirming the source file's fourth field is a phone number, not a proxy port.

## Verification Plan

- [x] Run `python3 -m py_compile smtp_base.py smtp.py imap_base.py imap.py proxy_smtplib.py main.py database.py var.py`.
- [x] Validate Mail.ru provider config with `jq '.config.mail_server.mail' config.example.json data/gmonster_config/config.json`.
- [x] Validate group sheets with pandas/openpyxl:
  - `data/sheets/group_a.xlsx` has the expected columns and three `@mail.ru` rows.
  - `data/sheets/group_b.xlsx` has the expected columns and two `@mail.ru` rows.
- [x] Run direct Mail.ru login-only checks for all five accounts:
  - IMAP `imap.mail.ru:993` login succeeds.
  - SMTP SSL `smtp.mail.ru:465` login succeeds.
  - `INBOX` selects successfully.
  - Mail.ru sent folder selects successfully using `&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-`.
- [x] Run proxy Mail.ru login-only checks after copying Gmail proxies:
  - SMTP SSL `smtp.mail.ru:465` succeeds through copied SOCKS5 proxies for all five accounts.
  - IMAP `imap.mail.ru:993` fails through copied SOCKS5 proxies with `SSLEOFError` for all five accounts.
  - Direct IMAP still succeeds, so the remaining issue is proxy compatibility with Mail.ru IMAP rather than account credentials.

## Notes

- Mail.ru is structurally similar to Gmail/GMX in this app because provider selection already maps `@mail.ru` to key `mail`.
- Mail.ru differs from the current GMX STARTTLS setup because official Mail.ru guidance uses SMTP over SSL/TLS on port `465`.
- Live direct SMTP/IMAP verification passed after using the third field from `order8071357.txt` as the app password.
- GMX direct verification later confirmed that GMX uses sent folder `Sent`, not `Sent Items`.
- GMX direct IMAP/SMTP verification passed for all five existing GMX rows after updating `gmx.sent_folder` to `Sent`.
- GMX through copied SOCKS5 proxies failed for all five rows: IMAP returned `SSLEOFError`, SMTP returned `SMTPServerDisconnected`.
