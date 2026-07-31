# MailGenius Test Spam Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user optionally run a MailGenius deliverability audit from the Campaign tab's existing Test popup and view its progress and result in that same popup.

**Architecture:** Keep MailGenius HTTP and response normalization in a new dependency-light `mailgenius.py` module. Extend the existing `Send` dialog only when it is opened for a campaign test, and pass the generated MailGenius audit address to `TestMail` as a second SMTP envelope recipient. The dialog's background worker starts an audit, sends the normal test and audit copy, polls the resulting slug, and updates the UI through Qt signals.

**Tech Stack:** Python 3.10, PyQt5, `requests`, existing `threading.Thread`, SMTP through `TestMail`, JSON configuration, standard-library `unittest`.

## Global Constraints

- Preserve current behavior for a test send when the MailGenius toggle is off.
- Do not change campaign-send or inbox-forward behavior.
- Do not log, show, or commit RapidAPI keys, mail passwords, or full email bodies.
- Use `GET https://{rapidapi_host}/external/api/email-audit` to obtain `test_email` and `slug`.
- Use `GET https://{rapidapi_host}/external/api/email-result/{slug}` to retrieve the asynchronous audit result.
- Authenticate with `x-rapidapi-key` and `x-rapidapi-host`; do not add a separate bearer-token setting unless the audit endpoint demonstrably requires one.
- Use the existing runtime configuration file at `data/gmonster_config/config.json`; keep the example config free of secrets.
- Edit `ui/email_input.ui` first, then regenerate `email_input_gui.py` with `pyuic5`.
- Continue using the application’s `Thread` plus Qt-signal pattern so HTTP polling never blocks the PyQt event loop.

---

## File Structure

- `mailgenius.py` — MailGenius request, validation, polling, and response-normalization boundary; contains no PyQt or SMTP imports.
- `tests/test_mailgenius.py` — standard-library unit tests for endpoint construction, audit parsing, result state parsing, and timeout behavior.
- `var.py` — default/load `mailgenius` configuration into shared runtime state.
- `utils.py` — preserve `var.mailgenius` whenever the app writes configuration.
- `smtp.py` — allow `TestMail` to send the same MIME message to the normal recipient and an optional MailGenius audit address.
- `send_dialog.py` — test-only checkbox behavior, orchestration, and Qt signal-driven state/result updates.
- `ui/email_input.ui` — canonical popup layout containing the toggle and initially hidden result panel.
- `email_input_gui.py` — generated wrapper for the updated `.ui` file.

### Task 1: Add a testable MailGenius client

**Files:**
- Create: `mailgenius.py`
- Create: `tests/__init__.py`
- Create: `tests/test_mailgenius.py`

**Interfaces:**
- Consumes: `dict` containing `rapidapi_key`, `rapidapi_host`, and optional `enabled`.
- Produces: `MailGeniusClient`, `MailGeniusAudit`, `MailGeniusResult`, and `MailGeniusError` for later dialog code.

- [ ] **Step 1: Write failing unit tests for the external contract**

```python
# tests/test_mailgenius.py
import unittest

from mailgenius import MailGeniusClient, MailGeniusError


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers, timeout):
        self.calls.append((url, headers, timeout))
        return self.responses.pop(0)


class MailGeniusClientTests(unittest.TestCase):
    def test_start_audit_returns_slug_and_test_address(self):
        session = FakeSession([FakeResponse({"slug": "audit-1", "test_email": "audit@example.test"})])
        client = MailGeniusClient({"rapidapi_key": "key", "rapidapi_host": "host.test"}, session=session)

        audit = client.start_audit()

        self.assertEqual(audit.slug, "audit-1")
        self.assertEqual(audit.test_email, "audit@example.test")
        self.assertEqual(session.calls[0][0], "https://host.test/external/api/email-audit")
        self.assertEqual(session.calls[0][1]["x-rapidapi-host"], "host.test")

    def test_start_audit_rejects_missing_required_response_fields(self):
        session = FakeSession([FakeResponse({"slug": "audit-1"})])
        client = MailGeniusClient({"rapidapi_key": "key", "rapidapi_host": "host.test"}, session=session)

        with self.assertRaises(MailGeniusError):
            client.start_audit()

    def test_get_result_marks_processing_status_as_pending(self):
        session = FakeSession([FakeResponse({"slug": "audit-1", "status": "pending"})])
        client = MailGeniusClient({"rapidapi_key": "key", "rapidapi_host": "host.test"}, session=session)

        result = client.get_result("audit-1")

        self.assertTrue(result.pending)
        self.assertEqual(result.status, "pending")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_mailgenius -v`

Expected: FAIL because `mailgenius` does not exist.

- [ ] **Step 3: Implement the small HTTP client and normalized models**

```python
# mailgenius.py
from dataclasses import dataclass, field
from typing import Any

import requests


class MailGeniusError(Exception):
    pass


@dataclass(frozen=True)
class MailGeniusAudit:
    slug: str
    test_email: str


@dataclass(frozen=True)
class MailGeniusResult:
    status: str
    pending: bool
    data: dict[str, Any] = field(default_factory=dict)


class MailGeniusClient:
    def __init__(self, config, session=requests, timeout=(5, 20)):
        self.key = str(config.get("rapidapi_key", "")).strip()
        self.host = str(config.get("rapidapi_host", "")).strip()
        self.session = session
        self.timeout = timeout
        if not self.key or not self.host:
            raise MailGeniusError("MailGenius is not configured.")

    def _get(self, path):
        response = self.session.get(
            f"https://{self.host}{path}",
            headers={"x-rapidapi-key": self.key, "x-rapidapi-host": self.host},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise MailGeniusError(f"MailGenius request failed ({response.status_code}).")
        try:
            return response.json()
        except ValueError as exc:
            raise MailGeniusError("MailGenius returned an invalid response.") from exc

    def start_audit(self):
        data = self._get("/external/api/email-audit")
        slug, test_email = data.get("slug"), data.get("test_email")
        if not isinstance(slug, str) or not isinstance(test_email, str):
            raise MailGeniusError("MailGenius did not return an audit address.")
        return MailGeniusAudit(slug=slug, test_email=test_email)

    def get_result(self, slug):
        data = self._get(f"/external/api/email-result/{slug}")
        status = str(data.get("status", "unknown")).lower()
        return MailGeniusResult(status=status, pending=status in {"pending", "processing", "queued"}, data=data)
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `python -m unittest tests.test_mailgenius -v`

Expected: PASS.

- [ ] **Step 5: Commit the independently testable client**

```bash
git add mailgenius.py tests/__init__.py tests/test_mailgenius.py
git commit -m "feat: add MailGenius API client"
```

### Task 2: Make the MailGenius configuration survive app saves

**Files:**
- Modify: `var.py:248-395`
- Modify: `utils.py:76-153`
- Modify: `config.example.json`
- Test: `tests/test_mailgenius.py`

**Interfaces:**
- Consumes: `config["mailgenius"]`.
- Produces: `var.mailgenius`, a dictionary with `enabled`, `rapidapi_key`, and `rapidapi_host`.

- [ ] **Step 1: Add a failing persistence test**

```python
def test_config_payload_preserves_mailgenius_settings(self):
    import var
    from utils import get_config_json

    previous = var.mailgenius
    self.addCleanup(setattr, var, "mailgenius", previous)
    var.mailgenius = {"enabled": False, "rapidapi_key": "key", "rapidapi_host": "host.test"}

    self.assertEqual(get_config_json()["config"]["mailgenius"], var.mailgenius)
```

- [ ] **Step 2: Run the focused test before changing runtime configuration**

Run: `python -m unittest tests.test_mailgenius -v`

Expected: FAIL with a missing `mailgenius` key in `get_config_json()`.

- [ ] **Step 3: Add a default and load/save the same dictionary**

```python
# var.py, alongside other configuration defaults
mailgenius = {"enabled": False, "rapidapi_key": "", "rapidapi_host": ""}

# var.py, after config = data["config"]
if not isinstance(config.get("mailgenius"), dict):
    config["mailgenius"] = mailgenius.copy()
else:
    mailgenius.update(config["mailgenius"])
config["mailgenius"] = mailgenius

# utils.py, inside both `update_config_json()` and `get_config_json()` config dictionaries
"mailgenius": var.mailgenius,
```

Keep `config.example.json` identical except for an empty `rapidapi_key` and the real RapidAPI host. Do not modify an existing user key while editing the example.

- [ ] **Step 4: Run configuration and client tests**

Run: `python -m unittest tests.test_mailgenius -v`

Expected: PASS.

- [ ] **Step 5: Commit the configuration persistence change**

```bash
git add var.py utils.py config.example.json tests/test_mailgenius.py
git commit -m "feat: preserve MailGenius configuration"
```

### Task 3: Let one test message reach MailGenius and the normal recipient

**Files:**
- Modify: `smtp.py:85-207`
- Test: `tests/test_mailgenius.py`

**Interfaces:**
- Consumes: `TestMail(send_to: str, audit_recipient: str | None = None)`.
- Produces: one MIME message, transmitted to `[send_to]` or `[send_to, audit_recipient]`; the visible `To` header remains the user-entered test recipient.

- [ ] **Step 1: Write a failing recipient-list test**

```python
def test_test_mail_recipients_include_audit_address_only_when_present():
    from smtp import TestMail

    self.assertEqual(TestMail.recipient_list("user@example.com", None), ["user@example.com"])
    self.assertEqual(
        TestMail.recipient_list("user@example.com", "audit@example.test"),
        ["user@example.com", "audit@example.test"],
    )
```

- [ ] **Step 2: Run the test to verify the helper is missing**

Run: `python -m unittest tests.test_mailgenius.MailGeniusClientTests.test_test_mail_recipients_include_audit_address_only_when_present -v`

Expected: FAIL because `TestMail.recipient_list` is not defined.

- [ ] **Step 3: Add the recipient helper and use it for SMTP delivery**

```python
# smtp.py, inside TestMail
@staticmethod
def recipient_list(send_to, audit_recipient=None):
    return [address for address in [send_to, audit_recipient] if address]

# smtp.py, in TestMail.send(), keep msg["To"] = self.send_to
server.sendmail(self.user, self.recipient_list(self.send_to, self.audit_recipient), msg.as_string())
```

Set `self.audit_recipient` from the new optional constructor argument. Keep the message headers, template substitutions, attachments, sender selection, and proxy path unchanged.

- [ ] **Step 4: Run the recipient test and existing import smoke test**

Run: `python -m unittest tests.test_mailgenius -v && python -m py_compile smtp.py`

Expected: PASS with no syntax errors.

- [ ] **Step 5: Commit the SMTP-only change**

```bash
git add smtp.py tests/test_mailgenius.py
git commit -m "feat: send test copies to MailGenius"
```

### Task 4: Add the test-only toggle and expandable results panel

**Files:**
- Modify: `ui/email_input.ui`
- Regenerate: `email_input_gui.py`
- Modify: `send_dialog.py:41-97`

**Interfaces:**
- Consumes: `Send(dialog, parent="test")`.
- Produces: `checkBox_mailgenius`, `frame_mailgenius_results`, `label_mailgenius_state`, and `formLayout_mailgenius_results`.

- [ ] **Step 1: Add a UI construction smoke test before editing the dialog**

```python
def test_test_dialog_exposes_mailgenius_controls():
    from PyQt5.QtWidgets import QApplication, QDialog
    from send_dialog import Send

    app = QApplication.instance() or QApplication([])
    dialog = QDialog()
    ui = Send(dialog, parent="test")

    self.assertEqual(ui.checkBox_mailgenius.text(), "Also test spam score with MailGenius")
    self.assertFalse(ui.frame_mailgenius_results.isVisible())
```

- [ ] **Step 2: Run the UI test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m unittest tests.test_mailgenius.MailGeniusClientTests.test_test_dialog_exposes_mailgenius_controls -v`

Expected: FAIL because the new controls do not exist.

- [ ] **Step 3: Update the `.ui` source and regenerate its Python wrapper**

Add these controls below the email field and above the existing progress/status area:

```xml
<widget class="QCheckBox" name="checkBox_mailgenius">
 <property name="text"><string>Also test spam score with MailGenius</string></property>
</widget>
<widget class="QFrame" name="frame_mailgenius_results">
 <property name="visible"><bool>false</bool></property>
 <layout class="QVBoxLayout" name="verticalLayout_mailgenius">
  <item><widget class="QLabel" name="label_mailgenius_state"/></item>
  <item><layout class="QFormLayout" name="formLayout_mailgenius_results"/></item>
 </layout>
</widget>
```

Use the app’s existing Statistics-card colors for the frame: pale blue background, rounded border, compact bold labels. Then run:

```bash
pyuic5 ui/email_input.ui -o email_input_gui.py
```

In `Send.__init__`, hide both controls for `parent="forward"`. For `parent="test"`, enable the checkbox only when both configured RapidAPI values are non-empty; otherwise keep it disabled and give it the tooltip `MailGenius is not configured.` Connect its state change to a method that expands/collapses the result frame and calls `self.dialog.adjustSize()`.

- [ ] **Step 4: Run the offscreen UI test**

Run: `QT_QPA_PLATFORM=offscreen python -m unittest tests.test_mailgenius -v`

Expected: PASS.

- [ ] **Step 5: Commit the dialog layout and behavior**

```bash
git add ui/email_input.ui email_input_gui.py send_dialog.py tests/test_mailgenius.py
git commit -m "feat: add MailGenius controls to test dialog"
```

### Task 5: Orchestrate audit, send, poll, and same-popup results

**Files:**
- Modify: `mailgenius.py`
- Modify: `send_dialog.py:37-97`
- Modify: `tests/test_mailgenius.py`

**Interfaces:**
- Consumes: `MailGeniusClient.start_audit()` and `MailGeniusClient.get_result(slug)`.
- Produces: `Send.test()` states: `Sending test email…`, `Email sent — analyzing deliverability…`, `Spam score ready`, or an actionable partial-failure state.

- [ ] **Step 1: Write failing tests for state classification and polling**

```python
def test_poll_returns_first_non_pending_result():
    session = FakeSession([
        FakeResponse({"slug": "audit-1", "status": "pending"}),
        FakeResponse({"slug": "audit-1", "status": "complete", "spam_score": 8}),
    ])
    client = MailGeniusClient({"rapidapi_key": "key", "rapidapi_host": "host.test"}, session=session)

    result = client.wait_for_result("audit-1", attempts=2, interval_seconds=0, sleep=lambda _: None)

    self.assertFalse(result.pending)
    self.assertEqual(result.data["spam_score"], 8)

def test_poll_raises_clear_timeout_error():
    session = FakeSession([FakeResponse({"status": "pending"})])
    client = MailGeniusClient({"rapidapi_key": "key", "rapidapi_host": "host.test"}, session=session)

    with self.assertRaisesRegex(MailGeniusError, "timed out"):
        client.wait_for_result("audit-1", attempts=1, interval_seconds=0, sleep=lambda _: None)
```

- [ ] **Step 2: Run the polling tests to verify they fail**

Run: `python -m unittest tests.test_mailgenius -v`

Expected: FAIL because `wait_for_result` is not defined.

- [ ] **Step 3: Implement bounded polling and dialog state updates**

```python
# mailgenius.py (also add `import time` at the module top)
def wait_for_result(self, slug, attempts=20, interval_seconds=3, sleep=time.sleep):
    for _ in range(attempts):
        result = self.get_result(slug)
        if not result.pending:
            return result
        sleep(interval_seconds)
    raise MailGeniusError("MailGenius analysis timed out. Please try again.")
```

Extend `Communicate` with a signal carrying a state string and result mapping. In `Send.test()`:

1. Validate the entered email before starting work.
2. If the checkbox is off, invoke the existing `TestMail(send_to).send()` path unchanged.
3. If it is on, create `MailGeniusClient(var.mailgenius)`, call `start_audit()`, then call `TestMail(send_to, audit_recipient=audit.test_email).send()`.
4. Only after SMTP success, call `wait_for_result(audit.slug)`.
5. Render the returned response as labels in `formLayout_mailgenius_results`: prefer `spam_score`, `score`, `grade`, `spf`, `dkim`, `dmarc`, `recommendations`, and `warnings` when those keys exist; additionally render all remaining primitive result fields with title-cased labels. This shows the provider’s actual response without inventing field names.
6. On a MailGenius failure after SMTP success, retain `Sent` in the primary status and show the safe MailGenius error in the expanded panel with a `Retry score check` button that reuses the saved slug and does not resend email.

Disable Send while any state is in progress and re-enable it in every terminal state.

- [ ] **Step 4: Run all targeted tests and syntax checks**

Run: `QT_QPA_PLATFORM=offscreen python -m unittest tests.test_mailgenius -v && python -m py_compile mailgenius.py send_dialog.py smtp.py var.py utils.py`

Expected: PASS.

- [ ] **Step 5: Commit orchestration and result rendering**

```bash
git add mailgenius.py send_dialog.py tests/test_mailgenius.py
git commit -m "feat: show MailGenius test results"
```

### Task 6: Verify the full desktop workflow against the live API

**Files:**
- Modify: none unless a confirmed API response shape requires an additive renderer mapping.
- Test: live manual verification using `data/gmonster_config/config.json`.

**Interfaces:**
- Consumes: configured RapidAPI key/host, one valid campaign sender account, at least one target row, and a recipient address controlled by the tester.
- Produces: a live MailGenius result rendered in the existing Test popup.

- [ ] **Step 1: Verify configuration safely**

Run:

```bash
jq -e '.config.mailgenius.rapidapi_key | type == "string" and length > 0' data/gmonster_config/config.json >/dev/null
jq -e '.config.mailgenius.rapidapi_host == "mailgenius-email-deliverability-api1.p.rapidapi.com"' data/gmonster_config/config.json >/dev/null
```

Expected: both commands exit with status 0; do not print the key.

- [ ] **Step 2: Manually verify the unchanged path**

Open Campaign → Test, leave the MailGenius switch off, send to the controlled recipient, and confirm the popup still transitions from `Sending…` to `Sent` without showing a results frame.

- [ ] **Step 3: Manually verify the MailGenius path**

Open Campaign → Test, enable `Also test spam score with MailGenius`, send to the controlled recipient, and confirm:

```text
Creating MailGenius audit…
Sending test email…
Email sent — analyzing deliverability…
Spam score ready
```

Confirm the controlled recipient receives one test email, the result frame expands in the same popup, and it shows the returned status plus response fields. Confirm no RapidAPI key appears in the popup or logs.

- [ ] **Step 4: Manually verify a partial failure**

Temporarily replace `rapidapi_key` in the local runtime config with an invalid value, reopen the app, run the switched-on test, and confirm the popup says MailGenius could not start while it does not attempt SMTP delivery. Restore the real key immediately after the check.

- [ ] **Step 5: Commit any confirmed response-field mapping only**

```bash
git add mailgenius.py send_dialog.py tests/test_mailgenius.py
git commit -m "fix: map MailGenius audit response fields"
```

## Plan Self-Review

- Spec coverage: Tasks 1-2 cover API access and persistent configuration; Task 3 preserves the current recipient test while delivering a copy to MailGenius; Task 4 provides the test-only toggle and expandable same-popup panel; Task 5 implements asynchronous states, polling, retries, and safe errors; Task 6 verifies off/on and partial-failure behavior live.
- Placeholder scan: no `TODO`, `TBD`, or undefined future implementation references remain. The unknown provider response field names are handled explicitly by preserving and rendering primitive fields instead of assuming a proprietary schema.
- Type consistency: `MailGeniusClient` produces `MailGeniusAudit` and `MailGeniusResult`; `Send.test()` consumes these and passes only `audit.test_email` to `TestMail`; the retry uses `audit.slug` through the same client.
