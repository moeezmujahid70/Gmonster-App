# Proxy Mail Debug Log

- Generated: 2026-05-28T16:00:00
- Source sheet: `data/sheets/group_a.xlsx`
- Proxy type: `SOCKS5`
- Secrets: redacted
- Test type: login-only, no email send

## gmail
- Account: `78***@gmail.com`
- IMAP endpoint: `imap.gmail.com:993`
- SMTP endpoint: `smtp.gmail.com:587`

### IMAP Stages
- proxy_tcp: OK - connect_ok
- tls_and_greeting: OK - ok
- login: OK - ok
- select_inbox: OK - OK
- exception: FAIL - error: SELECT command error: BAD [b'Could not parse command']

### IMAP Details
```text
INBOX select response: [b'1231']
Exception traceback sanitized:
imaplib.IMAP4.error: SELECT command error: BAD [b'Could not parse command']

```

### SMTP Stages
- proxy_tcp: OK - connect_ok
- connect_banner: OK - connected
- ehlo_plain: OK - 250 b'smtp.gmail.com at your service, [<ipv6-redacted>]\nSIZE 35882577\n8BITMIME\nSTARTTLS\<token-redacted>\nPIPELINING\nCHUNKING\nSMTPUTF8'
- starttls: OK - 220 b'2.0.0 Ready to start TLS'
- ehlo_tls: OK - 250 b'smtp.gmail.com at your service, [<ipv6-redacted>]\nSIZE 35882577\n8BITMIME\nAUTH LOGIN PLAIN XOAUTH2 PLAIN-CLIENTTOKEN OAUTHBEARER XOAUTH\<token-redacted>\nPIPELINING\nCHUNKING\nSMTPUTF8'
- login: OK - ok

### SMTP Debug Trace
```text
<ipv6-redacted>.191973 send: 'ehlo <ip-redacted>.in-addr.arpa\r\n'
<ipv6-redacted>.261648 reply: b'250-smtp.gmail.com at your service, [<ipv6-redacted>]\r\n'
<ipv6-redacted>.261704 reply: b'250-SIZE 35882577\r\n'
<ipv6-redacted>.261715 reply: b'250-8BITMIME\r\n'
<ipv6-redacted>.261724 reply: b'250-STARTTLS\r\n'
<ipv6-redacted>.261732 reply: b'250-<token-redacted>\r\n'
<ipv6-redacted>.261744 reply: b'250-PIPELINING\r\n'
<ipv6-redacted>.261753 reply: b'250-CHUNKING\r\n'
<ipv6-redacted>.261760 reply: b'250 SMTPUTF8\r\n'
<ipv6-redacted>.261776 reply: retcode (250); Msg: b'smtp.gmail.com at your service, [<ipv6-redacted>]\nSIZE 35882577\n8BITMIME\nSTARTTLS\<token-redacted>\nPIPELINING\nCHUNKING\nSMTPUTF8'
<ipv6-redacted>.262355 send: 'STARTTLS\r\n'
<ipv6-redacted>.317272 reply: b'220 2.0.0 Ready to start TLS\r\n'
<ipv6-redacted>.317353 reply: retcode (220); Msg: b'2.0.0 Ready to start TLS'
<ipv6-redacted>.371479 send: 'ehlo <ip-redacted>.in-addr.arpa\r\n'
<ipv6-redacted>.457215 reply: b'250-smtp.gmail.com at your service, [<ipv6-redacted>]\r\n'
<ipv6-redacted>.457321 reply: b'250-SIZE 35882577\r\n'
<ipv6-redacted>.457340 reply: b'250-8BITMIME\r\n'
send: AUTH <redacted>
<ipv6-redacted>.457379 reply: b'250-<token-redacted>\r\n'
<ipv6-redacted>.457405 reply: b'250-PIPELINING\r\n'
<ipv6-redacted>.457419 reply: b'250-CHUNKING\r\n'
<ipv6-redacted>.457433 reply: b'250 SMTPUTF8\r\n'
send: AUTH <redacted>
send: AUTH <redacted>
<ipv6-redacted>.697268 reply: b'235 2.7.0 Accepted\r\n'
<ipv6-redacted>.697354 reply: retcode (235); Msg: b'2.7.0 Accepted'
<ipv6-redacted>.697387 send: 'quit\r\n'
<ipv6-redacted>.750461 reply: b'221 2.0.0 closing connection ffacd0b85a97d-<token-redacted>.26 - gsmtp\r\n'
<ipv6-redacted>.750551 reply: retcode (221); Msg: b'2.0.0 closing connection ffacd0b85a97d-<token-redacted>.26 - gsmtp'
```

## gmx
- Account: `cv***@gmx.com`
- IMAP endpoint: `imap.gmx.com:993`
- SMTP endpoint: `mail.gmx.com:587`

### IMAP Stages
- proxy_tcp: OK - connect_ok
- exception: FAIL - SSLEOFError: EOF occurred in violation of protocol (_ssl.c:997)

### IMAP Details
```text
Exception traceback sanitized:
ssl.SSLEOFError: EOF occurred in violation of protocol (_ssl.c:997)

```

### SMTP Stages
- proxy_tcp: OK - connect_ok
- exception: FAIL - SMTPServerDisconnected: Connection unexpectedly closed

## yahoo
- Account: `pe***@yahoo.com`
- IMAP endpoint: `imap.mail.yahoo.com:993`
- SMTP endpoint: `smtp.mail.yahoo.com:465`

### IMAP Stages
- proxy_tcp: OK - connect_ok
- exception: FAIL - SSLEOFError: EOF occurred in violation of protocol (_ssl.c:997)

### IMAP Details
```text
Exception traceback sanitized:
ssl.SSLEOFError: EOF occurred in violation of protocol (_ssl.c:997)

```

### SMTP Stages
- proxy_tcp: OK - connect_ok
- exception: FAIL - SSLEOFError: EOF occurred in violation of protocol (_ssl.c:997)

## mail.ru
- Account: `nu***@mail.ru`
- IMAP endpoint: `imap.mail.ru:993`
- SMTP endpoint: `smtp.mail.ru:465`

### IMAP Stages
- proxy_tcp: OK - connect_ok
- exception: FAIL - SSLEOFError: EOF occurred in violation of protocol (_ssl.c:997)

### IMAP Details
```text
Exception traceback sanitized:
ssl.SSLEOFError: EOF occurred in violation of protocol (_ssl.c:997)

```

### SMTP Stages
- proxy_tcp: OK - connect_ok
- ssl_connect_banner: OK - connected
- ehlo: OK - 250 b'smtp.mail.ru\nSIZE 73400320\n8BITMIME\nDSN\nSMTPUTF8\nAUTH PLAIN LOGIN XOAUTH2'
- login: OK - ok

### SMTP Debug Trace
```text
<ipv6-redacted>.500874 send: 'ehlo <ip-redacted>.in-addr.arpa\r\n'
<ipv6-redacted>.596691 reply: b'250-smtp.mail.ru\r\n'
<ipv6-redacted>.596737 reply: b'250-SIZE 73400320\r\n'
<ipv6-redacted>.596747 reply: b'250-8BITMIME\r\n'
<ipv6-redacted>.596755 reply: b'250-DSN\r\n'
<ipv6-redacted>.596763 reply: b'250-SMTPUTF8\r\n'
send: AUTH <redacted>
send: AUTH <redacted>
send: AUTH <redacted>
<ipv6-redacted>.745468 reply: b'235 Authentication succeeded\r\n'
send: AUTH <redacted>
<ipv6-redacted>.745589 send: 'quit\r\n'
<ipv6-redacted>.050321 reply: b'221 exim-smtp-5b85998476-twp2b closing connection\r\n'
<ipv6-redacted>.050479 reply: retcode (221); Msg: b'exim-smtp-5b85998476-twp2b closing connection'
```

## aol
- Account: `da***@aol.com`
- IMAP endpoint: `imap.aol.com:993`
- SMTP endpoint: `smtp.aol.com:465`

### IMAP Stages
- proxy_tcp: OK - connect_ok
- exception: FAIL - SSLEOFError: EOF occurred in violation of protocol (_ssl.c:997)

### IMAP Details
```text
Exception traceback sanitized:
ssl.SSLEOFError: EOF occurred in violation of protocol (_ssl.c:997)

```

### SMTP Stages
- proxy_tcp: OK - connect_ok
- exception: FAIL - SSLEOFError: EOF occurred in violation of protocol (_ssl.c:997)
