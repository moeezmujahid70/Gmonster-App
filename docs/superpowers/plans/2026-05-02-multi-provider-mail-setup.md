# GMX, Yahoo, And Mail.ru Provider Setup Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure a Gmonster-like codebase to support GMX, Yahoo, and Mail.ru alongside Gmail for SMTP sending and IMAP inbox/sent-mail operations.

**Architecture:** Reuse the existing domain-based provider routing through `var.mail_server`. Provider config must define SMTP server/port/TLS behavior and IMAP sent-folder names so the existing SMTP/IMAP worker classes can resolve provider-specific behavior without Gmail hard-coding.

**Tech Stack:** Python 3.10, PyQt5, smtplib, imaplib, PySocks, pandas/openpyxl, JSON config.

---

## Scope

- Use existing `data/sheets/group_a.xlsx` and `data/sheets/group_b.xlsx`.
- Do not generate or transform account sheets in this plan.
- Preserve the existing sheet schema: `FIRSTFROMNAME`, `LASTFROMNAME`, `EMAIL`, `EMAIL_PASS`, `PROXY:PORT`, `PROXY_USER`, `PROXY_PASS`.
- Update provider config/code so the accounts already present in the sheets can send and perform IMAP operations.

## Provider Config

Update the provider map in all runtime/template config files that exist in the target repo:

- `config.example.json`
- `data/gmonster_config/config.json`
- `data/gmonster_config/gmonster_config.json` if present

The app runtime source of truth is `data/gmonster_config/config.json`, loaded through `var.config_file_path`.

Required provider entries:

```json
"gmx": {
    "imap": {
        "server": "imap.gmx.com",
        "port": 993
    },
    "smtp": {
        "server": "mail.gmx.com",
        "port": 587,
        "require_ssl": false
    },
    "sent_folder": "Sent"
},
"yahoo": {
    "imap": {
        "server": "imap.mail.yahoo.com",
        "port": 993
    },
    "smtp": {
        "server": "smtp.mail.yahoo.com",
        "port": 465,
        "require_ssl": true
    },
    "sent_folder": "Sent"
},
"mail": {
    "imap": {
        "server": "imap.mail.ru",
        "port": 993
    },
    "smtp": {
        "server": "smtp.mail.ru",
        "port": 465,
        "require_ssl": true
    },
    "sent_folder": "&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-"
}
```

Important domain mapping:

- `@gmx.com` resolves to provider key `gmx`.
- `@yahoo.com` resolves to provider key `yahoo`.
- `@mail.ru` resolves to provider key `mail`.

## Required Code Behavior

- SMTP provider resolution must read `var.mail_server[mail_vendor]["smtp"]` and respect optional `require_ssl`.
- For `require_ssl: false`, SMTP should use regular `smtplib.SMTP`, call `starttls()`, then login.
- For `require_ssl: true`, SMTP should use `smtplib.SMTP_SSL`, then login.
- If proxy support is enabled, provide both paths:
  - STARTTLS providers use the existing `SmtpProxy`.
  - SSL providers use an `SmtpProxySSL` class based on `smtplib.SMTP_SSL`.
- IMAP provider resolution must read `var.mail_server[mail_vendor]["imap"]`.
- IMAP folder selection must use a provider-aware sent-folder resolver instead of hard-coded Gmail `"[Gmail]/Sent Mail"`.
- Gmail delete behavior can keep using `+X-GM-LABELS "\\Trash"`.
- Non-Gmail delete behavior should use `+FLAGS (\\Deleted)` and then `expunge()`.
- Sheet/database loading should not require `PROXY:PORT` to be non-empty; rows should load when `EMAIL` is non-empty.
- Proxy parsing should treat blank or invalid `PROXY:PORT` as no proxy instead of crashing.

## Verification Findings

Direct login-only tests passed:

- GMX:
  - IMAP `imap.gmx.com:993` passed.
  - SMTP STARTTLS `mail.gmx.com:587` passed.
  - `INBOX` and `Sent` folder selection passed.
- Yahoo:
  - IMAP `imap.mail.yahoo.com:993` passed.
  - SMTP SSL `smtp.mail.yahoo.com:465` passed.
  - `INBOX` and `Sent` folder selection passed.
- Mail.ru:
  - IMAP `imap.mail.ru:993` passed.
  - SMTP SSL `smtp.mail.ru:465` passed.
  - `INBOX` passed.
  - Sent folder passed with `&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-`.

Proxy test findings:

- Existing copied Gmail SOCKS5 proxies are not generally compatible with these providers.
- Mail.ru SMTP through copied proxies passed, but Mail.ru IMAP through copied proxies failed with `SSLEOFError`.
- Yahoo IMAP and SMTP through copied proxies failed with `SSLEOFError`.
- GMX IMAP through copied proxies failed with `SSLEOFError`.
- GMX SMTP through copied proxies failed with `SMTPServerDisconnected`.
- Therefore, credentials and provider config are valid; proxy compatibility is the remaining issue.

## Proxy Requirements

If proxies are required, ask the client for SOCKS5 proxies that explicitly support email traffic.

Required outbound destinations:

- GMX:
  - `imap.gmx.com:993`
  - `mail.gmx.com:587`
- Yahoo:
  - `imap.mail.yahoo.com:993`
  - `smtp.mail.yahoo.com:465`
- Mail.ru:
  - `imap.mail.ru:993`
  - `smtp.mail.ru:465`

Required per-account proxy fields:

```text
PROXY:PORT = proxy_host:proxy_port
PROXY_USER = proxy_username
PROXY_PASS = proxy_password
```

If no compatible proxies are available, run these providers without proxy. Direct IMAP/SMTP was verified successfully for GMX, Yahoo, and Mail.ru.

## Test Plan

- Run compile check:

```bash
python3 -m py_compile smtp_base.py smtp.py imap_base.py imap.py proxy_smtplib.py main.py database.py var.py utils.py
```

- Validate config:

```bash
jq '.config.mail_server.gmx, .config.mail_server.yahoo, .config.mail_server.mail' \
  config.example.json \
  data/gmonster_config/config.json \
  data/gmonster_config/gmonster_config.json
```

- Validate account sheets are readable and keep the expected schema:

```bash
python3 - <<'PY'
import pandas as pd

expected = [
    "FIRSTFROMNAME",
    "LASTFROMNAME",
    "EMAIL",
    "EMAIL_PASS",
    "PROXY:PORT",
    "PROXY_USER",
    "PROXY_PASS",
]

for path, sheet in [
    ("data/sheets/group_a.xlsx", "group_a"),
    ("data/sheets/group_b.xlsx", "group_b"),
]:
    df = pd.read_excel(path, engine="openpyxl", sheet_name=sheet)
    assert list(df.columns) == expected, path
    print(path, "rows=", len(df))
PY
```

- Run login-only verification before sending campaigns:
  - Direct IMAP login.
  - Direct SMTP login.
  - `INBOX` select.
  - provider sent-folder select.
  - proxy IMAP/SMTP login only if the client provides compatible email proxies.

## Operational Notes

- Yahoo and Mail.ru accounts usually require app passwords for third-party IMAP/SMTP clients.
- GMX can authenticate with the tested account password values, but account-level IMAP/SMTP settings still need to be enabled.
- Do not print account passwords, app passwords, proxy hosts, proxy usernames, or proxy passwords during tests.
- Successful campaign logs should contain `Sent - sender recipient`.
- `send mail without proxy` means the direct path was used.
- `send mail with proxy` means the proxy path was used.
