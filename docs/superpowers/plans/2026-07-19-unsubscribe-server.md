# Unsubscribe Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add authenticated, account-wide unsubscribe settings, campaign preparation, suppression management, and public unsubscribe links to the live Flask server.

**Architecture:** Extend `Subscriber` with the footer setting and add a unique account-recipient suppression model. A new unsubscribe blueprint exposes bearer-token-protected account APIs and an unauthenticated encrypted-link endpoint. Login remains text-compatible and adds a session token response header.

**Tech Stack:** Python 3.9, Flask 3.1, Flask-SQLAlchemy, Alembic/Flask-Migrate, itsdangerous, cryptography/Fernet, unittest.

## Global Constraints

- Server repository: `/Users/moeezmujahid/Projects/gmail_sub`.
- Existing login response body must remain exactly `Success` for successful logins.
- Existing accounts default footer insertion off; accounts created after migration default on.
- Suppression is account-wide across every sending mailbox.
- The server is the only persistent source of truth; no desktop suppression database exists.
- Tokens are non-expiring, confidential, authenticated, and generated only by the server.
- Campaign-preparation requests contain at most 1,000 recipients.
- Suppression filtering runs even when footer insertion is disabled.
- Never log passwords, bearer tokens, unsubscribe tokens, or complete recipient lists.

---

### Task 1: Subscriber session tokens without breaking login

**Files:**
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/security.py`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/verify/views.py:72-106`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/config.py:5-24`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/.env.example`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/tests/test_subscriber_token_auth.py`

**Interfaces:**
- Produces: `issue_subscriber_token(subscriber_id: int) -> str`.
- Produces: `subscriber_from_bearer_request() -> tuple[Subscriber | None, str | None]`.
- Produces: successful `/verify/login` header `X-Gmonster-Access-Token`.

- [ ] **Step 1: Write failing token and login-compatibility tests**

```python
# tests/test_subscriber_token_auth.py
import unittest
from datetime import date, timedelta

from app import create_app, db
from app.models import Subscriber, Version


class SubscriberTokenAuthTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['SUBSCRIBER_TOKEN_MAX_AGE_SECONDS'] = 3600
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        sub = Subscriber(email='owner@example.com', active=True,
                         end_date=date.today() + timedelta(days=30),
                         machine_uuid='machine', processor_id='processor')
        sub.password = 'secret'
        db.session.add_all([sub, Version(name='2.2r', link='', size=0)])
        db.session.commit()
        self.subscriber_id = sub.id
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_login_body_stays_compatible_and_adds_token_header(self):
        response = self.client.post('/verify/login', json={
            'email': 'owner@example.com', 'password': 'secret',
            'machine_uuid': 'machine', 'processor_id': 'processor',
            'version': '2.2r', 'type': 'main',
        })
        self.assertEqual(response.get_data(as_text=True), 'Success')
        self.assertTrue(response.headers['X-Gmonster-Access-Token'])

    def test_bearer_token_resolves_active_subscriber(self):
        from app.security import issue_subscriber_token, subscriber_from_bearer_request
        token = issue_subscriber_token(self.subscriber_id)
        with self.app.test_request_context(headers={'Authorization': f'Bearer {token}'}):
            subscriber, error = subscriber_from_bearer_request()
        self.assertEqual(subscriber.id, self.subscriber_id)
        self.assertIsNone(error)
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python -m unittest tests.test_subscriber_token_auth -v`

Expected: FAIL because the token helpers and response header do not exist.

- [ ] **Step 3: Add signed session-token helpers and preserve the login body**

```python
# app/security.py additions
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import current_app, request


def _subscriber_serializer():
    return URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'],
        salt='gmonster-subscriber-session-v1',
    )


def issue_subscriber_token(subscriber_id: int) -> str:
    return _subscriber_serializer().dumps({'subscriber_id': subscriber_id})


def subscriber_from_bearer_request():
    from . import db
    from .models import Subscriber
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None, 'missing_token'
    try:
        payload = _subscriber_serializer().loads(
            header[7:],
            max_age=current_app.config['SUBSCRIBER_TOKEN_MAX_AGE_SECONDS'],
        )
    except SignatureExpired:
        return None, 'expired_token'
    except BadSignature:
        return None, 'invalid_token'
    subscriber = db.session.get(Subscriber, payload.get('subscriber_id'))
    if not subscriber:
        return None, 'invalid_token'
    if not subscriber.active:
        return None, 'not_activated'
    if subscriber.end_date < datetime.utcnow().date():
        return None, 'subscription_expired'
    return subscriber, None
```

```python
# config.py Config addition
SUBSCRIBER_TOKEN_MAX_AGE_SECONDS = int(
    os.environ.get('SUBSCRIBER_TOKEN_MAX_AGE_SECONDS', '3600'))
```

```python
# app/verify/views.py successful login return
from ..security import issue_subscriber_token, validate_subscriber_credentials

response = current_app.make_response('Success')
response.headers['X-Gmonster-Access-Token'] = issue_subscriber_token(sub.id)
return response
```

Add `SUBSCRIBER_TOKEN_MAX_AGE_SECONDS=3600` to `.env.example`.

- [ ] **Step 4: Run the focused and existing authentication tests**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python -m unittest tests.test_subscriber_token_auth tests.test_ai_response_api -v`

Expected: PASS; existing login/AI behavior remains intact.

- [ ] **Step 5: Commit**

```bash
git add app/security.py app/verify/views.py config.py .env.example tests/test_subscriber_token_auth.py
git commit -m "feat: issue subscriber API session tokens"
```

---

### Task 2: Account setting and suppression schema

**Files:**
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/models.py:40-88`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/migrations/versions/c1d2e3f4a5b6_add_unsubscribe_suppressions.py`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/tests/test_unsubscribe_models.py`

**Interfaces:**
- Produces: `Subscriber.insert_unsubscribe_link: bool`.
- Produces: `UnsubscribeSuppression` with unique `(subscriber_id, normalized_email)`.

- [ ] **Step 1: Write failing model tests**

```python
# tests/test_unsubscribe_models.py
import unittest
from datetime import date, timedelta
from sqlalchemy.exc import IntegrityError
from app import create_app, db
from app.models import Subscriber, UnsubscribeSuppression


class UnsubscribeModelTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context(); self.ctx.push(); db.create_all()
        self.sub = Subscriber(email='owner@example.com', active=True,
                              end_date=date.today() + timedelta(days=30))
        db.session.add(self.sub); db.session.commit()

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()

    def test_new_subscriber_defaults_footer_on(self):
        self.assertTrue(self.sub.insert_unsubscribe_link)

    def test_account_and_normalized_email_are_unique(self):
        db.session.add_all([
            UnsubscribeSuppression(subscriber_id=self.sub.id, email='Lead@Example.com',
                                   normalized_email='lead@example.com', source='link'),
            UnsubscribeSuppression(subscriber_id=self.sub.id, email='lead@example.com',
                                   normalized_email='lead@example.com', source='manual'),
        ])
        with self.assertRaises(IntegrityError):
            db.session.commit()
```

- [ ] **Step 2: Run and verify failure**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python -m unittest tests.test_unsubscribe_models -v`

Expected: FAIL because the setting and suppression model do not exist.

- [ ] **Step 3: Add the SQLAlchemy fields and model**

```python
# app/models.py Subscriber addition
insert_unsubscribe_link = db.Column(
    db.Boolean, nullable=False, default=True, server_default=db.true())


class UnsubscribeSuppression(db.Model):
    __tablename__ = 'unsubscribe_suppressions'
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('subscribers.id'),
                              nullable=False, index=True)
    email = db.Column(db.String(254), nullable=False)
    normalized_email = db.Column(db.String(254), nullable=False)
    unsubscribed_at = db.Column(db.DateTime, nullable=False,
                                default=datetime.datetime.utcnow)
    source = db.Column(db.String(16), nullable=False)
    campaign_id = db.Column(db.String(36))
    campaign_subject = db.Column(db.Text)
    sender_email = db.Column(db.String(254))
    subscriber = db.relationship('Subscriber', backref='unsubscribe_suppressions')
    __table_args__ = (
        db.UniqueConstraint('subscriber_id', 'normalized_email',
                            name='uq_unsubscribe_subscriber_email'),
        db.CheckConstraint("source IN ('link', 'manual')",
                           name='ck_unsubscribe_source'),
    )
```

- [ ] **Step 4: Add the Alembic migration with existing-off/new-on semantics**

```python
# migrations/versions/c1d2e3f4a5b6_add_unsubscribe_suppressions.py
from alembic import op
import sqlalchemy as sa

revision = 'c1d2e3f4a5b6'
down_revision = 'afe090dd7658'


def upgrade():
    with op.batch_alter_table('subscribers') as batch_op:
        batch_op.add_column(sa.Column('insert_unsubscribe_link', sa.Boolean(),
                                      nullable=False, server_default=sa.false()))
    op.execute(sa.text('UPDATE subscribers SET insert_unsubscribe_link = false'))
    with op.batch_alter_table('subscribers') as batch_op:
        batch_op.alter_column('insert_unsubscribe_link', server_default=sa.true())
    op.create_table(
        'unsubscribe_suppressions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subscriber_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('normalized_email', sa.String(254), nullable=False),
        sa.Column('unsubscribed_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(16), nullable=False),
        sa.Column('campaign_id', sa.String(36)),
        sa.Column('campaign_subject', sa.Text()),
        sa.Column('sender_email', sa.String(254)),
        sa.ForeignKeyConstraint(['subscriber_id'], ['subscribers.id']),
        sa.UniqueConstraint('subscriber_id', 'normalized_email',
                            name='uq_unsubscribe_subscriber_email'),
        sa.CheckConstraint("source IN ('link', 'manual')",
                           name='ck_unsubscribe_source'),
    )
    op.create_index('ix_unsubscribe_suppressions_subscriber_id',
                    'unsubscribe_suppressions', ['subscriber_id'])


def downgrade():
    op.drop_index('ix_unsubscribe_suppressions_subscriber_id',
                  table_name='unsubscribe_suppressions')
    op.drop_table('unsubscribe_suppressions')
    with op.batch_alter_table('subscribers') as batch_op:
        batch_op.drop_column('insert_unsubscribe_link')
```

- [ ] **Step 5: Run tests and validate migration upgrade/downgrade**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python -m unittest tests.test_unsubscribe_models -v`

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && FLASK_CONFIG=development flask db upgrade && FLASK_CONFIG=development flask db downgrade afe090dd7658 && FLASK_CONFIG=development flask db upgrade`

Expected: tests PASS and migration completes in both directions.

- [ ] **Step 6: Commit**

```bash
git add app/models.py migrations/versions/c1d2e3f4a5b6_add_unsubscribe_suppressions.py tests/test_unsubscribe_models.py
git commit -m "feat: add unsubscribe suppression schema"
```

---

### Task 3: Confidential non-expiring unsubscribe tokens

**Files:**
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/requirements.txt`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/Pipfile`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/config.py`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/.env.example`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/app/unsubscribe/__init__.py`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/app/unsubscribe/tokens.py`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/tests/test_unsubscribe_tokens.py`

**Interfaces:**
- Produces: `encrypt_unsubscribe_token(payload: dict) -> str`.
- Produces: `decrypt_unsubscribe_token(token: str) -> dict`.

Create an empty `app/unsubscribe/__init__.py` in this task so token imports work; Task 4 replaces it with the blueprint declaration.

- [ ] **Step 1: Write failing confidentiality, round-trip, and tamper tests**

```python
# tests/test_unsubscribe_tokens.py
import unittest
from cryptography.fernet import Fernet, InvalidToken
from app import create_app


class UnsubscribeTokenTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['UNSUBSCRIBE_TOKEN_KEYS'] = [Fernet.generate_key().decode()]
        self.ctx = self.app.app_context(); self.ctx.push()

    def tearDown(self): self.ctx.pop()

    def test_token_is_opaque_and_round_trips(self):
        from app.unsubscribe.tokens import encrypt_unsubscribe_token, decrypt_unsubscribe_token
        payload = {'subscriber_id': 7, 'email': 'lead@example.com',
                   'campaign_id': 'campaign-1', 'campaign_subject': 'Hello',
                   'sender_email': 'sales@example.com'}
        token = encrypt_unsubscribe_token(payload)
        self.assertNotIn('lead@example.com', token)
        self.assertEqual(decrypt_unsubscribe_token(token), payload)

    def test_modified_token_is_rejected(self):
        from app.unsubscribe.tokens import encrypt_unsubscribe_token, decrypt_unsubscribe_token
        token = encrypt_unsubscribe_token({'subscriber_id': 7, 'email': 'lead@example.com'})
        with self.assertRaises(InvalidToken):
            decrypt_unsubscribe_token(token[:-1] + ('A' if token[-1] != 'A' else 'B'))
```

- [ ] **Step 2: Add cryptography and verify the tests fail on missing module code**

Add `cryptography==45.0.5` to `requirements.txt` and `cryptography = "==45.0.5"` to `Pipfile`.

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python -m unittest tests.test_unsubscribe_tokens -v`

Expected: FAIL because `app.unsubscribe.tokens` does not exist.

- [ ] **Step 3: Implement versioned MultiFernet tokens**

```python
# app/unsubscribe/tokens.py
import json
from cryptography.fernet import Fernet, MultiFernet
from flask import current_app


def _fernet():
    keys = current_app.config['UNSUBSCRIBE_TOKEN_KEYS']
    return MultiFernet([Fernet(key.encode('ascii')) for key in keys])


def encrypt_unsubscribe_token(payload: dict) -> str:
    envelope = {'version': 1, 'payload': payload}
    raw = json.dumps(envelope, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return _fernet().encrypt(raw).decode('ascii')


def decrypt_unsubscribe_token(token: str) -> dict:
    envelope = json.loads(_fernet().decrypt(token.encode('ascii')).decode('utf-8'))
    if envelope.get('version') != 1 or not isinstance(envelope.get('payload'), dict):
        from cryptography.fernet import InvalidToken
        raise InvalidToken
    return envelope['payload']
```

```python
# config.py Config addition
UNSUBSCRIBE_TOKEN_KEYS = [value for value in
    os.environ.get('UNSUBSCRIBE_TOKEN_KEYS', '').split(',') if value]
UNSUBSCRIBE_PUBLIC_BASE_URL = os.environ.get(
    'UNSUBSCRIBE_PUBLIC_BASE_URL', 'http://localhost:5000')
```

Add both variables to `.env.example`, using a documented Fernet-shaped example key and `http://localhost:5000`.

- [ ] **Step 4: Run token tests**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python -m unittest tests.test_unsubscribe_tokens -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt Pipfile config.py .env.example app/unsubscribe/tokens.py tests/test_unsubscribe_tokens.py
git commit -m "feat: add encrypted unsubscribe tokens"
```

---

### Task 4: Setting and campaign-preparation APIs

**Files:**
- Create: `/Users/moeezmujahid/Projects/gmail_sub/app/unsubscribe/__init__.py`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/app/unsubscribe/service.py`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/app/unsubscribe/views.py`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/__init__.py:42-45`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/tests/test_unsubscribe_prepare_api.py`

**Interfaces:**
- Produces: `GET/PUT /api/unsubscribe/setting`.
- Produces: `POST /api/unsubscribe/prepare`.
- Consumes: bearer auth from Task 1 and encrypted tokens from Task 3.

- [ ] **Step 1: Write API tests for setting defaults, suppression, links, limits, and isolation**

```python
# tests/test_unsubscribe_prepare_api.py test methods
def test_prepare_filters_suppressed_even_when_footer_is_off(self):
    self.sub.insert_unsubscribe_link = False
    db.session.add(UnsubscribeSuppression(
        subscriber_id=self.sub.id, email='blocked@example.com',
        normalized_email='blocked@example.com', source='manual'))
    db.session.commit()
    response = self.client.post('/api/unsubscribe/prepare', headers=self.auth,
        json={'campaign_id': 'a' * 36, 'campaign_subject': 'Hello',
              'sender_email': 'sales@example.com', 'kind': 'initial',
              'recipients': [{'ref': '0', 'email': 'blocked@example.com'},
                             {'ref': '1', 'email': 'open@example.com'}]})
    self.assertEqual(response.status_code, 200)
    self.assertFalse(response.json['insert_unsubscribe_link'])
    self.assertEqual([r['status'] for r in response.json['results']],
                     ['suppressed', 'allowed'])
    self.assertNotIn('unsubscribe_url', response.json['results'][1])

def test_prepare_rejects_more_than_1000_recipients(self):
    payload = self.valid_payload(recipients=[
        {'ref': str(i), 'email': f'lead{i}@example.com'} for i in range(1001)])
    self.assertEqual(self.client.post('/api/unsubscribe/prepare',
                     headers=self.auth, json=payload).status_code, 400)
```

Use this concrete setup at the top of the same test class:

```python
def setUp(self):
    self.app = create_app('testing')
    self.app.config['UNSUBSCRIBE_TOKEN_KEYS'] = [Fernet.generate_key().decode()]
    self.app.config['UNSUBSCRIBE_PUBLIC_BASE_URL'] = 'https://server.example.com'
    self.ctx = self.app.app_context(); self.ctx.push(); db.create_all()
    self.sub = Subscriber(email='owner@example.com', active=True,
                          end_date=date.today() + timedelta(days=30))
    self.other = Subscriber(email='other@example.com', active=True,
                            end_date=date.today() + timedelta(days=30))
    db.session.add_all([self.sub, self.other]); db.session.commit()
    self.auth = {'Authorization': 'Bearer ' + issue_subscriber_token(self.sub.id)}
    self.other_auth = {'Authorization': 'Bearer ' + issue_subscriber_token(self.other.id)}
    self.client = self.app.test_client()

def tearDown(self):
    db.session.remove(); db.drop_all(); self.ctx.pop()

def valid_payload(self, **overrides):
    payload = {'campaign_id': 'a' * 36, 'campaign_subject': 'Hello',
               'sender_email': 'sales@example.com', 'kind': 'initial',
               'recipients': [{'ref': '0', 'email': 'open@example.com'}]}
    payload.update(overrides)
    return payload

def test_other_account_suppression_does_not_block_owner(self):
    db.session.add(UnsubscribeSuppression(
        subscriber_id=self.other.id, email='open@example.com',
        normalized_email='open@example.com', source='manual'))
    db.session.commit()
    response = self.client.post('/api/unsubscribe/prepare', headers=self.auth,
                                json=self.valid_payload())
    self.assertEqual(response.json['results'][0]['status'], 'allowed')
```

- [ ] **Step 2: Run and verify failure**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python -m unittest tests.test_unsubscribe_prepare_api -v`

Expected: FAIL because the blueprint and endpoints do not exist.

- [ ] **Step 3: Implement normalization and preparation service**

```python
# app/unsubscribe/service.py
from email_validator import EmailNotValidError, validate_email
from flask import current_app
from ..models import UnsubscribeSuppression
from .tokens import encrypt_unsubscribe_token


def normalize_email(value: str) -> str:
    return validate_email(str(value).strip(), check_deliverability=False).normalized.lower()


def prepare_recipients(subscriber, data):
    recipients = data.get('recipients')
    if not isinstance(recipients, list) or not 1 <= len(recipients) <= 1000:
        raise ValueError('recipients must contain between 1 and 1000 items')
    blocked = {row.normalized_email for row in UnsubscribeSuppression.query.filter_by(
        subscriber_id=subscriber.id).all()}
    seen, results = set(), []
    for item in recipients:
        ref = str(item.get('ref', '')).strip()
        try:
            email = normalize_email(item.get('email', ''))
        except EmailNotValidError:
            results.append({'ref': ref, 'status': 'invalid', 'reason': 'invalid_email'})
            continue
        if email in seen:
            results.append({'ref': ref, 'email': email, 'status': 'invalid',
                            'reason': 'duplicate_email'})
            continue
        seen.add(email)
        if email in blocked:
            results.append({'ref': ref, 'email': email, 'status': 'suppressed'})
            continue
        result = {'ref': ref, 'email': email, 'status': 'allowed'}
        if subscriber.insert_unsubscribe_link:
            token = encrypt_unsubscribe_token({
                'subscriber_id': subscriber.id, 'email': email,
                'campaign_id': data['campaign_id'],
                'campaign_subject': data['campaign_subject'],
                'sender_email': normalize_email(data['sender_email']),
            })
            result['unsubscribe_url'] = (
                current_app.config['UNSUBSCRIBE_PUBLIC_BASE_URL'].rstrip('/')
                + '/unsubscribe?token=' + token)
        results.append(result)
    return {'insert_unsubscribe_link': subscriber.insert_unsubscribe_link,
            'results': results}
```

- [ ] **Step 4: Implement bearer-protected setting and preparation routes**

```python
# app/unsubscribe/views.py core route shape
from flask import jsonify, request
from . import unsubscribe
from .service import prepare_recipients
from .. import db
from ..security import subscriber_from_bearer_request


def _subscriber_or_response():
    subscriber, error = subscriber_from_bearer_request()
    return subscriber, (jsonify({'error': error}), 401) if not subscriber else None


@unsubscribe.route('/api/unsubscribe/setting', methods=['GET', 'PUT'])
def setting():
    subscriber, error = _subscriber_or_response()
    if error: return error
    if request.method == 'PUT':
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get('enabled'), bool):
            return jsonify({'error': 'enabled must be a boolean'}), 400
        subscriber.insert_unsubscribe_link = data['enabled']
        db.session.commit()
    return jsonify({'insert_unsubscribe_link': subscriber.insert_unsubscribe_link})


@unsubscribe.route('/api/unsubscribe/prepare', methods=['POST'])
def prepare():
    subscriber, error = _subscriber_or_response()
    if error: return error
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'JSON object body is required'}), 400
    try:
        return jsonify(prepare_recipients(subscriber, data))
    except (KeyError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400
```

Register the no-prefix blueprint in `app/__init__.py` so it can expose both `/api/unsubscribe/...` and `/unsubscribe` later.

```python
# app/unsubscribe/__init__.py
from flask import Blueprint

unsubscribe = Blueprint('unsubscribe', __name__)

from . import views

# app/__init__.py create_app addition
from .unsubscribe import unsubscribe as unsubscribe_blueprint
app.register_blueprint(unsubscribe_blueprint)
```

- [ ] **Step 5: Run focused tests**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python -m unittest tests.test_unsubscribe_prepare_api -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/unsubscribe app/__init__.py tests/test_unsubscribe_prepare_api.py
git commit -m "feat: add unsubscribe preparation API"
```

---

### Task 5: Public unsubscribe and management APIs

**Files:**
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/unsubscribe/service.py`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/unsubscribe/views.py`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/app/templates/unsubscribe_confirmation.html`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/app/templates/unsubscribe_error.html`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/tests/test_unsubscribe_management_api.py`

**Interfaces:**
- Produces: `GET /unsubscribe?token=...`.
- Produces: `GET /api/unsubscribe/records`.
- Produces: `POST /api/unsubscribe/manual`.

- [ ] **Step 1: Write failing public-click, idempotency, manual-add, list, and cross-account tests**

```python
# tests/test_unsubscribe_management_api.py test methods
def test_public_click_is_idempotent(self):
    token = encrypt_unsubscribe_token({
        'subscriber_id': self.sub.id, 'email': 'Lead@Example.com',
        'campaign_id': 'campaign', 'campaign_subject': 'Subject',
        'sender_email': 'sales@example.com'})
    first = self.client.get('/unsubscribe', query_string={'token': token})
    second = self.client.get('/unsubscribe', query_string={'token': token})
    self.assertEqual(first.status_code, 200)
    self.assertEqual(second.status_code, 200)
    self.assertEqual(UnsubscribeSuppression.query.count(), 1)

def test_invalid_token_writes_nothing(self):
    response = self.client.get('/unsubscribe', query_string={'token': 'bad'})
    self.assertEqual(response.status_code, 400)
    self.assertEqual(UnsubscribeSuppression.query.count(), 0)

def test_manual_add_and_list_are_account_scoped(self):
    added = self.client.post('/api/unsubscribe/manual', headers=self.auth,
                             json={'email': 'Lead@Example.com'})
    rows = self.client.get('/api/unsubscribe/records', headers=self.auth).json['records']
    self.assertEqual(added.status_code, 200)
    self.assertEqual(rows[0]['email'], 'Lead@Example.com')
    self.assertEqual(rows[0]['source'], 'manual')
```

- [ ] **Step 2: Run and verify failure**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python -m unittest tests.test_unsubscribe_management_api -v`

Expected: FAIL because the routes do not exist.

- [ ] **Step 3: Add an idempotent suppression service**

```python
# app/unsubscribe/service.py addition
from datetime import datetime
from .. import db


def add_suppression(subscriber_id, email, source, campaign_id=None,
                    campaign_subject=None, sender_email=None):
    normalized = normalize_email(email)
    existing = UnsubscribeSuppression.query.filter_by(
        subscriber_id=subscriber_id, normalized_email=normalized).first()
    if existing:
        return existing, False
    row = UnsubscribeSuppression(
        subscriber_id=subscriber_id, email=str(email).strip(),
        normalized_email=normalized, unsubscribed_at=datetime.utcnow(),
        source=source, campaign_id=campaign_id,
        campaign_subject=campaign_subject, sender_email=sender_email)
    db.session.add(row)
    db.session.commit()
    return row, True


def serialize_suppression(row):
    return {'id': row.id, 'email': row.email,
            'unsubscribed_at': row.unsubscribed_at.isoformat() + 'Z',
            'source': row.source, 'campaign_subject': row.campaign_subject}
```

- [ ] **Step 4: Add the public and authenticated management routes**

```python
# app/unsubscribe/views.py additions
from cryptography.fernet import InvalidToken
from flask import render_template
from email_validator import EmailNotValidError
from .tokens import decrypt_unsubscribe_token
from .service import add_suppression, serialize_suppression
from ..models import Subscriber, UnsubscribeSuppression


@unsubscribe.route('/unsubscribe', methods=['GET'])
def public_unsubscribe():
    try:
        payload = decrypt_unsubscribe_token(request.args.get('token', ''))
        subscriber = db.session.get(Subscriber, payload['subscriber_id'])
        if not subscriber: raise InvalidToken
        add_suppression(subscriber.id, payload['email'], 'link',
                        payload.get('campaign_id'), payload.get('campaign_subject'),
                        payload.get('sender_email'))
        return render_template('unsubscribe_confirmation.html')
    except (InvalidToken, KeyError, EmailNotValidError, ValueError):
        db.session.rollback()
        return render_template('unsubscribe_error.html'), 400


@unsubscribe.route('/api/unsubscribe/records', methods=['GET'])
def records():
    subscriber, error = _subscriber_or_response()
    if error: return error
    rows = UnsubscribeSuppression.query.filter_by(subscriber_id=subscriber.id).order_by(
        UnsubscribeSuppression.unsubscribed_at.desc(),
        UnsubscribeSuppression.id.desc()).all()
    return jsonify({'records': [serialize_suppression(row) for row in rows]})


@unsubscribe.route('/api/unsubscribe/manual', methods=['POST'])
def manual():
    subscriber, error = _subscriber_or_response()
    if error: return error
    data = request.get_json(silent=True)
    try:
        row, created = add_suppression(subscriber.id, data['email'], 'manual')
    except (TypeError, KeyError, EmailNotValidError):
        return jsonify({'error': 'valid email is required'}), 400
    return jsonify({'created': created, 'record': serialize_suppression(row)})
```

Use static pages that contain no recipient/account/campaign values:

```html
<!-- app/templates/unsubscribe_confirmation.html -->
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Unsubscribed</title></head>
<body><main><h1>You’ve been unsubscribed</h1>
<p>You won’t receive future campaign emails from this sender.</p></main></body></html>
```

```html
<!-- app/templates/unsubscribe_error.html -->
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Unable to unsubscribe</title></head>
<body><main><h1>We couldn’t process this link</h1>
<p>The unsubscribe link is invalid. Please contact the sender for help.</p></main></body></html>
```

- [ ] **Step 5: Run management and preparation tests**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python -m unittest tests.test_unsubscribe_management_api tests.test_unsubscribe_prepare_api -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/unsubscribe app/templates/unsubscribe_confirmation.html app/templates/unsubscribe_error.html tests/test_unsubscribe_management_api.py
git commit -m "feat: add unsubscribe click and management APIs"
```

---

### Task 6: Server documentation and full verification

**Files:**
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/documentation/API_DOCUMENTATION.md`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/README.md`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/CLAUDE.md`

**Interfaces:**
- Documents the exact response header, bearer authentication, payloads, status codes, batch limit, and production secrets consumed by the desktop plan.

- [ ] **Step 1: Document the concrete API examples**

Add request/response examples for:

```http
GET /api/unsubscribe/setting
Authorization: Bearer <session-token>

PUT /api/unsubscribe/setting
Authorization: Bearer <session-token>
Content-Type: application/json
{"enabled": true}

POST /api/unsubscribe/prepare
Authorization: Bearer <session-token>
Content-Type: application/json
{"campaign_id":"...","campaign_subject":"Hello","sender_email":"sales@example.com","kind":"initial","recipients":[{"ref":"0","email":"lead@example.com"}]}

GET /api/unsubscribe/records
POST /api/unsubscribe/manual
GET /unsubscribe?token=<opaque-token>
```

Document `X-Gmonster-Access-Token`, `SUBSCRIBER_TOKEN_MAX_AGE_SECONDS`, `UNSUBSCRIBE_TOKEN_KEYS`, `UNSUBSCRIBE_PUBLIC_BASE_URL`, the 1,000-recipient limit, and the first-key-encrypts/all-keys-decrypt rotation rule.

- [ ] **Step 2: Run the complete server suite**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && python sub.py test`

Expected: all tests PASS with no errors or failures.

- [ ] **Step 3: Run migration and route smoke checks**

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && FLASK_CONFIG=development flask db upgrade`

Run: `cd /Users/moeezmujahid/Projects/gmail_sub && FLASK_CONFIG=development flask routes`

Expected: migration reaches `c1d2e3f4a5b6`; route output includes all five unsubscribe routes.

- [ ] **Step 4: Commit**

```bash
git add documentation/API_DOCUMENTATION.md README.md CLAUDE.md
git commit -m "docs: document unsubscribe API"
```

## Server Completion Gate

Do not start the desktop integration against production until:

- The migration has been applied to a staging database.
- `UNSUBSCRIBE_TOKEN_KEYS` and `UNSUBSCRIBE_PUBLIC_BASE_URL` are configured in staging.
- A staging login returns `Success` plus `X-Gmonster-Access-Token`.
- A prepared staging link opens the confirmation page and suppresses the recipient on the next preparation request.
