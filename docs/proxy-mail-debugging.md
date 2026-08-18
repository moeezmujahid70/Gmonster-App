# Proxy Mail Debugging Guide

This guide explains how to debug SMTP and IMAP failures when accounts use sheet-configured proxies.

The goal is to separate these cases:

- The proxy credentials are wrong.
- The proxy tunnel cannot reach the mail host.
- TLS/SSL fails after the proxy tunnel opens.
- SMTP/IMAP login fails after the provider accepts the connection.
- The provider closes the session because of proxy IP reputation, geo/security checks, or provider-specific filtering.

## Safety Rules

- Do not print account passwords.
- Do not print proxy host, proxy port, proxy username, or proxy password.
- Redact SMTP `AUTH` commands and base64 payloads.
- Mask emails in logs, for example `ab***@gmail.com`.
- Use login-only tests unless a real send test is explicitly needed.

## Debug Levels

SMTP has built-in protocol debug output:

```python
server.set_debuglevel(2)
```

Useful SMTP stages:

- `proxy_tcp`: SOCKS5 tunnel opened to the destination host and port.
- `connect_banner`: SMTP server returned the initial `220` banner.
- `ehlo_plain`: server responded to `EHLO` before STARTTLS.
- `starttls`: server accepted `STARTTLS`.
- `ehlo_tls`: server responded to `EHLO` after TLS upgrade.
- `ssl_connect_banner`: SSL SMTP connection opened on port `465`.
- `login`: SMTP authentication succeeded.

Useful IMAP stages:

- `proxy_tcp`: SOCKS5 tunnel opened to the IMAP host and port.
- `tls_and_greeting`: SSL IMAP session opened and server greeting was received.
- `login`: IMAP authentication succeeded.
- `select_inbox`: `INBOX` was selected.
- `select_sent`: configured sent folder was selected.

## Capturing SMTP Debug Output

`smtplib` writes debug output to `stderr`. There are two practical ways to capture it.

### Preferred In-App Approach

Use `contextlib.redirect_stderr()` for test scripts. It is simpler and safer than replacing file descriptors globally:

```python
import contextlib
import io

debug_output = io.StringIO()

with contextlib.redirect_stderr(debug_output):
    server.set_debuglevel(2)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(email, password)

trace = debug_output.getvalue()
```

Before printing `trace`, redact sensitive lines:

```python
def sanitize_smtp_trace(trace, email, masked_email):
    lines = []
    for line in trace.splitlines():
        upper = line.upper()
        if "AUTH " in upper or "'AUTH" in upper:
            lines.append("send: AUTH <redacted>")
            continue
        lines.append(line.replace(email, masked_email))
    return "\n".join(lines)
```

### File Descriptor Approach

The alternate approach is to temporarily redirect file descriptor `2` (`stderr`) into a temporary file, run the SMTP task, then restore `stderr`.

This idea comes from:

- Source: https://stackoverflow.com/a/34682107
- Author: vy32
- Retrieved: 2026-05-28
- License: CC BY-SA 3.0

Use this only in isolated diagnostic scripts. It changes process-level `stderr`, so it is not ideal inside the running PyQt app.

## Recommended Diagnostic Flow

Run checks in this order for each provider/account.

1. Parse one row from `data/sheets/group_a.xlsx`.
2. Mask the account email for output.
3. Parse `PROXY:PORT`, `PROXY_USER`, and `PROXY_PASS`.
4. Open a raw SOCKS5 TCP tunnel to the provider host and port.
5. Run the SMTP or IMAP protocol login through the same proxy.
6. Print only staged results and sanitized protocol trace.

## Provider Settings

Current provider settings used by this project:

```text
gmail:
  IMAP: imap.gmail.com:993 SSL
  SMTP: smtp.gmail.com:587 STARTTLS

gmx:
  IMAP: imap.gmx.com:993 SSL
  SMTP: mail.gmx.com:587 STARTTLS

yahoo:
  IMAP: imap.mail.yahoo.com:993 SSL
  SMTP: smtp.mail.yahoo.com:465 SSL

mail.ru:
  IMAP: imap.mail.ru:993 SSL
  SMTP: smtp.mail.ru:465 SSL

aol:
  IMAP: imap.aol.com:993 SSL
  SMTP: smtp.aol.com:465 SSL
```

## How To Interpret Failures

### `proxy_tcp=FAIL`

The proxy could not connect to the destination host and port.

Likely causes:

- Wrong proxy host or port.
- Wrong proxy username or password.
- Proxy does not support SOCKS5.
- Proxy provider blocks the destination host or port.
- Local network cannot reach the proxy.

### `proxy_tcp=OK` then `SSLEOFError`

The proxy tunnel opened, but the TLS/SSL session was closed.

Likely causes:

- Mail provider rejected the proxy IP range.
- Provider closed the connection during TLS inspection/security checks.
- Proxy path is unstable for long-lived SSL mail sessions.
- Provider-specific filtering for IMAP/SMTP traffic.

This means the proxy credentials are probably valid, but the provider session is not usable.

### `proxy_tcp=OK` then `SMTPServerDisconnected`

The proxy tunnel opened, but the SMTP server closed before or during the banner/protocol stage.

Likely causes:

- Provider blocked that proxy IP before SMTP dialogue.
- Provider rejected the connection based on reputation or geo.
- Proxy can connect to the host but cannot sustain the SMTP session.

### `STARTTLS` Fails

The server accepted the plain SMTP connection but TLS upgrade failed.

Likely causes:

- Proxy interferes with STARTTLS.
- Provider closed the session during TLS negotiation.
- TLS/SNI/certificate negotiation failed.

### `login=FAIL`

The network path worked, but authentication failed.

Likely causes:

- Wrong account password.
- App password required.
- IMAP/SMTP disabled in provider account settings.
- Account security challenge triggered by new IP/proxy location.

## Findings From Latest Proxy Trace

The latest `group_a.xlsx` proxy diagnostics showed:

```text
Gmail SMTP:
proxy_tcp OK
connect_banner OK
EHLO OK
STARTTLS OK
EHLO after TLS OK
login OK

Mail.ru SMTP:
proxy_tcp OK
SSL connect OK
EHLO OK
login OK

GMX SMTP:
proxy_tcp OK
SMTPServerDisconnected before banner/session completed

Yahoo SMTP:
proxy_tcp OK
SSLEOFError during SSL handshake

AOL SMTP:
proxy_tcp OK
SSLEOFError during SSL handshake

GMX/Yahoo/Mail.ru/AOL IMAP:
proxy_tcp OK
SSLEOFError before IMAP login
```

Conclusion:

The tested proxies are not simply invalid. They can open TCP tunnels. Gmail SMTP and Mail.ru SMTP work through the sheet proxies. The failures happen after the proxy tunnel opens, during TLS/SSL or provider protocol startup. That points to provider/proxy-path rejection or provider-side session termination, not a basic username/password proxy problem.

## Client-Friendly Explanation

Use this wording when explaining the issue:

```text
The proxy credentials are valid because the proxy can open TCP tunnels to the mail servers.
The failures happen after the connection reaches the provider, during SSL/TLS or mail protocol startup.

That means this is not a simple bad username/password issue. Gmail SMTP and Mail.ru SMTP work through the sheet proxies, but GMX/Yahoo/AOL and several IMAP paths are closed by the provider or the proxy path after the tunnel opens.

So the proxy supports some email traffic, but not all providers/protocols reliably.
```

