# GMX Provider Integration Notes

This document describes the changes needed to add GMX support to a Gmonster-like codebase that currently assumes Gmail-style SMTP, IMAP, and sent-mail behavior.

## Goal

Support `@gmx.com` accounts alongside Gmail accounts for:

- campaign SMTP sending
- follow-up SMTP sending
- inbox download
- sent-mail download
- read flag changes
- inbox and sent-mail deletion

## Provider Configuration

Add GMX to the runtime `mail_server` config. In this project, the source template is `config.example.json`, and the live app reads `data/gmonster_config/config.json` through `var.mail_server`.

Recommended GMX config for this codebase:

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
    "sent_folder": "Sent Items"
}
```

Use port `587` with STARTTLS because the existing proxy SMTP path creates a regular SMTP connection and then calls `starttls()`. GMX also supports port `465` with SSL/TLS, but that requires an SSL-wrapped proxy SMTP implementation before it is safe to use with `proxy_on`.

Also update existing user config files, not only the example template. Existing installs keep reading `data/gmonster_config/config.json`, so new providers added only to `config.example.json` will not be available until the live config is migrated.

## SMTP Changes

Update the shared SMTP provider resolver so it reads a full provider object, not only Gmail defaults:

- derive `mail_vendor` from the sender email domain
- read `var.mail_server[mail_vendor]["smtp"]["server"]`
- read `var.mail_server[mail_vendor]["smtp"]["port"]`
- read optional `var.mail_server[mail_vendor]["smtp"]["require_ssl"]`
- default `require_ssl` to `false`

Apply this in `smtp_base.py` so follow-up sending inherits the same behavior.

Apply the same login behavior in `smtp.py` for campaign sending:

- if `require_ssl` is true and no proxy is used, create `smtplib.SMTP_SSL`
- otherwise create regular `smtplib.SMTP`
- call `starttls()` only when `require_ssl` is false
- keep proxy sending on the regular SMTP plus STARTTLS path unless an SSL proxy class is added

## IMAP Changes

Move Gmail-specific folder handling into provider-aware helpers in `imap_base.py`:

- add a sent-folder token such as `__SENT__`
- add `get_sent_folder()` that reads `provider_config["sent_folder"]`
- keep Gmail fallback as `"[Gmail]/Sent Mail"`
- add `resolve_folder()` so callers can request `INBOX` or `__SENT__`

Use those helpers anywhere the old code hard-coded Gmail's sent folder.

Important call sites:

- `ImapReadFlagEmail.change_flag()`
- `ImapDeleteEmail.run()`
- `ImapDownload.run()`
- the download dialog setup in `main.py`

The download folder list should become:

```python
folders=["INBOX", "__SENT__"]
```

## Delete Behavior

Gmail supports `+X-GM-LABELS "\\Trash"`, but GMX does not. Add a provider-aware delete helper:

```python
def delete_message(self, imap, uid):
    if self.mail_vendor == "gmail":
        imap.uid("STORE", uid, "+X-GM-LABELS", "\\Trash")
        return False
    imap.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
    return True
```

For non-Gmail providers, call `imap.expunge()` after deleting messages from the selected mailbox.

## Folder Download Behavior

When downloading inbox and sent mail:

- resolve each configured folder before selecting it
- skip unresolved folders
- mark messages as sent when the resolved folder is not `INBOX`
- do not compare against the raw token, because `__SENT__` is only an internal placeholder

## Verification Checklist

Use at least one GMX account with IMAP enabled in the GMX account settings.

Check these flows:

- campaign send logs in successfully through `mail.gmx.com:587`
- follow-up send logs in through the same provider config
- inbox download selects `INBOX`
- sent download selects `Sent Items`
- read flag changes work for inbox and sent messages
- delete works for inbox and sent messages, followed by `expunge()` for GMX
- Gmail still downloads `"[Gmail]/Sent Mail"` and still uses Gmail trash labels

## Current Integration Status In This Repository

GMX is mostly integrated:

- `config.example.json` includes a `gmx` provider
- `smtp_base.py` and `smtp.py` support provider SMTP config and `require_ssl`
- `imap_base.py` supports provider-aware sent folder resolution
- `imap.py` no longer hard-codes Gmail's sent folder in download, read, or delete flows
- `main.py` passes `__SENT__` instead of Gmail's sent folder string

Remaining risk:

- The SSL SMTP path only works without proxy. If live config uses GMX port `465` with `require_ssl: true` while `proxy_on` is enabled, sending can fail because `SmtpProxy` is not SSL-wrapped. Prefer GMX port `587` with `require_ssl: false`, or add an SSL-capable proxy SMTP class.
