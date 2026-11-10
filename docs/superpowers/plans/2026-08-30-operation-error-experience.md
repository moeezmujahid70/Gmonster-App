# Operation Error Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every user-triggered Gmonster operation a safe, actionable error explanation instead of raw exceptions or log-only failures.

**Architecture:** Keep `user_messages.py` pure and extend it into the single operation-error catalog. Workers classify errors at their boundary, retain tracebacks only in logs, and return or collect immutable `UserMessage` values; existing dialog signals and `var.command_q` then present one appropriate message on the Qt thread.

**Tech Stack:** Python 3.10, PyQt5, `threading.Thread`, existing `var.command_q`, `unittest`, `smtplib`, `imaplib`, `requests`.

**Spec:** `docs/superpowers/specs/2026-08-30-operation-error-experience-design.md`

## Global Constraints

- Python 3.10 and existing PyQt signal/queue threading model only; do not introduce a second event system.
- User-visible copy must not include passwords, tokens, proxy credentials, recipient lists, raw response bodies, or exception text.
- Every failure shown to a user contains a stable uppercase error reference.
- One-account dialogs explain errors immediately; bulk/background operations show one deduplicated final summary.
- Preserve existing MailGenius and unsubscribe reference codes.

---

### Task 1: Complete the shared error catalog

**Files:**
- Modify: `user_messages.py`
- Modify: `tests/test_user_messages.py`

**Interfaces:**
- Produces: `operation_message(operation: str, error: Optional[Exception] = None, *, rejected: bool = False) -> UserMessage`
- Produces: `display_text(message: UserMessage) -> str`
- Preserves: `smtp_message`, `preparation_message`, `mailgenius_message`, `followup_message`

- [ ] **Step 1: Write failing catalog tests**

```python
from user_messages import display_text, operation_message

def test_login_authentication_error_never_exposes_server_text(self):
    message = operation_message("login", smtplib.SMTPAuthenticationError(535, b"invalid credentials"))
    self.assertEqual(message.code, "AUTH_INVALID")
    self.assertIn("app password", message.body.lower())
    self.assertNotIn("invalid credentials", display_text(message).lower())

def test_imap_timeout_has_a_safe_retry_message(self):
    message = operation_message("imap_download", TimeoutError("host=secret"))
    self.assertEqual(message.code, "CONNECTION_TIMEOUT")
    self.assertIn("retry", message.body.lower())
    self.assertNotIn("host=secret", display_text(message))
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `python3 -m unittest tests.test_user_messages -v`

Expected: failure because `operation_message` and `display_text` do not exist.

- [ ] **Step 3: Implement the classifier and display formatter**

```python
def display_text(message: UserMessage) -> str:
    return f"{message.body}\n\nError reference: {message.code}"

def operation_message(operation, error=None, *, rejected=False):
    if rejected or isinstance(error, smtplib.SMTPRecipientsRefused):
        return UserMessage("RECIPIENT_REJECTED", "Recipient address was rejected", "The mail provider rejected the recipient address. Check the address and try again.")
    if isinstance(error, (smtplib.SMTPAuthenticationError, imaplib.IMAP4.error)):
        return UserMessage("AUTH_INVALID", "Account could not sign in", "Check the email and password. Some providers require an app password.")
    if isinstance(error, TimeoutError):
        return UserMessage("CONNECTION_TIMEOUT", "The service took too long to respond", "Wait briefly and retry.")
    if isinstance(error, (socket.gaierror, ConnectionError, smtplib.SMTPConnectError)):
        return UserMessage("CONNECTION_FAILED", "Could not reach the service", "Check your internet connection and proxy settings, then retry.")
    return UserMessage("OPERATION_FAILED", "Operation could not be completed", "Check the account and connection, then retry.")
```

Import `imaplib` and `requests` only if their exception classes are used directly. Map HTTP 401/403 to `AUTH_INVALID`, 408/504 to `CONNECTION_TIMEOUT`, and 429/5xx to `SERVICE_UNAVAILABLE` without retaining the response text.

- [ ] **Step 4: Run catalog tests and existing focused message tests**

Run: `python3 -m unittest tests.test_user_messages -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add user_messages.py tests/test_user_messages.py
git commit -m "feat: centralize safe operation error messages"
```

### Task 2: Use shared messages in login, forward, reply, and test dialogs

**Files:**
- Modify: `dialog.py`
- Modify: `smtp.py`
- Modify: `send_dialog.py`
- Modify: `campaign_reply.py`
- Create: `tests/test_operation_error_wiring.py`

**Interfaces:**
- Consumes: `operation_message`, `display_text`, `UserMessage` from Task 1.
- Produces: `ForwardMail.failure_message: UserMessage | None` and `ReplyMail.failure_message: UserMessage | None`.

- [ ] **Step 1: Write failing wiring tests**

```python
def test_forward_and_reply_preserve_a_user_message_for_the_dialog(self):
    source = pathlib.Path("smtp.py").read_text(encoding="utf-8")
    self.assertIn("self.failure_message = operation_message(\"forward\", e)", source)
    self.assertIn("self.failure_message = operation_message(\"reply\", e)", source)

def test_login_never_sets_status_from_a_raw_exception(self):
    source = pathlib.Path("dialog.py").read_text(encoding="utf-8")
    self.assertIn("operation_message(\"login\"", source)
    self.assertNotIn('status = "Couldn\'t connect - {}'.format(e)', source)
```

- [ ] **Step 2: Run the wiring tests and verify failure**

Run: `python3 -m unittest tests.test_operation_error_wiring -v`

Expected: failure because forwarding, reply, and login do not use the shared classifier.

- [ ] **Step 3: Classify errors at their source and display them inline**

In `ForwardMail.send()` and `ReplyMail.send()`, initialize `self.failure_message = None`; on a caught exception assign `operation_message("forward", e)` or `operation_message("reply", e)` before logging. In `Send.forward()` and `Reply.reply()`, render `display_text(instance.failure_message or operation_message(...))` in the existing status label.

In `Sign_in.validate()`, reject blank email and password before starting a thread with `INPUT_INVALID`. In `make_sign_up_requests()`, replace raw response/error strings with a safe login/signup message, except preserve the literal `Success` success condition. Remove password `print()` calls from sign-up validation and remove the hard-coded sign-in password.

- [ ] **Step 4: Run focused tests and syntax checks**

Run: `python3 -m unittest tests.test_user_messages tests.test_operation_error_wiring -v && python3 -m compileall -q dialog.py smtp.py send_dialog.py campaign_reply.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dialog.py smtp.py send_dialog.py campaign_reply.py tests/test_operation_error_wiring.py
git commit -m "feat: explain login and single-send failures"
```

### Task 3: Normalize campaign and follow-up summaries

**Files:**
- Modify: `var.py`
- Modify: `smtp.py`
- Modify: `main.py`
- Modify: `tests/test_campaign_unsubscribe_preparation.py`
- Create: `tests/test_campaign_error_summary.py`

**Interfaces:**
- Consumes: `operation_message`, `display_text`.
- Produces: `var.campaign_user_messages` and `var.followup_user_messages` containing `UserMessage` values only.

- [ ] **Step 1: Write failing aggregation tests**

```python
def test_campaign_summary_deduplicates_by_reference(self):
    messages = [
        UserMessage("AUTH_INVALID", "Account could not sign in", "Check the email and password."),
        UserMessage("AUTH_INVALID", "Account could not sign in", "Check the email and password."),
    ]
    self.assertEqual(summary_text(messages).count("AUTH_INVALID"), 1)

def test_summary_has_no_raw_exception_text(self):
    text = summary_text([operation_message("campaign", RuntimeError("proxy_password=secret"))])
    self.assertNotIn("secret", text)
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `python3 -m unittest tests.test_campaign_error_summary -v`

Expected: failure because `summary_text` does not exist.

- [ ] **Step 3: Add a pure summary formatter and wire bulk workers**

Add `summary_text(messages: Iterable[UserMessage]) -> str` to `user_messages.py`; deduplicate by `code` and join `title`, `body`, and `Error reference` lines. Reset both global lists at the start of their corresponding operation. In the `Smtp.run` and `FollowUpSend.run` exception handlers, append `operation_message("campaign", e)` or `operation_message("followup", e)`. Replace the raw alert in `MyMainClass.send_campaign()` with `display_text(operation_message("campaign", e))`.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_user_messages tests.test_campaign_unsubscribe_preparation tests.test_followup_unsubscribe_preparation tests.test_campaign_error_summary -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add user_messages.py var.py smtp.py main.py tests/test_campaign_error_summary.py tests/test_campaign_unsubscribe_preparation.py
git commit -m "feat: summarize campaign and follow-up failures"
```

### Task 4: Surface inbox download and delete failures safely

**Files:**
- Modify: `var.py`
- Modify: `imap.py`
- Modify: `main.py`
- Create: `tests/test_inbox_error_summary.py`

**Interfaces:**
- Consumes: `operation_message`, `summary_text`.
- Produces: `var.inbox_user_messages: list[UserMessage]`.

- [ ] **Step 1: Write failing inbox-summary tests**

```python
def test_download_error_uses_the_shared_imap_category(self):
    source = pathlib.Path("imap.py").read_text(encoding="utf-8")
    self.assertIn('operation_message("imap_download", e)', source)
    self.assertIn("var.inbox_user_messages.append", source)

def test_inbox_summary_uses_one_alert_after_workers_finish(self):
    source = pathlib.Path("imap.py").read_text(encoding="utf-8")
    self.assertIn("summary_text(var.inbox_user_messages)", source)
```

- [ ] **Step 2: Run the test and verify failure**

Run: `python3 -m unittest tests.test_inbox_error_summary -v`

Expected: failure because inbox workers only log their exceptions.

- [ ] **Step 3: Collect and present the final inbox result**

Initialize `var.inbox_user_messages = []` before starting download/delete worker threads. Classify exceptions in `ImapDownload.run`, `ImapDeleteEmail.run`, and the thread-start boundary. Once workers finish, use `var.command_q.put` to show one `alert()` containing completed counts and `summary_text(var.inbox_user_messages)` when failures exist. Keep the operation successful-but-partial when other accounts completed.

- [ ] **Step 4: Run focused tests and syntax checks**

Run: `python3 -m unittest tests.test_user_messages tests.test_inbox_error_summary -v && python3 -m compileall -q imap.py main.py var.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add var.py imap.py main.py tests/test_inbox_error_summary.py
git commit -m "feat: explain inbox operation failures"
```

### Task 5: Verify user-visible failure flows

**Files:**
- Modify: `tests/test_user_messages.py`
- Modify: `tests/test_operation_error_wiring.py`
- Modify: `tests/test_campaign_error_summary.py`
- Modify: `tests/test_inbox_error_summary.py`

- [ ] **Step 1: Add no-secret regression cases**

```python
def test_all_display_messages_exclude_secret_like_exception_text(self):
    error = RuntimeError("password=abc proxy_pass=def token=ghi")
    for operation in ("login", "smtp", "forward", "reply", "campaign", "followup", "imap_download", "imap_delete"):
        self.assertNotIn("abc", display_text(operation_message(operation, error)))
        self.assertNotIn("def", display_text(operation_message(operation, error)))
        self.assertNotIn("ghi", display_text(operation_message(operation, error)))
```

- [ ] **Step 2: Run the full targeted suite**

Run: `python3 -m unittest tests.test_user_messages tests.test_operation_error_wiring tests.test_campaign_error_summary tests.test_inbox_error_summary tests.test_campaign_unsubscribe_preparation tests.test_followup_unsubscribe_preparation tests.test_mailgenius -v`

Expected: PASS.

- [ ] **Step 3: Perform a manual smoke check**

Verify in an off-network or safe test account setup that invalid login credentials, a rejected test recipient, and a campaign sender authentication failure each show a safe explanation and reference; verify the corresponding log retains the traceback under the same code.

- [ ] **Step 4: Commit**

```bash
git add tests
git commit -m "test: cover safe operation error explanations"
```
