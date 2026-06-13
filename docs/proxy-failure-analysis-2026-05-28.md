# Proxy Failure Analysis — group_a.xlsx (2026-05-28)

## TL;DR

The SOCKS5 proxies in `data/sheets/group_a.xlsx` are valid and not doing TLS interception. The failures for Yahoo / AOL / GMX / Mail.ru-IMAP are **provider-side IP-reputation blocks at L4** — the destination edge drops connections from the proxy IPs before any TLS or SMTP dialogue. No client-side knob (TLS version, ciphers, retries, jitter) fixes it. The only effective remedy is changing the egress IP (residential / mobile-ISP proxy pool) for those provider accounts.

Gmail (SMTP+IMAP) and Mail.ru SMTP work through the current proxies.

## Source data

- Debug log: `data/logs/proxy-mail-debug-group-a-20260528-155959.md`
- Sheet: `data/sheets/group_a.xlsx` (per-account SOCKS5 proxies on `81.x:402x`)
- Diagnostic scripts (added):
  - `scripts/proxy_diag.py` — baseline SOCKS5 + TLS + greeting/EHLO per row
  - `scripts/proxy_tls_experiment.py` — failing endpoints × {default, TLS1.2, TLS1.3} × 3 attempts

## Baseline run

| Provider | Endpoint            | Result                                 |
| -------- | ------------------- | -------------------------------------- |
| Gmail    | SMTP 587 STARTTLS   | OK (banner, EHLO, STARTTLS, real cert) |
| Gmail    | IMAP 993            | OK TLS, real Google cert               |
| Mail.ru  | SMTP 465 SSL        | OK, real GlobalSign cert               |
| Mail.ru  | IMAP 993 SSL        | FAIL `SSLEOFError`                   |
| GMX      | IMAP 993 SSL        | FAIL `SSLEOFError`                   |
| GMX      | SMTP 587 STARTTLS   | FAIL — empty banner, immediate FIN    |
| Yahoo    | IMAP 993 / SMTP 465 | FAIL `SSLEOFError`                   |
| AOL      | IMAP 993 / SMTP 465 | FAIL `SSLEOFError`                   |

`proxy_tcp` succeeded in every single case. Kill happens immediately after the TCP handshake.

## Ruling out TLS interception (MITM)

Pulled the peer cert via `CERT_NONE` wrap on the few endpoints that complete handshake:

- `smtp.gmail.com:465` → `CN=smtp.gmail.com`, issuer **Google Trust Services**
- `imap.gmail.com:993` → `CN=imap.gmail.com`, issuer **Google Trust Services**
- `smtp.mail.ru:465` → `CN=*.mail.ru`, issuer **GlobalSign**

Real provider certs → proxy is a clean SOCKS5 tunnel, not MITM. (Initial `CERT_VERIFY_FAILED` on this dev machine was a local Python trust-store issue, unrelated to the proxy.)

## Ruling out client-side fixes — TLS variant experiment

`scripts/proxy_tls_experiment.py` hit each failing endpoint with three TLS contexts (`default`, `TLSv1_2` pinned + `SECLEVEL=2` ciphers, `TLSv1_3` pinned) × 3 attempts with jittered backoff.

**Result: 0 / 63 successes.**

- Deterministic failure (0/3 every time, ~0.2 s) → not flaky/percentage-based, retries won't help.
- Same fail timing regardless of TLS version → server doesn't read the ClientHello.
- GMX SMTP 587 plaintext stage also dies (empty banner, FIN) — proves the kill is pre-TLS at the L4 layer.

## Conclusion

The kill is at the **destination provider's edge**, applied to the proxy's source IP, before any application-layer or even TLS-layer dialogue begins. Yahoo, AOL, GMX, and Mail.ru-IMAP all enforce this for the current `81.x` datacenter proxy IPs. Gmail and Mail.ru-SMTP currently do not.

### Not fixable client-side

- TLS version / cipher pinning
- SNI tweaks (already correct)
- Retries / backoff / jitter
- Auth method changes (connection dies before auth)
- Proxy auth / SOCKS settings (tunnel is already up when the kill happens)

### What does fix it

- **Move blocked providers to a residential / mobile-ISP proxy pool.** Keep current datacenter proxies for Gmail and Mail.ru-SMTP.
- **Per-provider proxy routing** in config so accounts can be assigned different proxies without sheet rewrites.
