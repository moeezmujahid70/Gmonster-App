# Operation Error Experience Design

## Goal

Every user-triggered Gmonster operation explains a failure in plain language,
states the safe next action, and includes a stable reference code for support.
Raw protocol, proxy, server, and traceback details remain in application logs
only.

## Scope

The first release covers sign-in and sign-up, campaign sending, test email,
MailGenius, forwarding, reply sending, follow-up sending, inbox download, and
inbox deletion. Background errors are presented only when they affect the
result of an operation the user started.

## Shared Error Catalog

`user_messages.py` remains the pure, dependency-free catalog. It exposes a
single classifier:

```python
def operation_message(operation: str, error: Optional[Exception] = None, *, rejected: bool = False) -> UserMessage:
    ...
```

`operation` is one of `login`, `signup`, `smtp`, `forward`, `reply`,
`campaign`, `followup`, `imap_download`, `imap_delete`, or `mailgenius`.
The function classifies known exception types and safe response codes into a
`UserMessage(code, title, body)`. It never returns an exception message,
email address, password, token, proxy value, or response body.

Required categories are:

| Reference | Title | Action |
|---|---|---|
| `AUTH_INVALID` | Account could not sign in | Check the email and password; use an app password if the provider requires one. |
| `CONNECTION_FAILED` | Could not reach the service | Check the internet connection and proxy settings, then retry. |
| `CONNECTION_TIMEOUT` | The service took too long to respond | Wait briefly and retry. |
| `RECIPIENT_REJECTED` | Recipient address was rejected | Check the address and retry. |
| `PROVIDER_BLOCKED` | Mail provider paused this sender | Check the mailbox for a provider notice, then retry later. |
| `INPUT_INVALID` | Check the information entered | Correct the highlighted field and retry. |
| `SERVICE_UNAVAILABLE` | Gmonster service is unavailable | Retry shortly; contact support with the reference if it continues. |
| `OPERATION_FAILED` | Operation could not be completed | Retry after checking the account and connection. |

Existing MailGenius and unsubscribe references remain stable so support and
current tests do not lose their identifiers.

## Presentation Rules

Single-account dialogs—sign-in, sign-up, test email, MailGenius, forward, and
reply—show the message immediately in their status area. The status reads:

```
<title>\n<body>\n\nError reference: <code>
```

Multi-account operations—campaigns, follow-ups, inbox download, and inbox
delete—collect deduplicated `UserMessage` instances. They show one final
summary when the operation ends, including successful and failed account/item
counts. They never show one dialog per failed recipient or account.

Preflight validation failures prevent work from starting and show the same
message in an `alert()` dialog. Raw exception strings must not reach UI labels
or alerts.

## Threading and Data Flow

Worker threads classify the caught exception at its boundary and append only
the immutable `UserMessage` to the operation-specific collection in `var.py`.
They continue to log the traceback with the message code. UI mutations remain
on the Qt thread: workers use the existing `var.command_q` mechanism to invoke
the final alert/status update, and dialogs use their existing Qt signals.

`user_messages.py` does not import PyQt, `var`, SMTP, IMAP, or dialogs. This
keeps classification directly unit-testable and prevents worker/UI coupling.

## Per-Flow Integration

- `dialog.py`: validate blank credentials locally; translate login and sign-up
  HTTP, timeout, network, and rejected-credential failures before setting the
  status label.
- `smtp.py`: preserve `TestMail.failure_message`; add the same result property
  to `ForwardMail` and `ReplyMail`; classify campaign and follow-up worker
  failures before their final summaries.
- `send_dialog.py` and `campaign_reply.py`: display the returned messages
  inline instead of generic failures.
- `imap.py`: collect download/delete errors by category and publish a single
  completion summary through the existing UI queue.
- `main.py`: replace raw `Error at send_campaign: <exception>` alerts with a
  shared preflight message and keep the technical exception in logs.

## Security and Copy Constraints

- Never display or log a password, app password, bearer token, proxy
  credential, full API response, or recipient list in a user message.
- Error titles identify what failed; bodies state the next action in plain
  language.
- References are short, stable uppercase codes and are safe to provide to
  support.
- Success and partial-success outcomes distinguish what was sent from what
  failed; MailGenius must never imply the test email failed when only scoring
  failed.

## Verification

Unit tests cover classification for each category and verify no raw exception
text leaks into display strings. Focused integration tests verify that test,
forward, reply, campaign, follow-up, inbox, and login routes use the catalog.
Manual smoke checks exercise an invalid password, invalid recipient, an SMTP
connection failure, a campaign with one failed sender, a failed follow-up, and
an unavailable inbox account.
