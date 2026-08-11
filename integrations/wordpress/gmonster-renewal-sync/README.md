# Gmonster Renewal Sync

This WordPress plugin sends a signed event to the Gmonster PythonAnywhere backend after every successful WooCommerce Subscriptions renewal payment. It processes both automatic and manual renewals. It does not process a first purchase, cancellation, or suspension.

## Configure before activating

Generate one new 64-character random secret. Add these constants to `wp-config.php` before the line containing `That's all, stop editing!`:

```php
define(
    'GMONSTER_RENEWAL_ENDPOINT',
    'https://enzim.pythonanywhere.com/verify/woocommerce/renewal'
);
define(
    'GMONSTER_RENEWAL_WEBHOOK_SECRET',
    'replace-this-with-the-new-random-secret'
);
```

Set the same value as the PythonAnywhere web app environment variable:

```text
WOOCOMMERCE_WEBHOOK_SECRET
```

Do not commit, email, or paste the secret into a ticket or chat.

## Install

1. Zip the `gmonster-renewal-sync` directory, keeping it as the top-level directory in the ZIP.
2. In WordPress Admin, open `Plugins → Add New Plugin → Upload Plugin`.
3. Upload the ZIP and activate **Gmonster Renewal Sync**.
4. In PythonAnywhere, link every new Gmonster subscriber to their WooCommerce `Subscription #` before that subscriber's next renewal.

## Delivery outcomes

- HTTP 200: renewal was processed or was already processed; no order note is created.
- HTTP 202: the WooCommerce subscription is not linked to a Gmonster subscriber; the plugin adds a private renewal-order note and does not retry.
- HTTP 400 or 401: the request or secret configuration is wrong; the plugin adds a private renewal-order note and does not retry.
- Network failures and HTTP 5xx: the plugin retries after 5 minutes, 15 minutes, 1 hour, 6 hours, and 24 hours. After the final failure, it adds a private order note.

## Testing

Use a staging store and payment-gateway sandbox. Link a test Gmonster subscriber to the staging WooCommerce subscription ID, complete one renewal, and verify that the backend moves that subscriber's end date forward by one calendar month exactly once.
