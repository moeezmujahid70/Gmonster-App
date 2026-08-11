# WooCommerce Renewal Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically extend a linked Gmonster subscriber by one calendar month when WooCommerce Subscriptions records a successful automatic or manual renewal payment.

**Architecture:** A small WordPress plugin listens only to WooCommerce Subscriptions’ `woocommerce_subscription_renewal_payment_complete` action. It signs and sends the WooCommerce subscription ID, renewal order ID, and billing email to a PythonAnywhere Flask endpoint. The backend records an admin-managed subscription-ID-to-subscriber link, validates the signed request, creates an idempotent renewal-event record, and extends the linked subscriber’s `end_date` exactly once.

**Tech Stack:** Python 3.9, Flask, Flask-SQLAlchemy, Alembic/Flask-Migrate, SQLite or the configured production SQLAlchemy database, unittest, PHP for WordPress, WooCommerce 10.4.4, WooCommerce Subscriptions 7.9.0, WordPress HTTP API, WordPress Action Scheduler.

## Global Constraints

- Scope is successful renewal payments only; do not automate new subscriptions, cancellation, suspension, or desktop registration.
- Process both automatic and manual renewal payments, because WooCommerce’s renewal-complete action is fired for both.
- Do not treat billing or PayPal email as the permanent identity; the WooCommerce subscription ID is the permanent link key.
- Accept only authenticated requests signed with `WOOCOMMERCE_WEBHOOK_SECRET`; keep that secret in PythonAnywhere runtime configuration and WordPress `wp-config.php`, never in source control or the desktop app.
- Use `renewal_order_id` as the idempotency key; a retry must never add a second month.
- Extend from `max(subscriber.end_date, UTC today)` by one calendar month, preserving calendar-month behavior (for example, January 31 becomes February 28 or 29).
- If a renewal is not linked and cannot be safely auto-linked, record it as `unmapped`, return HTTP 202, and do not change any subscriber.
- Auto-link only an already-active subscriber whose normalized Gmonster email exactly equals the signed WooCommerce billing email and whose subscription ID is not linked elsewhere.
- WordPress core, WooCommerce, and WooCommerce Subscriptions must not be edited; deploy a separate plugin.

---

## File Structure

### PythonAnywhere backend repository: `/Users/moeezmujahid/Projects/gmail_sub`

- Modify `config.py`: add webhook-secret and signature-age configuration.
- Modify `app/models.py`: add the subscription-link and renewal-event persistence models plus the `Subscriber` relationships.
- Create `app/woocommerce.py`: keep calendar-month arithmetic, request validation, HMAC validation, email normalization, and renewal processing outside Flask routes.
- Modify `app/verify/__init__.py`: register the new renewal route module.
- Create `app/verify/woocommerce.py`: expose the signed public renewal endpoint.
- Modify `app/main/views.py`: add authenticated linkage endpoints and expose current link IDs in the existing pending/active-user JSON responses.
- Modify `app/templates/pending_request.html`: require an admin-entered WooCommerce subscription ID when activating a pending subscriber.
- Modify `app/templates/active_user.html`: display current linked ID(s) and provide an explicit “Link WooCommerce subscription” action for an existing active subscriber.
- Create `migrations/versions/c2a1b3d4e5f6_add_woocommerce_renewal_tables.py`: create the two new tables and their unique/index constraints.
- Create `tests/test_woocommerce_renewals.py`: cover the backend renewal and linkage behavior.

### WordPress integration source in the Gmonster repository

- Create `integrations/wordpress/gmonster-renewal-sync/gmonster-renewal-sync.php`: plugin entry point, signed delivery, and retry scheduling.
- Create `integrations/wordpress/gmonster-renewal-sync/README.md`: installation, configuration, and troubleshooting instructions.

## Interfaces

### WordPress to backend request

`POST https://enzim.pythonanywhere.com/verify/woocommerce/renewal`

Headers:

```text
Content-Type: application/json
X-Gmonster-Timestamp: <Unix timestamp in seconds>
X-Gmonster-Signature: <lowercase SHA-256 HMAC>
```

Body, serialized exactly once before signing:

```json
{
  "subscription_id": 8853,
  "renewal_order_id": 8964,
  "billing_email": "customer@example.com"
}
```

Signature message:

```text
<timestamp>.<raw request body bytes>
```

Responses:

```json
{"status":"processed","subscriber_id":42,"end_date":"2026-09-11"}
{"status":"duplicate","subscriber_id":42,"end_date":"2026-09-11"}
{"status":"unmapped","renewal_order_id":8964}
```

Use HTTP 200 for `processed` and `duplicate`, HTTP 202 for `unmapped`, HTTP 400 for malformed JSON/data, HTTP 401 for missing/invalid/stale signature, and HTTP 503 only when the webhook secret is absent from server configuration.

### Admin linkage requests

`POST /activate_user/<subscriber_id>`

```json
{
  "end_date": "2026-09-11",
  "woocommerce_subscription_id": 8853
}
```

`POST /subscriber/<subscriber_id>/woocommerce-links`

```json
{
  "woocommerce_subscription_id": 8853
}
```

Both routes require the existing Flask-Login admin session. They reject blank, non-numeric, zero/negative, or already-linked subscription IDs with HTTP 400 or 409 and a JSON message.

---

### Task 1: Add persistence models and a reversible database migration

**Files:**
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/models.py`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/migrations/versions/c2a1b3d4e5f6_add_woocommerce_renewal_tables.py`
- Test: `/Users/moeezmujahid/Projects/gmail_sub/tests/test_woocommerce_renewals.py`

**Consumes:** Existing `Subscriber` model and Flask-SQLAlchemy `db` instance.

**Produces:** `WooCommerceSubscriptionLink`, `WooCommerceRenewalEvent`, and `Subscriber.woocommerce_subscription_links` for use by admin routes and the public renewal endpoint.

- [ ] **Step 1: Write the model persistence tests.**

```python
def test_subscription_id_is_unique_and_can_link_to_a_subscriber(self):
    subscriber = Subscriber(email='owner@example.com', active=True,
                            end_date=date(2026, 8, 1))
    db.session.add(subscriber)
    db.session.commit()

    link = WooCommerceSubscriptionLink(
        subscriber_id=subscriber.id,
        woocommerce_subscription_id=8853,
    )
    db.session.add(link)
    db.session.commit()

    self.assertEqual(subscriber.woocommerce_subscription_links.first().woocommerce_subscription_id, 8853)


def test_renewal_order_id_is_unique(self):
    event = WooCommerceRenewalEvent(
        woocommerce_subscription_id=8853,
        renewal_order_id=8964,
        status='unmapped',
    )
    db.session.add(event)
    db.session.commit()

    duplicate = WooCommerceRenewalEvent(
        woocommerce_subscription_id=8853,
        renewal_order_id=8964,
        status='unmapped',
    )
    db.session.add(duplicate)
    with self.assertRaises(IntegrityError):
        db.session.commit()
```

- [ ] **Step 2: Run the new tests and verify they fail because the models do not exist.**

Run:

```bash
python -m unittest tests.test_woocommerce_renewals -v
```

Expected: `ImportError` for `WooCommerceSubscriptionLink` and `WooCommerceRenewalEvent`.

- [ ] **Step 3: Add the models.**

Add these model contracts to `app/models.py`:

```python
class WooCommerceSubscriptionLink(db.Model):
    __tablename__ = 'woocommerce_subscription_links'
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('subscribers.id'), nullable=False, index=True)
    woocommerce_subscription_id = db.Column(db.BigInteger, nullable=False, unique=True, index=True)
    linked_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    subscriber = db.relationship('Subscriber', back_populates='woocommerce_subscription_links')


class WooCommerceRenewalEvent(db.Model):
    __tablename__ = 'woocommerce_renewal_events'
    id = db.Column(db.Integer, primary_key=True)
    woocommerce_subscription_id = db.Column(db.BigInteger, nullable=False, index=True)
    renewal_order_id = db.Column(db.BigInteger, nullable=False, unique=True, index=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('subscribers.id'), nullable=True, index=True)
    status = db.Column(db.String(16), nullable=False)
    resulting_end_date = db.Column(db.Date(), nullable=True)
    received_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
```

Add this relationship inside `Subscriber`:

```python
woocommerce_subscription_links = db.relationship(
    'WooCommerceSubscriptionLink', back_populates='subscriber',
    lazy='dynamic', cascade='all, delete-orphan'
)
```

- [ ] **Step 4: Write the explicit Alembic migration.**

Set the migration identifiers exactly as follows:

```python
revision = 'c2a1b3d4e5f6'
down_revision = '456a945560f6'
```

In `upgrade()`, create `woocommerce_subscription_links` and `woocommerce_renewal_events` with the columns above, foreign keys to `subscribers.id`, and unique constraints on `woocommerce_subscription_id` and `renewal_order_id`. In `downgrade()`, drop `woocommerce_renewal_events` first and then `woocommerce_subscription_links`.

- [ ] **Step 5: Run the model tests and the existing test suite.**

Run:

```bash
python -m unittest discover -v
```

Expected: all existing tests and the new persistence tests pass.

- [ ] **Step 6: Commit the backend persistence changes.**

```bash
git add app/models.py migrations/versions/c2a1b3d4e5f6_add_woocommerce_renewal_tables.py tests/test_woocommerce_renewals.py
git commit -m "feat: persist WooCommerce subscription links and renewal events"
```

### Task 2: Implement signed, idempotent renewal processing

**Files:**
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/config.py`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/app/woocommerce.py`
- Create: `/Users/moeezmujahid/Projects/gmail_sub/app/verify/woocommerce.py`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/verify/__init__.py`
- Test: `/Users/moeezmujahid/Projects/gmail_sub/tests/test_woocommerce_renewals.py`

**Consumes:** Task 1 models and the existing `/verify` blueprint.

**Produces:** `POST /verify/woocommerce/renewal`, `add_one_calendar_month()`, and `process_renewal()`.

- [ ] **Step 1: Add failing endpoint tests.**

Add test helpers that serialize compact JSON and sign the exact request body:

```python
def signed_headers(body: bytes, timestamp: int) -> dict:
    signature = hmac.new(
        b'test-webhook-secret',
        str(timestamp).encode('ascii') + b'.' + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        'Content-Type': 'application/json',
        'X-Gmonster-Timestamp': str(timestamp),
        'X-Gmonster-Signature': signature,
    }
```

Cover these cases with individual test methods: a linked renewal extends once; a repeated renewal order returns `duplicate` without a second extension; an active exact-email match auto-links and processes; a non-matching email returns `unmapped` without extending; invalid and stale signatures return HTTP 401; and month-end arithmetic maps January 31, 2026 to February 28, 2026.

For the month-end test, assert `add_one_calendar_month(date(2026, 1, 31)) == date(2026, 2, 28)`.

- [ ] **Step 2: Run the endpoint tests and verify they fail because the route is missing.**

Run:

```bash
python -m unittest tests.test_woocommerce_renewals -v
```

Expected: endpoint tests fail with HTTP 404.

- [ ] **Step 3: Add runtime configuration.**

Add to `Config` in `config.py`:

```python
WOOCOMMERCE_WEBHOOK_SECRET = os.environ.get('WOOCOMMERCE_WEBHOOK_SECRET')
WOOCOMMERCE_WEBHOOK_MAX_AGE_SECONDS = 300
```

Set `WOOCOMMERCE_WEBHOOK_SECRET = 'test-webhook-secret'` in the test setup after creating the testing app. Production must obtain the value only from its environment.

- [ ] **Step 4: Implement the pure service functions in `app/woocommerce.py`.**

Define these interfaces: `normalize_email(value: str) -> str`; `add_one_calendar_month(start_date: date) -> date`; `verify_webhook_signature(raw_body: bytes, timestamp_header: Optional[str], signature_header: Optional[str]) -> bool`; `validate_renewal_payload(payload: object) -> Optional[dict]`; and `process_renewal(subscription_id: int, renewal_order_id: int, billing_email: str) -> tuple[dict, int]`.

`process_renewal()` must execute in one transaction:

1. Return a stored processed event as `{"status": "duplicate", "subscriber_id": existing_event.subscriber_id, "end_date": existing_event.resulting_end_date.isoformat()}, 200` if `renewal_order_id` already has status `processed`.
2. Find a `WooCommerceSubscriptionLink` by `subscription_id`.
3. If no link exists, find exactly one `Subscriber` with `active=True` and a normalized email equal to `billing_email`; create a link only when that ID is still unlinked.
4. If still unlinked, insert an event with `status='unmapped'`, commit, and return `{"status": "unmapped", "renewal_order_id": renewal_order_id}, 202`.
5. Calculate `new_end_date = add_one_calendar_month(max(subscriber.end_date, date.today()))`.
6. Assign `subscriber.end_date = new_end_date`, insert/update the event with `status='processed'`, `subscriber_id`, `resulting_end_date`, and `processed_at=datetime.utcnow()`, then commit.
7. On `IntegrityError` from a concurrent duplicate order, roll back, load the existing event, and return `duplicate` without touching the expiry date.

- [ ] **Step 5: Implement the public route.**

In `app/verify/woocommerce.py`, register:

```python
@verify.route('/woocommerce/renewal', methods=['POST'])
def receive_woocommerce_renewal():
    raw_body = request.get_data(cache=True)
    if not current_app.config['WOOCOMMERCE_WEBHOOK_SECRET']:
        return jsonify({'message': 'Webhook secret is not configured'}), 503
    if not verify_webhook_signature(
        raw_body,
        request.headers.get('X-Gmonster-Timestamp'),
        request.headers.get('X-Gmonster-Signature'),
    ):
        return jsonify({'message': 'Invalid webhook signature'}), 401
    payload = request.get_json(silent=True)
    validated = validate_renewal_payload(payload)
    if validated is None:
        return jsonify({'message': 'Invalid renewal payload'}), 400
    response, status_code = process_renewal(**validated)
    return jsonify(response), status_code
```

Read `request.get_data(cache=True)` before JSON parsing, reject missing server secret with HTTP 503, verify the signature and five-minute timestamp window, parse JSON, require positive integer `subscription_id` and `renewal_order_id`, require a non-empty string `billing_email`, then return `jsonify(payload), status_code` from `process_renewal()`.

Import the module from `app/verify/__init__.py`:

```python
from . import views, woocommerce
```

- [ ] **Step 6: Run all backend tests.**

Run:

```bash
python -m unittest discover -v
```

Expected: all endpoint, model, and existing tests pass.

- [ ] **Step 7: Commit the renewal endpoint.**

```bash
git add config.py app/woocommerce.py app/verify/__init__.py app/verify/woocommerce.py tests/test_woocommerce_renewals.py
git commit -m "feat: process signed WooCommerce renewal events"
```

### Task 3: Add the admin linkage workflow

**Files:**
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/main/views.py`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/templates/pending_request.html`
- Modify: `/Users/moeezmujahid/Projects/gmail_sub/app/templates/active_user.html`
- Test: `/Users/moeezmujahid/Projects/gmail_sub/tests/test_woocommerce_renewals.py`

**Consumes:** Task 1 link model and existing Flask-Login-protected admin screens.

**Produces:** An admin can activate a pending user and link a subscription in one action, or link an existing active user later.

Define `activate_and_link_subscriber(subscriber_id: int, payload: Optional[dict]) -> Response` and `link_existing_subscriber(subscriber_id: int, payload: Optional[dict]) -> Response` in `app/main/views.py`. Both helpers own all JSON validation, duplicate-ID handling, transaction rollback, and JSON response creation used by the thin route functions below.

- [ ] **Step 1: Write failing admin-route tests.**

Use a logged-in test client and add four individual tests: activation creates a link; an active subscriber receives an additional link; the same ID cannot be linked to two subscribers; and a non-numeric ID returns HTTP 400.

The successful activation request is:

```python
response = self.client.post(
    f'/activate_user/{subscriber.id}',
    json={'end_date': '2026-09-11', 'woocommerce_subscription_id': 8853},
)
self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run the admin-route tests and verify they fail with HTTP 404.**

Run:

```bash
python -m unittest tests.test_woocommerce_renewals -v
```

Expected: the new admin endpoints are not registered yet.

- [ ] **Step 3: Implement the JSON admin routes.**

In `app/main/views.py`, add these Flask-Login-protected routes:

```python
@main.route('/activate_user/<int:subscriber_id>', methods=['POST'])
@login_required
def activate_user_with_woocommerce_link(subscriber_id):
    return activate_and_link_subscriber(subscriber_id, request.get_json(silent=True))

@main.route('/subscriber/<int:subscriber_id>/woocommerce-links', methods=['POST'])
@login_required
def create_woocommerce_subscription_link(subscriber_id):
    return link_existing_subscriber(subscriber_id, request.get_json(silent=True))
```

Both routes must parse `request.get_json(silent=True)`, validate a `YYYY-MM-DD` end date for activation, validate a positive numeric `woocommerce_subscription_id`, return HTTP 404 when the subscriber does not exist, and return HTTP 409 when another link owns that ID. Activation must set `active=True`, set `end_date` to the supplied date, create the link, and commit as one database transaction.

Extend `/pending_request/all-users` and `/active_users` JSON records with:

```python
'woocommerce_subscription_ids': [
    link.woocommerce_subscription_id
    for link in item.woocommerce_subscription_links.order_by(
        WooCommerceSubscriptionLink.woocommerce_subscription_id
    )
]
```

- [ ] **Step 4: Update the pending-user activation modal.**

In `pending_request.html`:

1. Change the modal title to `Activate and link WooCommerce subscription`.
2. Add a required numeric input with ID `woocommerce_subscription_id`, label `WooCommerce Subscription ID`, `min="1"`, and placeholder `Example: 8853`.
3. Replace the URL-parameter request with this JSON request:

```javascript
request.open('POST', '/activate_user/' + e.dataset.id, true);
request.setRequestHeader('Content-Type', 'application/json');
request.send(JSON.stringify({
    end_date: datepicker.value,
    woocommerce_subscription_id: Number(
        document.getElementById('woocommerce_subscription_id').value
    )
}));
```

4. Display the server’s JSON `message` on non-200 responses and do not reload the page.

- [ ] **Step 5: Update the active-user screen.**

In `active_user.html`:

1. Add a `WooCommerce Subscription ID` table column that renders a comma-separated list or `Not linked`.
2. Add a `Link WooCommerce subscription` button for every active subscriber.
3. Add a dedicated modal with a required numeric `woocommerce_subscription_id` field.
4. Submit JSON to `/subscriber/<subscriber_id>/woocommerce-links` and reload only after a 200 response.

- [ ] **Step 6: Run all tests and perform a local admin smoke test.**

Run:

```bash
python -m unittest discover -v
FLASK_CONFIG=development python sub.py
```

Expected: tests pass; the pending activation modal requires a WordPress subscription number; the active-users table displays saved link IDs; duplicate IDs show a clear error and do not change either subscriber.

- [ ] **Step 7: Commit the admin linkage workflow.**

```bash
git add app/main/views.py app/templates/pending_request.html app/templates/active_user.html tests/test_woocommerce_renewals.py
git commit -m "feat: let admins link Gmonster users to WooCommerce subscriptions"
```

### Task 4: Build the independent WordPress renewal-sync plugin

**Files:**
- Create: `/Users/moeezmujahid/Projects/emailSaas/Gmonster/integrations/wordpress/gmonster-renewal-sync/gmonster-renewal-sync.php`
- Create: `/Users/moeezmujahid/Projects/emailSaas/Gmonster/integrations/wordpress/gmonster-renewal-sync/README.md`

**Consumes:** Task 2 endpoint and the shared endpoint/secret constants defined in WordPress configuration.

**Produces:** A deployable plugin that sends one signed event after every successful WooCommerce renewal payment and retries transient delivery failures.

- [ ] **Step 1: Create the plugin header and fail-safe configuration guard.**

The PHP file must declare:

```php
/**
 * Plugin Name: Gmonster Renewal Sync
 * Description: Sends successful WooCommerce subscription renewals to the Gmonster backend.
 * Version: 1.0.0
 * Requires Plugins: woocommerce, woocommerce-subscriptions
 */
```

Require all of `ABSPATH`, `GMONSTER_RENEWAL_ENDPOINT`, and `GMONSTER_RENEWAL_WEBHOOK_SECRET`; if any are absent, return without registering the renewal hook and call `error_log()` without printing the secret.

- [ ] **Step 2: Implement signed event delivery.**

Register this action with two arguments:

```php
add_action(
    'woocommerce_subscription_renewal_payment_complete',
    'gmonster_sync_queue_renewal',
    10,
    2
);
```

`gmonster_sync_queue_renewal( WC_Subscription $subscription, WC_Order $renewal_order )` must schedule `gmonster_sync_dispatch_renewal` with the numeric subscription/order IDs. `gmonster_sync_dispatch_renewal( int $subscription_id, int $renewal_order_id, int $attempt = 0 )` must reload the objects, serialize this exact payload using `wp_json_encode()`:

```php
array(
    'subscription_id'  => $subscription->get_id(),
    'renewal_order_id' => $renewal_order->get_id(),
    'billing_email'    => $renewal_order->get_billing_email(),
)
```

Use `time()` as the timestamp, calculate:

```php
hash_hmac('sha256', $timestamp . '.' . $body, GMONSTER_RENEWAL_WEBHOOK_SECRET)
```

and call `wp_remote_post()` with a 15-second timeout and the three interface headers from this plan.

- [ ] **Step 3: Add delivery outcome behavior and retry scheduling.**

Handle outcomes exactly:

- HTTP 200: finish silently; backend processed the renewal or accepted a duplicate.
- HTTP 202: add a private renewal-order note: `Gmonster renewal sync: subscription is not linked to a Gmonster account.` Do not retry.
- HTTP 400 or 401: add a private renewal-order note: `Gmonster renewal sync: request rejected by backend. Check plugin configuration.` Do not retry.
- `WP_Error` or HTTP 500–599: schedule one retry with Action Scheduler using delays `[300, 900, 3600, 21600, 86400]` seconds for attempts `0` through `4`; after the fifth failed delivery, add a private renewal-order note: `Gmonster renewal sync: delivery failed after five retries. Review server logs.`

Use the Action Scheduler group `gmonster-renewal-sync`. If Action Scheduler functions are not available, log the failure with `error_log()` and add the final failure note rather than throwing a PHP error.

- [ ] **Step 4: Write installation and configuration documentation.**

In the plugin README, include:

```php
define(
    'GMONSTER_RENEWAL_ENDPOINT',
    'https://enzim.pythonanywhere.com/verify/woocommerce/renewal'
);
define('GMONSTER_RENEWAL_WEBHOOK_SECRET', 'generate-a-new-64-character-random-secret');
```

State that these constants belong in `wp-config.php` before the `/* That's all, stop editing! */` line, that the same secret must be set as `WOOCOMMERCE_WEBHOOK_SECRET` in PythonAnywhere, and that neither value may be committed or pasted into support tickets.

- [ ] **Step 5: Run PHP lint and package the plugin.**

Run:

```bash
php -l integrations/wordpress/gmonster-renewal-sync/gmonster-renewal-sync.php
cd integrations/wordpress && zip -r ../../dist/gmonster-renewal-sync.zip gmonster-renewal-sync
```

Expected: `No syntax errors detected`; the ZIP contains a top-level `gmonster-renewal-sync` directory.

- [ ] **Step 6: Commit plugin source, not the secret or generated ZIP.**

```bash
git add integrations/wordpress/gmonster-renewal-sync/gmonster-renewal-sync.php integrations/wordpress/gmonster-renewal-sync/README.md
git commit -m "feat: send WooCommerce renewal events to Gmonster"
```

### Task 5: Deploy safely and verify the end-to-end renewal path

**Files:**
- Modify at deployment: PythonAnywhere runtime environment configuration and the production database.
- Modify at deployment: `gmonster.co/wp-config.php` and the WordPress Plugins page.

**Consumes:** Tasks 1–4.

**Produces:** A live, observable renewal integration with a clear rollback path.

- [ ] **Step 1: Back up production before changing it.**

From the PythonAnywhere database management/console tools, export the `subscribers` table and create a full database backup. From cPanel File Manager, download copies of `wp-config.php` and the current `wp-content/plugins` directory listing. Store the backup outside the web root.

- [ ] **Step 2: Deploy the backend before installing the WordPress plugin.**

On PythonAnywhere, update the backend source using its existing deployment method, set the runtime variable `WOOCOMMERCE_WEBHOOK_SECRET` to a newly generated 64-character random value, run the explicit migration, then reload the web app from the Web tab. Confirm the endpoint rejects an unsigned `POST` with HTTP 401; this verifies the route is live without changing any subscription.

- [ ] **Step 3: Configure and install the WordPress plugin.**

Add the endpoint and the same secret to `gmonster.co/wp-config.php`. Upload `gmonster-renewal-sync.zip` in WordPress Admin at `Plugins → Add New Plugin → Upload Plugin`, activate `Gmonster Renewal Sync`, and confirm no PHP warning appears in the WordPress admin.

- [ ] **Step 4: Create a controlled backend linkage.**

In the Gmonster PythonAnywhere admin panel, select a non-production test subscriber, enter a future end date, enter that test WooCommerce `Subscription #` in the new activation/link field, and save. Confirm the linked ID appears in the active-user table.

- [ ] **Step 5: Test a successful renewal in the payment provider’s sandbox or a staging store.**

Use a WooCommerce staging site and gateway sandbox subscription. Complete one renewal payment. Confirm:

1. A `woocommerce_subscription_renewal_payment_complete` event runs.
2. WordPress receives HTTP 200 from the backend.
3. Exactly one `woocommerce_renewal_events` row exists for that renewal order ID with `status='processed'`.
4. The linked Gmonster subscriber’s `end_date` advanced by exactly one calendar month.
5. Replaying the same signed request returns `duplicate` and does not advance the end date again.

- [ ] **Step 6: Test unmapped and failed-delivery behavior.**

With a staging renewal whose subscription ID is not linked and whose billing email does not exactly match an active Gmonster subscriber, confirm HTTP 202, one `unmapped` event row, no subscriber date change, and a private WooCommerce order note. Temporarily point the staging plugin endpoint to a non-routable URL, confirm Action Scheduler schedules retries, then restore the endpoint and confirm a retry processes exactly once.

- [ ] **Step 7: Roll back if any production verification fails.**

Deactivate `Gmonster Renewal Sync` in WordPress, reload the PythonAnywhere web app after reverting the deployed backend revision, and restore the database backup only if the migration or data validation introduced an error. Do not delete WooCommerce orders, subscriptions, or WordPress core/plugin files.

- [ ] **Step 8: Commit deployment documentation only after the staging verification passes.**

```bash
git add docs/superpowers/plans/2026-08-11-woocommerce-renewal-automation.md
git commit -m "docs: add WooCommerce renewal automation deployment plan"
```

## Plan Self-Review

- Scope coverage: Tasks 1–3 implement durable manual admin linkage and exact-email fallback; Task 2 implements signed, idempotent, calendar-month renewal extension; Task 4 emits successful automatic and manual renewal events; Task 5 verifies production behavior and rollback.
- No scope expansion: no new-purchase automation, cancellation automation, Resend, or desktop registration work is included.
- Type consistency: `woocommerce_subscription_id` is a positive integer everywhere; `renewal_order_id` is the event idempotency key; endpoint path and HMAC message match in the backend and plugin tasks.
- Security coverage: shared secret stays server/config-only, timing-safe comparison is required by the service helper, stale messages are rejected, and external input is validated before database writes.
