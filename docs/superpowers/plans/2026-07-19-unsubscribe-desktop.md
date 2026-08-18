# Unsubscribe Desktop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the server unsubscribe APIs into Gmonster so campaigns and follow-ups are prepared before sending, personalized footers are composed safely, and users can manage account-wide suppressions.

**Architecture:** A focused API client owns bearer-token capture, one-time refresh, setting operations, campaign preparation, and management calls. Pure preparation and email-composition modules keep network and MIME logic testable outside `main.py`. The existing SMTP orchestration prepares all sender-recipient assignments before any worker starts.

**Tech Stack:** Python 3.10, requests, pandas, PyQt5, Python email MIME, unittest.

## Global Constraints

- Desktop repository: `/Users/moeezmujahid/Projects/emailSaas/Gmonster`.
- Implement only after the server plan API contract passes staging verification.
- Use `var` for shared runtime state; do not introduce another configuration layer.
- Keep access tokens in memory only and never log them.
- Do not create a persistent local unsubscribe table or cache.
- Prepare recipients before every initial campaign and every follow-up run.
- Do not refresh suppression after an initial campaign begins.
- Every preparation batch must succeed before any SMTP worker starts.
- Batch at 1,000 recipients maximum and require one result per input reference.
- Suppression applies even when footer insertion is disabled.
- Add fixed wording to both HTML and plain-text MIME alternatives.
- Test sends receive no active unsubscribe link.
- Edit `ui/gui.ui`, then regenerate `gui.py`; do not edit generated UI code manually.

---

### Task 1: Capture and refresh subscriber bearer tokens

**Files:**
- Modify: `var.py:240-280`
- Modify: `dialog.py:217-267`
- Create: `gmonster_api.py`
- Create: `tests/test_gmonster_api.py`

**Interfaces:**
- Produces: `var.api_access_token: str`.
- Produces: `capture_access_token(response) -> bool`.
- Produces: `authenticated_request(method, path, *, json=None, timeout=None, session=requests) -> Response`.

- [ ] **Step 1: Write failing token-capture and one-retry tests**

```python
# tests/test_gmonster_api.py
import unittest
from unittest.mock import Mock, patch
import var
from gmonster_api import authenticated_request, capture_access_token


class GmonsterApiTest(unittest.TestCase):
    def setUp(self): var.api_access_token = ''

    def test_capture_access_token_keeps_it_in_memory(self):
        response = Mock(headers={'X-Gmonster-Access-Token': 'token-1'})
        self.assertTrue(capture_access_token(response))
        self.assertEqual(var.api_access_token, 'token-1')

    @patch('gmonster_api.refresh_access_token', return_value=True)
    def test_authenticated_request_refreshes_once_after_401(self, refresh):
        first = Mock(status_code=401)
        second = Mock(status_code=200)
        session = Mock(); session.request.side_effect = [first, second]
        var.api_access_token = 'old'
        response = authenticated_request('GET', 'api/unsubscribe/setting', session=session)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.request.call_count, 2)
        refresh.assert_called_once()
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_gmonster_api -v`

Expected: FAIL because `gmonster_api.py` and `var.api_access_token` do not exist.

- [ ] **Step 3: Implement in-memory token capture and authenticated requests**

```python
# var.py
api_access_token = ''
```

```python
# gmonster_api.py
import requests
import var

TOKEN_HEADER = 'X-Gmonster-Access-Token'


def capture_access_token(response):
    token = str(response.headers.get(TOKEN_HEADER, '')).strip()
    if token:
        var.api_access_token = token
        return True
    return False


def _login_payload():
    return {'email': var.login_email, 'password': var.login_password,
            'machine_uuid': var.login_machine_uuid,
            'processor_id': var.login_processor_id,
            'version': var.version, 'type': 'main'}


def refresh_access_token(session=requests):
    response = session.post(var.api + 'verify/login', json=_login_payload(),
                            timeout=var.API_TIMEOUT)
    return response.status_code == 200 and response.text == 'Success' and capture_access_token(response)


def authenticated_request(method, path, *, json=None, timeout=None, session=requests):
    def send():
        return session.request(method, var.api + path.lstrip('/'), json=json,
                               headers={'Authorization': f'Bearer {var.api_access_token}'},
                               timeout=timeout or var.API_TIMEOUT)
    response = send()
    if response.status_code == 401 and refresh_access_token(session=session):
        response = send()
    return response
```

In `dialog.make_sign_up_requests`, call `capture_access_token(x)` only when `endpoint == 'login'` and `x.text == 'Success'`. Clear `var.api_access_token` before each login attempt and on failed login.

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_gmonster_api -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add var.py dialog.py gmonster_api.py tests/test_gmonster_api.py
git commit -m "feat: authenticate unsubscribe API requests"
```

---

### Task 2: Unsubscribe API client and all-or-nothing preparation

**Files:**
- Create: `unsubscribe_client.py`
- Create: `tests/test_unsubscribe_client.py`

**Interfaces:**
- Produces: `PreparationError`.
- Produces: `PreparedRecipient(ref, email, status, unsubscribe_url)`.
- Produces: `prepare_batches(assignments, campaign_id, subject, kind) -> tuple[bool, dict[str, PreparedRecipient]]`.
- Produces: `get_setting()`, `update_setting(enabled)`, `get_records()`, `add_manual(email)`.

- [ ] **Step 1: Write failing batching, completeness, and setting-consistency tests**

```python
# tests/test_unsubscribe_client.py
import unittest
from unittest.mock import patch, Mock
from unsubscribe_client import PreparationError, prepare_batches


class UnsubscribeClientTest(unittest.TestCase):
    @patch('unsubscribe_client.authenticated_request')
    def test_prepares_1001_recipients_in_two_batches(self, request):
        def response_for_call(*args, **kwargs):
            recipients = kwargs['json']['recipients']
            return Mock(status_code=200, json=lambda: {
                'insert_unsubscribe_link': True,
                'results': [{'ref': row['ref'], 'email': row['email'],
                             'status': 'allowed',
                             'unsubscribe_url': 'https://server/unsubscribe?t=' + row['ref']}
                            for row in recipients]})
        request.side_effect = response_for_call
        assignments = [{'ref': str(i), 'email': f'lead{i}@example.com',
                        'sender_email': 'sales@example.com'} for i in range(1001)]
        enabled, prepared = prepare_batches(assignments, 'campaign', 'Subject', 'initial')
        self.assertTrue(enabled)
        self.assertEqual(len(prepared), 1001)
        self.assertEqual(request.call_count, 2)

    @patch('unsubscribe_client.authenticated_request')
    def test_incomplete_response_aborts_preparation(self, request):
        request.return_value = Mock(status_code=200, json=lambda: {
            'insert_unsubscribe_link': True, 'results': []})
        with self.assertRaises(PreparationError):
            prepare_batches([{'ref': '0', 'email': 'lead@example.com',
                              'sender_email': 'sales@example.com'}],
                            'campaign', 'Subject', 'initial')
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_unsubscribe_client -v`

Expected: FAIL because the client module does not exist.

- [ ] **Step 3: Implement the strict client contract**

```python
# unsubscribe_client.py
from dataclasses import dataclass
from gmonster_api import authenticated_request

BATCH_SIZE = 1000


class PreparationError(RuntimeError):
    """Campaign preparation failed before SMTP was allowed to start."""


@dataclass(frozen=True)
class PreparedRecipient:
    ref: str
    email: str
    status: str
    unsubscribe_url: str = ''


def _chunks(values, size=BATCH_SIZE):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def prepare_batches(assignments, campaign_id, subject, kind):
    prepared, effective_setting = {}, None
    grouped = {}
    for row in assignments:
        grouped.setdefault(row['sender_email'], []).append(row)
    for sender_email, sender_rows in grouped.items():
        for batch in _chunks(sender_rows):
            payload = {'campaign_id': campaign_id, 'campaign_subject': subject,
                       'sender_email': sender_email, 'kind': kind,
                       'recipients': [{'ref': row['ref'], 'email': row['email']}
                                      for row in batch]}
            response = authenticated_request('POST', 'api/unsubscribe/prepare',
                                             json=payload)
            if response.status_code != 200:
                raise PreparationError('Unable to prepare campaign recipients')
            data = response.json()
            setting = data.get('insert_unsubscribe_link')
            if not isinstance(setting, bool):
                raise PreparationError('Preparation response omitted setting')
            if effective_setting is not None and setting != effective_setting:
                raise PreparationError('Unsubscribe setting changed during preparation')
            effective_setting = setting
            results = data.get('results')
            if not isinstance(results, list) or len(results) != len(batch):
                raise PreparationError('Preparation response was incomplete')
            expected_refs = {row['ref'] for row in batch}
            for result in results:
                ref = str(result.get('ref', ''))
                if ref not in expected_refs or ref in prepared:
                    raise PreparationError('Preparation response contained invalid references')
                status = result.get('status')
                url = result.get('unsubscribe_url', '')
                if status == 'allowed' and setting and not url:
                    raise PreparationError('Allowed recipient omitted unsubscribe URL')
                prepared[ref] = PreparedRecipient(ref, result.get('email', ''), status, url)
    if len(prepared) != len(assignments):
        raise PreparationError('Not every recipient was prepared')
    return bool(effective_setting), prepared


def get_setting():
    response = authenticated_request('GET', 'api/unsubscribe/setting')
    if response.status_code != 200: raise RuntimeError('Unable to load setting')
    return bool(response.json()['insert_unsubscribe_link'])


def update_setting(enabled):
    response = authenticated_request('PUT', 'api/unsubscribe/setting',
                                     json={'enabled': bool(enabled)})
    if response.status_code != 200: raise RuntimeError('Unable to save setting')
    return bool(response.json()['insert_unsubscribe_link'])


def get_records():
    response = authenticated_request('GET', 'api/unsubscribe/records')
    if response.status_code != 200: raise RuntimeError('Unable to load unsubscribes')
    return response.json()['records']


def add_manual(email):
    response = authenticated_request('POST', 'api/unsubscribe/manual', json={'email': email})
    if response.status_code != 200: raise ValueError('Enter a valid email address')
    return response.json()['record']
```

- [ ] **Step 4: Add mixed-setting and failed-HTTP tests**

```python
@patch('unsubscribe_client.authenticated_request')
def test_setting_change_between_batches_aborts(self, request):
    request.side_effect = [
        Mock(status_code=200, json=lambda: {
            'insert_unsubscribe_link': True,
            'results': [{'ref': str(i), 'email': f'lead{i}@example.com',
                         'status': 'allowed', 'unsubscribe_url': f'https://u/{i}'}
                        for i in range(1000)]}),
        Mock(status_code=200, json=lambda: {
            'insert_unsubscribe_link': False,
            'results': [{'ref': '1000', 'email': 'lead1000@example.com',
                         'status': 'allowed'}]}),
    ]
    assignments = [{'ref': str(i), 'email': f'lead{i}@example.com',
                    'sender_email': 'sales@example.com'} for i in range(1001)]
    with self.assertRaises(PreparationError):
        prepare_batches(assignments, 'campaign', 'Subject', 'initial')

@patch('unsubscribe_client.authenticated_request')
def test_http_failure_aborts(self, request):
    request.return_value = Mock(status_code=503)
    with self.assertRaises(PreparationError):
        prepare_batches([{'ref': '0', 'email': 'lead@example.com',
                          'sender_email': 'sales@example.com'}],
                        'campaign', 'Subject', 'initial')
```

- [ ] **Step 5: Run focused tests**

Run: `python -m unittest tests.test_unsubscribe_client -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add unsubscribe_client.py tests/test_unsubscribe_client.py
git commit -m "feat: add unsubscribe API client"
```

---

### Task 3: Safe plain-text and HTML footer composition

**Files:**
- Create: `unsubscribe_email.py`
- Create: `tests/test_unsubscribe_email.py`

**Interfaces:**
- Produces: `compose_alternatives(plain_body: str, html_body: str, url: str, enabled: bool) -> tuple[str, str]`.

- [ ] **Step 1: Write failing footer tests**

```python
# tests/test_unsubscribe_email.py
import unittest
from unsubscribe_email import compose_alternatives


class UnsubscribeEmailTest(unittest.TestCase):
    def test_enabled_footer_is_added_to_both_alternatives(self):
        plain, html = compose_alternatives('Hello', '<p>Hello</p>',
                                           'https://server/unsubscribe?token=a&b=c', True)
        self.assertIn("Don't want to receive future emails from this sender?", plain)
        self.assertIn('https://server/unsubscribe?token=a&b=c', plain)
        self.assertIn('token=a&amp;b=c', html)
        self.assertIn('>Unsubscribe</a>.', html)

    def test_disabled_footer_leaves_bodies_unchanged(self):
        self.assertEqual(compose_alternatives('Hello', '<p>Hello</p>', '', False),
                         ('Hello', '<p>Hello</p>'))
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_unsubscribe_email -v`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement fixed, escaped footer composition**

```python
# unsubscribe_email.py
from html import escape

FOOTER_TEXT = "Don't want to receive future emails from this sender?"


def compose_alternatives(plain_body, html_body, url, enabled):
    if not enabled:
        return plain_body, html_body
    if not url:
        raise ValueError('unsubscribe URL is required when footer is enabled')
    plain = plain_body.rstrip() + f'\n\n{FOOTER_TEXT} Unsubscribe: {url}'
    footer = (f'<p>{FOOTER_TEXT} '
              f'<a href="{escape(url, quote=True)}">Unsubscribe</a>.</p>')
    html = html_body.rstrip() + footer
    return plain, html
```

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_unsubscribe_email -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add unsubscribe_email.py tests/test_unsubscribe_email.py
git commit -m "feat: compose unsubscribe email footers"
```

---

### Task 4: Prepare initial campaign assignments before SMTP starts

**Files:**
- Modify: `smtp.py:871-1015`
- Modify: `smtp.py:496-590`
- Create: `tests/test_campaign_unsubscribe_preparation.py`

**Interfaces:**
- Consumes: `prepare_batches(...)` from Task 2.
- Consumes: `compose_alternatives(...)` from Task 3.
- Produces: target rows containing `UNSUBSCRIBE_URL` and `UNSUBSCRIBE_ENABLED` before `Smtp.start()`.

- [ ] **Step 1: Write failing assignment and all-or-nothing tests**

```python
# tests/test_campaign_unsubscribe_preparation.py
import unittest
from unittest.mock import patch
import pandas as pd
from smtp import build_sender_assignments, prepare_sender_assignments
from unsubscribe_client import PreparationError


class CampaignPreparationTest(unittest.TestCase):
    def test_assignments_include_sender_and_stable_ref(self):
        group = pd.DataFrame([{'EMAIL': 'a@example.com'}, {'EMAIL': 'b@example.com'}])
        targets = pd.DataFrame([{'EMAIL': f'lead{i}@example.com'} for i in range(3)])
        assignments = build_sender_assignments(group, targets, {0: 2, 1: 1})
        self.assertEqual([row['sender_email'] for row in assignments],
                         ['a@example.com', 'a@example.com', 'b@example.com'])
        self.assertEqual([row['ref'] for row in assignments], ['0', '1', '2'])

    @patch('smtp.prepare_batches', side_effect=PreparationError('offline'))
    def test_preparation_failure_returns_no_worker_payloads(self, prepare):
        with self.assertRaises(PreparationError):
            prepare_sender_assignments([], 'campaign', 'Subject')
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_campaign_unsubscribe_preparation -v`

Expected: FAIL because the assignment helpers do not exist.

- [ ] **Step 3: Extract deterministic assignment and preparation helpers**

```python
# smtp.py additions
from unsubscribe_client import prepare_batches, PreparationError
from unsubscribe_email import compose_alternatives


def build_sender_assignments(group, target, worker_email_counts):
    assignments, cursor = [], 0
    for group_index, sender in group.iterrows():
        count = worker_email_counts[group_index]
        for target_index in target.index[cursor:cursor + count]:
            assignments.append({'ref': str(target_index),
                                'email': target.at[target_index, 'EMAIL'],
                                'sender_email': sender['EMAIL'],
                                'group_index': group_index})
        cursor += count
    return assignments


def prepare_sender_assignments(assignments, campaign_id, subject):
    enabled, results = prepare_batches(assignments, campaign_id, subject, 'initial')
    prepared = []
    for assignment in assignments:
        result = results[assignment['ref']]
        if result.status == 'allowed':
            prepared.append({**assignment, 'unsubscribe_enabled': enabled,
                             'unsubscribe_url': result.unsubscribe_url})
    return prepared
```

Refactor `smtp.main` to calculate assignments immediately after worker counts, call `prepare_sender_assignments`, and construct all worker target slices before starting webhook/cache/removal workers or any `Smtp` thread. If preparation raises, enqueue an alert, leave `send_campaign_email_count` at zero, and exit through the existing `finally` UI reset.

- [ ] **Step 4: Attach prepared metadata and compose both MIME alternatives**

Before each worker starts, add `UNSUBSCRIBE_ENABLED` and `UNSUBSCRIBE_URL` to its target rows. In `Smtp.run`, always build `plain_body` and `html_body`, call:

```python
plain_body, html_body = compose_alternatives(
    plain_body, html_body,
    str(item.get('UNSUBSCRIBE_URL', '')),
    bool(item.get('UNSUBSCRIBE_ENABLED', False)),
)
msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
msg.attach(MIMEText(html_body, 'html', 'utf-8'))
```

Remove the old branch that emits only HTML for `var.body_type == 'Html'`. Preserve personalization, attachments, reports, webhooks, block checks, and follow-up queue behavior.

- [ ] **Step 5: Run preparation and email tests**

Run: `python -m unittest tests.test_campaign_unsubscribe_preparation tests.test_unsubscribe_email -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add smtp.py tests/test_campaign_unsubscribe_preparation.py
git commit -m "feat: prepare campaign unsubscribe links before sending"
```

---

### Task 5: Re-prepare recipients before every follow-up run

**Files:**
- Modify: `smtp.py:1127-1224`
- Modify: `followup_smtp.py:59-119`
- Create: `tests/test_followup_unsubscribe_preparation.py`

**Interfaces:**
- Consumes: Task 2 preparation and Task 3 footer composition.
- Produces: fresh `unsubscribe_url` and `unsubscribe_enabled` values on each follow-up target.

- [ ] **Step 1: Write failing follow-up filtering tests**

```python
# tests/test_followup_unsubscribe_preparation.py
import unittest
from unittest.mock import patch
from smtp import prepare_followup_groups
from unsubscribe_client import PreparedRecipient


class FollowupPreparationTest(unittest.TestCase):
    @patch('smtp.prepare_batches')
    def test_suppressed_recipient_is_removed_before_followup_thread(self, prepare):
        prepare.return_value = (True, {
            '0': PreparedRecipient('0', 'blocked@example.com', 'suppressed'),
            '1': PreparedRecipient('1', 'open@example.com', 'allowed', 'https://u/1'),
        })
        groups = [{'user': 'sales@example.com', 'target_info': [
            {'target_email': 'blocked@example.com'}, {'target_email': 'open@example.com'}]}]
        result = prepare_followup_groups(groups, 'campaign', 'Follow up')
        self.assertEqual([r['target_email'] for r in result[0]['target_info']],
                         ['open@example.com'])
        self.assertEqual(result[0]['target_info'][0]['unsubscribe_url'], 'https://u/1')
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_followup_unsubscribe_preparation -v`

Expected: FAIL because `prepare_followup_groups` does not exist.

- [ ] **Step 3: Implement fresh follow-up preparation before workers start**

```python
# smtp.py addition
def prepare_followup_groups(groups, campaign_id, subject):
    assignments, lookup = [], {}
    for group_index, group in enumerate(groups):
        for target_index, target in enumerate(group['target_info']):
            ref = f'{group_index}:{target_index}'
            assignments.append({'ref': ref, 'email': target['target_email'],
                                'sender_email': group['user']})
            lookup[ref] = (group_index, target)
    enabled, results = prepare_batches(assignments, campaign_id, subject, 'followup')
    prepared_groups = [{**group, 'target_info': []} for group in groups]
    for ref, (group_index, target) in lookup.items():
        result = results[ref]
        if result.status == 'allowed':
            prepared_groups[group_index]['target_info'].append({
                **target, 'unsubscribe_enabled': enabled,
                'unsubscribe_url': result.unsubscribe_url})
    return [group for group in prepared_groups if group['target_info']]
```

In `follow_up`, run this helper after IMAP reply checks produce `followup_required` and before creating any `FollowUpSend` thread. A preparation failure sends no follow-ups and logs only campaign ID plus exception class.

- [ ] **Step 4: Compose both follow-up MIME alternatives with the fresh URL**

Replace the two direct `MIMEText` attachments in `FollowUpSend.run` with:

```python
plain_body, html_body = compose_alternatives(
    html_to_text(body), body,
    item.get('unsubscribe_url', ''),
    bool(item.get('unsubscribe_enabled', False)),
)
msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
msg.attach(MIMEText(html_body, 'html', 'utf-8'))
```

Import `compose_alternatives` from `unsubscribe_email` and keep the existing attachment and SMTP retry behavior.

- [ ] **Step 5: Run focused tests**

Run: `python -m unittest tests.test_followup_unsubscribe_preparation tests.test_unsubscribe_email -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add smtp.py followup_smtp.py tests/test_followup_unsubscribe_preparation.py
git commit -m "feat: enforce unsubscribes on follow-ups"
```

---

### Task 6: Server-backed Settings toggle

**Files:**
- Modify: `ui/gui.ui:2700-2840`
- Regenerate: `gui.py`
- Modify: `main.py:491-730`
- Create: `unsubscribe_setting.py`
- Create: `tests/test_unsubscribe_setting_controller.py`

**Interfaces:**
- Creates UI object `GUI.checkBox_insert_unsubscribe_link`.
- Consumes: `get_setting()` and `update_setting(enabled)`.

- [ ] **Step 1: Write failing controller tests against a small focused controller**

```python
# tests/test_unsubscribe_setting_controller.py
import unittest
from unittest.mock import Mock
from unsubscribe_setting import UnsubscribeSettingController


class UnsubscribeSettingControllerTest(unittest.TestCase):
    def test_failed_save_restores_previous_value(self):
        checkbox = Mock()
        checkbox.blockSignals.return_value = False
        controller = UnsubscribeSettingController(
            checkbox, load=lambda: False,
            save=Mock(side_effect=RuntimeError('offline')))
        controller.current_value = False
        with self.assertRaises(RuntimeError): controller.persist_value(True)
        controller.restore_current_value()
        checkbox.setChecked.assert_called_with(False)
```

- [ ] **Step 2: Add the checkbox in Qt Designer XML and regenerate**

Add a `QCheckBox` named `checkBox_insert_unsubscribe_link` beside the existing campaign settings checkboxes, with text `Insert unsubscribe link` and the same checked/unchecked pill stylesheet as `checkBox_hide_warmup_emails`.

```xml
<item>
 <widget class="QCheckBox" name="checkBox_insert_unsubscribe_link">
  <property name="styleSheet">
   <string notr="true">QCheckBox { padding: 8px 16px; background-color: #e2e8f0; color: #4a5568; border-radius: 16px; font-weight: bold; border: 1px solid #cbd5e1; } QCheckBox::indicator { width: 0px; height: 0px; } QCheckBox:hover { background-color: #cbd5e1; } QCheckBox:checked { background-color: #028fc3; color: #ffffff; border: 1px solid #028fc3; }</string>
  </property>
  <property name="text"><string>Insert unsubscribe link</string></property>
 </widget>
</item>
```

Run: `python3 -m PyQt5.uic.pyuic ui/gui.ui -o gui.py`

Expected: `rg -n "checkBox_insert_unsubscribe_link" gui.py` finds construction and translated text.

- [ ] **Step 3: Implement focused setting state/rollback behavior**

```python
# unsubscribe_setting.py
class UnsubscribeSettingController:
    def __init__(self, checkbox, load, save):
        self.checkbox, self.load, self.save = checkbox, load, save
        self.current_value = False

    def apply_loaded_value(self, enabled):
        previous = self.checkbox.blockSignals(True)
        self.checkbox.setChecked(bool(enabled))
        self.checkbox.setEnabled(True)
        self.checkbox.blockSignals(previous)
        self.current_value = bool(enabled)

    def persist_value(self, requested):
        return bool(self.save(bool(requested)))

    def restore_current_value(self):
        previous = self.checkbox.blockSignals(True)
        self.checkbox.setChecked(self.current_value)
        self.checkbox.setEnabled(True)
        self.checkbox.blockSignals(previous)
```

In `MyMainClass.__init__`, create the controller, disable the checkbox while a background thread calls `get_setting`, apply the result on the Qt thread through `var.command_q`, and connect `stateChanged` only after controller creation. On load failure leave it disabled and show `Unable to load unsubscribe setting. Retry by reopening Gmonster.` On save failure show `Unable to save unsubscribe setting. Your previous setting is still active.`

```python
# main.py methods and __init__ wiring
self.unsubscribe_setting = UnsubscribeSettingController(
    GUI.checkBox_insert_unsubscribe_link, get_setting, update_setting)
GUI.checkBox_insert_unsubscribe_link.setEnabled(False)
GUI.checkBox_insert_unsubscribe_link.stateChanged.connect(
    self.begin_save_unsubscribe_setting)
Thread(target=self.load_unsubscribe_setting, daemon=True).start()

def load_unsubscribe_setting(self):
    try:
        self._loaded_unsubscribe_setting = get_setting()
        var.command_q.put('self.finish_load_unsubscribe_setting()')
    except Exception:
        var.command_q.put("alert(text='Unable to load unsubscribe setting. Retry by reopening Gmonster.', title='Unsubscribe setting', button='OK')")

def finish_load_unsubscribe_setting(self):
    self.unsubscribe_setting.apply_loaded_value(self._loaded_unsubscribe_setting)

def begin_save_unsubscribe_setting(self, _state):
    requested = GUI.checkBox_insert_unsubscribe_link.isChecked()
    GUI.checkBox_insert_unsubscribe_link.setEnabled(False)
    Thread(target=self.save_unsubscribe_setting, args=(requested,), daemon=True).start()

def save_unsubscribe_setting(self, requested):
    try:
        self._saved_unsubscribe_setting = self.unsubscribe_setting.persist_value(requested)
        var.command_q.put('self.finish_save_unsubscribe_setting()')
    except Exception:
        var.command_q.put('self.fail_save_unsubscribe_setting()')

def finish_save_unsubscribe_setting(self):
    self.unsubscribe_setting.apply_loaded_value(self._saved_unsubscribe_setting)

def fail_save_unsubscribe_setting(self):
    self.unsubscribe_setting.restore_current_value()
    alert(text='Unable to save unsubscribe setting. Your previous setting is still active.',
          title='Unsubscribe setting', button='OK')
```

- [ ] **Step 4: Run controller tests and verify generated UI imports**

Run: `python -m unittest tests.test_unsubscribe_setting_controller -v`

Run: `python -m py_compile gui.py main.py unsubscribe_setting.py`

Expected: PASS and no syntax errors.

- [ ] **Step 5: Commit**

```bash
git add ui/gui.ui gui.py main.py unsubscribe_setting.py tests/test_unsubscribe_setting_controller.py
git commit -m "feat: add server-backed unsubscribe setting"
```

---

### Task 7: Unsubscribes management page, search, manual add, and CSV

**Files:**
- Create: `unsubscribe_management.py`
- Create: `unsubscribe_page.py`
- Modify: `main.py:491-510,1033-1076,3129-3155`
- Create: `tests/test_unsubscribe_management.py`
- Create: `tests/test_unsubscribe_page.py`

**Interfaces:**
- Produces: `filter_records(records, query) -> list[dict]`.
- Produces: `export_records(path, records) -> int`.
- Produces: `UnsubscribePage`, with Qt signals `refreshRequested`, `manualAddRequested(str)`, and `exportRequested()`.

- [ ] **Step 1: Write failing search and filtered-export tests**

```python
# tests/test_unsubscribe_management.py
import csv, tempfile, unittest
from unsubscribe_management import filter_records, export_records


class UnsubscribeManagementTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {'email': 'alice@example.com', 'unsubscribed_at': '2026-07-19T01:00:00Z',
             'source': 'link', 'campaign_subject': 'Pricing'},
            {'email': 'bob@example.com', 'unsubscribed_at': '2026-07-18T01:00:00Z',
             'source': 'manual', 'campaign_subject': None},
        ]

    def test_search_matches_email_source_and_subject(self):
        self.assertEqual([r['email'] for r in filter_records(self.rows, 'pricing')],
                         ['alice@example.com'])
        self.assertEqual([r['email'] for r in filter_records(self.rows, 'manual')],
                         ['bob@example.com'])

    def test_export_writes_only_supplied_filtered_rows(self):
        with tempfile.NamedTemporaryFile(suffix='.csv') as file:
            self.assertEqual(export_records(file.name, self.rows[:1]), 1)
            file.seek(0)
            rows = list(csv.DictReader(line.decode() for line in file.readlines()))
        self.assertEqual([row['email'] for row in rows], ['alice@example.com'])
```

- [ ] **Step 2: Implement pure search and export helpers**

```python
# unsubscribe_management.py
import csv

COLUMNS = ('email', 'unsubscribed_at', 'source', 'campaign_subject')


def filter_records(records, query):
    needle = str(query or '').strip().lower()
    if not needle: return list(records)
    return [row for row in records if any(
        needle in str(row.get(column) or '').lower() for column in COLUMNS)]


def export_records(path, records):
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({column: row.get(column) or '' for column in COLUMNS}
                         for row in records)
    return len(records)
```

- [ ] **Step 3: Create the focused PyQt page**

```python
# unsubscribe_page.py
from PyQt5 import QtCore, QtWidgets
from unsubscribe_management import filter_records


class UnsubscribePage(QtWidgets.QWidget):
    refreshRequested = QtCore.pyqtSignal()
    manualAddRequested = QtCore.pyqtSignal(str)
    exportRequested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = []
        self.filtered_records = []
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel('Unsubscribes')
        title.setObjectName('unsubscribeTitle')
        self.refresh_button = QtWidgets.QPushButton('Refresh')
        self.refresh_button.setObjectName('unsubscribeRefreshButton')
        header.addWidget(title); header.addStretch(); header.addWidget(self.refresh_button)
        actions = QtWidgets.QHBoxLayout()
        self.search_button = QtWidgets.QPushButton('Search')
        self.search_button.setObjectName('unsubscribeSearchButton')
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText('Search unsubscribes')
        self.search_input.setClearButtonEnabled(True)
        self.search_input.hide()
        self.add_button = QtWidgets.QPushButton('Add manually')
        self.add_button.setObjectName('unsubscribeAddButton')
        self.export_button = QtWidgets.QPushButton('Export to CSV')
        self.export_button.setObjectName('unsubscribeExportButton')
        actions.addWidget(self.search_button); actions.addWidget(self.search_input)
        actions.addStretch(); actions.addWidget(self.add_button); actions.addWidget(self.export_button)
        self.status_label = QtWidgets.QLabel('')
        self.status_label.setObjectName('unsubscribeStatusLabel')
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ['Email', 'Unsubscribed at', 'Source', 'Campaign'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        layout.addLayout(header); layout.addLayout(actions)
        layout.addWidget(self.status_label); layout.addWidget(self.table)
        self.refresh_button.clicked.connect(self.refreshRequested.emit)
        self.search_button.clicked.connect(self.toggle_search)
        self.search_input.textChanged.connect(self.apply_filter)
        self.add_button.clicked.connect(self.request_manual_add)
        self.export_button.clicked.connect(self.exportRequested.emit)

    def toggle_search(self):
        visible = not self.search_input.isVisible()
        self.search_input.setVisible(visible)
        if visible: self.search_input.setFocus()
        else: self.search_input.clear()

    def request_manual_add(self):
        email, accepted = QtWidgets.QInputDialog.getText(
            self, 'Add unsubscribe', 'Recipient email:')
        if accepted and email.strip(): self.manualAddRequested.emit(email.strip())

    def set_loading(self):
        self.status_label.setText('Loading unsubscribes…')
        self.refresh_button.setEnabled(False)

    def set_error(self, message):
        self.status_label.setText(message)
        self.refresh_button.setEnabled(True)

    def set_records(self, records):
        self.records = list(records)
        self.refresh_button.setEnabled(True)
        self.apply_filter(self.search_input.text())

    def apply_filter(self, text):
        self.filtered_records = filter_records(self.records, text)
        self.table.setRowCount(len(self.filtered_records))
        for row_index, record in enumerate(self.filtered_records):
            for column_index, key in enumerate(
                    ('email', 'unsubscribed_at', 'source', 'campaign_subject')):
                self.table.setItem(row_index, column_index,
                                   QtWidgets.QTableWidgetItem(str(record.get(key) or '')))
        self.status_label.setText(
            'No unsubscribed recipients' if not self.filtered_records
            else f'{len(self.filtered_records)} unsubscribed recipient(s)')
```

- [ ] **Step 4: Integrate the page and API controller into `main.py`**

Insert a sidebar item named `Unsubscribes`, add the page to `GUI.stackedWidget`, store its index, and extend `list_clicked` and `setup_sidebar_icons` (`fa5s.user-slash`). On navigation or refresh, load `get_records()` in a daemon thread, then apply results through the Qt command queue. Manual add calls `add_manual(email)` in a daemon thread and reloads only after confirmation. Export opens `QFileDialog.getSaveFileName`, then calls `export_records(path, page.filtered_records)`.

Failures set the page error state without discarding the last successfully loaded rows. Do not log the entered address.

```python
# main.py setup and controller methods
def setup_unsubscribe_page(self):
    GUI.listWidget.insertItem(GUI.listWidget.count() - 1, 'Unsubscribes')
    self.unsubscribe_page = UnsubscribePage()
    self.unsubscribe_page_index = GUI.stackedWidget.addWidget(self.unsubscribe_page)
    self.unsubscribe_page.refreshRequested.connect(self.refresh_unsubscribes)
    self.unsubscribe_page.manualAddRequested.connect(self.add_manual_unsubscribe)
    self.unsubscribe_page.exportRequested.connect(self.export_unsubscribes)

def refresh_unsubscribes(self):
    self.unsubscribe_page.set_loading()
    Thread(target=self._load_unsubscribes, daemon=True).start()

def _load_unsubscribes(self):
    try:
        self._unsubscribe_records = get_records()
        var.command_q.put('self._finish_load_unsubscribes()')
    except Exception:
        var.command_q.put("self.unsubscribe_page.set_error('Unable to load unsubscribes. Select Refresh to retry.')")

def _finish_load_unsubscribes(self):
    self.unsubscribe_page.set_records(self._unsubscribe_records)

def add_manual_unsubscribe(self, email):
    self._manual_unsubscribe_email = email
    Thread(target=self._add_manual_unsubscribe, daemon=True).start()

def _add_manual_unsubscribe(self):
    try:
        add_manual(self._manual_unsubscribe_email)
        self._load_unsubscribes()
    except Exception:
        var.command_q.put("self.unsubscribe_page.set_error('Unable to add that address. Check it and retry.')")

def export_unsubscribes(self):
    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        mainWindow, 'Export unsubscribes', 'unsubscribes.csv', 'CSV files (*.csv)')
    if path:
        count = export_records(path, self.unsubscribe_page.filtered_records)
        alert(text=f'Exported {count} unsubscribe record(s).', title='Export complete', button='OK')
```

Call `setup_unsubscribe_page()` before `setup_sidebar_icons()`. In `list_clicked`, handle `item_text == 'Unsubscribes'` by selecting `self.unsubscribe_page_index` and calling `refresh_unsubscribes()`.

- [ ] **Step 5: Run pure and offscreen page tests**

Set `QT_QPA_PLATFORM=offscreen` and test `set_records`, filtering, empty state, and signal emission without opening the main window.

Run: `QT_QPA_PLATFORM=offscreen python -m unittest tests.test_unsubscribe_management tests.test_unsubscribe_page -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add unsubscribe_management.py unsubscribe_page.py main.py tests/test_unsubscribe_management.py tests/test_unsubscribe_page.py
git commit -m "feat: add unsubscribe management page"
```

---

### Task 8: End-to-end verification and operational documentation

**Files:**
- Create: `tests/test_unsubscribe_integration.py`
- Modify: `README.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Verifies the desktop contract against a fake HTTP server/session and composed MIME messages without real SMTP.

- [ ] **Step 1: Add the integration test**

```python
import unittest
from unittest.mock import Mock, patch
from unsubscribe_client import prepare_batches
from unsubscribe_email import compose_alternatives


class UnsubscribeIntegrationTest(unittest.TestCase):
    @patch('unsubscribe_client.authenticated_request')
    def test_prepare_click_then_suppress_on_next_campaign(self, request):
        clicked = {'value': False}

        def fake_request(method, path, json=None, **kwargs):
            ref = json['recipients'][0]['ref']
            if clicked['value']:
                result = {'ref': ref, 'email': 'lead@example.com',
                          'status': 'suppressed'}
            else:
                result = {'ref': ref, 'email': 'lead@example.com',
                          'status': 'allowed',
                          'unsubscribe_url': 'https://server/unsubscribe?token=opaque'}
            return Mock(status_code=200, json=lambda: {
                'insert_unsubscribe_link': True, 'results': [result]})

        request.side_effect = fake_request
        assignment = [{'ref': '0', 'email': 'lead@example.com',
                       'sender_email': 'sales@example.com'}]
        enabled, first = prepare_batches(assignment, 'campaign-1', 'Hello', 'initial')
        plain, html = compose_alternatives(
            'Hello', '<p>Hello</p>', first['0'].unsubscribe_url, enabled)
        self.assertIn('token=opaque', plain)
        self.assertIn('token=opaque', html)
        clicked['value'] = True
        _, second = prepare_batches(assignment, 'campaign-2', 'Hello again', 'initial')
        allowed = [row for row in second.values() if row.status == 'allowed']
        smtp_send = Mock()
        for row in allowed: smtp_send(row.email)
        smtp_send.assert_not_called()
```

- [ ] **Step 2: Run all targeted desktop tests**

Run:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest \
  tests.test_gmonster_api \
  tests.test_unsubscribe_client \
  tests.test_unsubscribe_email \
  tests.test_campaign_unsubscribe_preparation \
  tests.test_followup_unsubscribe_preparation \
  tests.test_unsubscribe_setting_controller \
  tests.test_unsubscribe_management \
  tests.test_unsubscribe_page \
  tests.test_unsubscribe_integration -v
```

Expected: all tests PASS.

- [ ] **Step 3: Run the complete existing suite and syntax checks**

Run: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

Run: `python -m py_compile dialog.py main.py smtp.py followup_smtp.py gmonster_api.py unsubscribe_client.py unsubscribe_email.py unsubscribe_setting.py unsubscribe_management.py unsubscribe_page.py`

Expected: all tests PASS and compilation exits 0.

- [ ] **Step 4: Perform a staging smoke test without sending to real recipients**

Use a two-address controlled target list and test mailboxes. Verify:

1. Login UI is unchanged and token capture succeeds.
2. Existing account toggle starts off and persists on the server when enabled.
3. Campaign preparation completes before SMTP starts.
4. The received message contains matching active links in plain-text and HTML alternatives.
5. Clicking one link shows the generic confirmation page.
6. A second controlled campaign filters that address.
7. A scheduled follow-up also filters it.
8. Manual add, search, and filtered CSV export work.
9. Disconnecting the server before preparation sends zero messages and shows a retryable error.

- [ ] **Step 5: Document operational behavior**

Update README/AGENTS with the server dependency, bearer-token header, no-local-cache rule, preparation-before-send rule, batch size 1,000, UI regeneration command, and staging verification commands. Do not document or commit real tokens, recipient lists, credentials, or Fernet keys.

- [ ] **Step 6: Commit**

```bash
git add tests/test_unsubscribe_integration.py README.md AGENTS.md
git commit -m "test: verify unsubscribe workflow"
```

## Desktop Completion Gate

The feature is complete only when the server completion gate has passed, all desktop tests pass, the generated `gui.py` matches `ui/gui.ui`, and the controlled staging smoke test confirms that a clicked recipient is excluded from both a later campaign and a later follow-up.
