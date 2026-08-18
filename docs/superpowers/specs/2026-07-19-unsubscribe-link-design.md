# Unsubscribe Link Design

## Overview

Gmonster will add an optional unsubscribe footer to campaign emails and automated follow-ups. A recipient who uses the link will be suppressed from every future campaign sent by any mailbox connected to the same Gmonster login account.

The live server is the source of truth for the account setting, secure unsubscribe links, and suppression records. The desktop app prepares each campaign through the server, keeps the prepared results only in memory, and never stores a persistent local unsubscribe list.

## Scope

Version 1 includes:

- An account-level **Insert unsubscribe link** switch in the desktop Settings tab.
- Fixed unsubscribe wording in plain-text and HTML campaign messages.
- Unsubscribe links in initial campaign messages and automated follow-ups.
- Account-wide suppression across all sending mailboxes under one Gmonster login.
- A public link-click endpoint with confirmation and generic error pages.
- An Unsubscribes management tab with view, search, manual addition, and CSV export.
- Authenticated campaign preparation and unsubscribe-management APIs.

Version 1 does not include:

- Re-subscription or removal from the suppression list.
- A persistent local suppression cache or database.
- Google Sheets integration.
- Cross-account suppression.
- Refreshing the suppression snapshot after an initial campaign has started.
- Active unsubscribe links in test emails.

## Ownership and Boundaries

### Live server

The server owns:

- The account-level footer setting.
- Suppression records and uniqueness enforcement.
- Token encryption and validation.
- Campaign preparation and recipient suppression.
- Manual suppression additions.
- Suppression-list retrieval.
- Public confirmation and error pages.

### Desktop application

The desktop owns:

- The Settings-tab switch.
- Campaign metadata and recipient collection.
- Calls to the campaign-preparation API.
- In-memory prepared-recipient data for the current send.
- Footer insertion in plain-text and HTML MIME alternatives.
- Campaign and follow-up start blocking when preparation fails.
- The Unsubscribes management tab and CSV generation.

No encryption secret is shipped with the desktop executable.

## Account Scope and Identity

Suppression is keyed to the authenticated Gmonster account, not to a device installation or individual sending mailbox. If a recipient unsubscribes from a message sent by one connected Gmail, Yahoo, GMX, Mail.ru, AOL, or other mailbox, the recipient is suppressed from every mailbox connected to that Gmonster login.

The server derives the account identifier from the authenticated session. Account-management APIs must not trust a user ID supplied by the desktop.

The server still records the originating sending mailbox, campaign ID, and campaign subject for auditing.

## Server Data Model

### Account setting

Add `insert_unsubscribe_link`, a Boolean setting associated with the server-side Gmonster account.

- Existing accounts default to `false` when the feature is deployed.
- Accounts registered after deployment default to `true`.
- The setting follows the user across desktop installations.

The exact table or model placement should follow the live server repository's existing account-settings conventions.

### Suppression record

Store one row per Gmonster account and normalized recipient address with these logical fields:

| Field | Purpose |
| --- | --- |
| `id` | Primary key |
| `user_id` | Owning server-side Gmonster account |
| `email` | Original recipient email for display |
| `normalized_email` | Trimmed, case-normalized address used for matching |
| `unsubscribed_at` | Server timestamp of the first successful addition |
| `source` | `link` or `manual` |
| `campaign_id` | Originating campaign UUID, nullable |
| `campaign_subject` | Originating email subject, nullable |
| `sender_email` | Originating sending mailbox, nullable |

Create a unique constraint or unique composite index on `(user_id, normalized_email)`. Repeated link clicks and repeated manual additions return success without creating duplicate rows or replacing the original unsubscribe timestamp.

## Authentication

The existing visible login behavior and response text remain compatible with older desktop versions. A successful login additionally supplies a short-lived access token, preferably through a response header that older clients safely ignore.

The updated desktop keeps the token in memory and sends it as a bearer token to the new setting, campaign-preparation, and management APIs. If the token expires, the desktop obtains a new token and retries once. A second authentication failure returns the user to sign-in.

The public unsubscribe endpoint does not require account authentication because possession of a valid encrypted link is the authorization to suppress that specific recipient.

## API Responsibilities

Endpoint names may be adapted to the live server's route conventions, but the following contracts are required.

### Retrieve setting

An authenticated endpoint returns the current account value of `insert_unsubscribe_link`.

### Update setting

An authenticated endpoint accepts a Boolean value and returns the persisted value. If saving fails, the desktop restores the switch to its previous state and reports the failure.

### Prepare campaign recipients

An authenticated endpoint accepts at most 1,000 recipients per request, along with:

- Campaign UUID.
- Campaign subject.
- Sending mailbox.
- Whether this is an initial campaign or a follow-up run.

Each input recipient has a stable client-side reference so the desktop can match the response without relying on array order.

The server normalizes and deduplicates recipients, removes addresses already suppressed for the authenticated account, and returns an explicit result for every distinct input recipient:

- `allowed`, with a personalized URL when footer insertion is enabled.
- `allowed`, without a URL when footer insertion is disabled.
- `suppressed`.
- `invalid`, with a non-sensitive validation reason.

Each response also returns the effective server-side value of `insert_unsubscribe_link`. Suppression is always enforced, regardless of this value. When a campaign spans multiple batches, every response must report the same setting value; otherwise the desktop aborts preparation and asks the user to retry. This prevents a concurrent setting change on another computer from producing a campaign with mixed footer behavior.

For campaigns larger than 1,000 recipients, the desktop sends sequential or bounded-concurrency batches using the same campaign UUID. It validates all batch responses before sending any email. The successful set of batch responses forms the campaign-start suppression snapshot.

### Retrieve suppressions

An authenticated endpoint returns all suppression rows owned by the account. Version 1 may load the complete list when the Unsubscribes tab opens and search it locally. The response must have a deterministic order, newest unsubscribe first.

### Add manual suppression

An authenticated endpoint accepts one recipient email. It normalizes the address and inserts a `manual` row idempotently. A manual addition appears in the UI only after server confirmation.

### Public unsubscribe endpoint

`GET /unsubscribe?token=<token>` performs the following work:

1. Decrypt and authenticate the token.
2. Reject missing, malformed, or modified tokens without writing data.
3. Insert the suppression row idempotently using the account and recipient from the token.
4. Display a confirmation page for both first and duplicate clicks.

The error page is generic and does not reveal recipient, account, mailbox, or campaign information.

## Token Design

Each delivered recipient receives a different non-expiring token. The authenticated encrypted payload contains only the data required to create and audit the suppression:

- Server-side account identifier.
- Recipient email.
- Campaign UUID.
- Campaign subject.
- Sending mailbox.

The server encryption key remains outside source control and is supplied through the live server's secret-management mechanism. Tokens must provide confidentiality and integrity: the URL must not expose a readable recipient address, and modified payloads must fail validation.

Non-expiring tokens allow recipients to unsubscribe from old messages. Server-side key rotation must preserve the previous decryption key for already delivered links or use versioned keys.

## Desktop Campaign Flow

### Login and setting initialization

1. Complete the existing login flow.
2. Retain the new access token in memory.
3. Fetch the account's unsubscribe-footer setting.
4. Initialize the Settings switch without triggering an update request.
5. Disable the switch and show an unavailable state if the setting cannot be loaded.

When the user changes the switch, the desktop updates the server. The switch retains the new value only after confirmation; otherwise it returns to the previous value and shows an actionable error.

### Initial campaign

1. Generate the existing campaign UUID.
2. Collect the campaign subject, sending mailbox, and recipient rows.
3. Trim, normalize, and deduplicate recipient addresses locally.
4. Prepare recipients through the server in batches of at most 1,000.
5. Validate that each distinct recipient has exactly one result, all batches report the same effective setting, and allowed recipients have links when that setting is enabled.
6. Abort before sending if any request fails or any response is incomplete or malformed.
7. Keep allowed recipient/link mappings in memory.
8. Begin the existing threaded sending flow.

The desktop does not refresh the suppression snapshot after the campaign begins. A recipient who unsubscribes during a long-running campaign is suppressed from the next campaign or follow-up preparation, not from the already prepared send.

### Automated follow-ups

Before each scheduled follow-up run, the desktop performs a new preparation request for the remaining recipients. This fresh snapshot prevents a follow-up from reaching anyone who unsubscribed after the initial campaign.

A failed follow-up preparation sends no messages for that run. The existing scheduler may retry according to its normal failure behavior, but it must not bypass preparation.

## Email Composition

When the setting is enabled, append fixed wording to both alternatives in the campaign's multipart message.

Plain-text form:

```text
Don't want to receive future emails from this sender? Unsubscribe: <personalized URL>
```

HTML form:

```html
<p>Don't want to receive future emails from this sender? <a href="<personalized URL>">Unsubscribe</a>.</p>
```

The HTML URL must be escaped correctly before insertion. The footer is appended after personalization so that content formatting cannot modify the token.

The footer applies to initial campaign messages and automated follow-ups. Test messages do not receive an active unsubscribe URL because clicking it could suppress the test recipient.

## Unsubscribes Management Tab

Add a desktop tab that contains:

- A table showing recipient email, unsubscribe timestamp, source, and campaign subject.
- The existing expanding-search interaction used elsewhere in the app.
- An **Add manually** action with email validation and server confirmation.
- An **Export to CSV** action.

Search operates on the loaded list. CSV export writes the currently filtered rows; clearing the search exports the entire list. Export columns are email, unsubscribe timestamp, source, and campaign subject. Campaign ID and sender mailbox remain server-side audit fields and are not required in the version 1 table or export.

The tab has loading, empty, error, and retry states. It may not show a manual addition until the server confirms it. There is no delete or re-subscribe control.

## Failure Handling

- Campaign preparation is all-or-nothing. No email is sent until all batches are valid.
- A network timeout or server error before a campaign or follow-up stops that send and presents a retry action.
- The desktop never falls back to an old local list or sends without suppression enforcement.
- Invalid recipient rows are reported before sending and are not silently treated as allowed.
- Expired authentication is refreshed once; repeated failure returns the user to sign-in.
- Setting-update failures restore the previous switch value.
- Manual-add failures leave the list unchanged.
- Invalid public tokens produce a generic error page and no database write.
- Duplicate clicks and manual additions return successful idempotent results.

## Privacy and Logging

- Do not log passwords, access tokens, unsubscribe tokens, or complete recipient lists.
- Avoid logging raw recipient addresses in routine success logs.
- Server errors use request or campaign identifiers for diagnosis without exposing token payloads.
- Public pages do not disclose whether a particular address was already suppressed.

## Testing Strategy

### Desktop tests

- Setting retrieval, update success, and rollback after failure.
- Initialization without accidental update requests.
- Recipient normalization and deduplication.
- Preparation batches at 1,000-recipient boundaries.
- Complete campaign abortion when any batch fails or is incomplete.
- Suppression enforcement when footer insertion is off.
- Personalized plain-text and HTML footer insertion when enabled.
- No active footer on test sends.
- Fresh preparation before each follow-up run.
- Management-list rendering, search, idempotent manual-add handling, and filtered CSV export.

### Server tests

- Token issuance and authenticated API access.
- Cross-account access rejection.
- Existing-account default off and new-account default on.
- Recipient normalization and account-scoped uniqueness.
- Campaign preparation with the footer setting on and off.
- Account-wide suppression across multiple sending mailboxes.
- Maximum batch size and complete per-recipient results.
- Token confidentiality, successful decryption, and tamper rejection.
- First and duplicate public link clicks.
- Manual additions and duplicate manual additions.
- Invalid public tokens with no database writes.

### Integration test

Exercise login, setting retrieval, campaign preparation, one public unsubscribe click, and a second campaign preparation that suppresses that recipient. Use mocked SMTP or inspect composed MIME messages; do not send a real email.

## Acceptance Criteria

- The desktop Settings tab has a server-backed account-level toggle.
- Existing accounts start with the toggle off; accounts created after deployment start with it on.
- Enabled initial campaigns and follow-ups contain personalized unsubscribe links in plain-text and HTML content.
- Disabled footer insertion does not disable suppression filtering.
- The public link creates an account-wide suppression and shows a confirmation page.
- Duplicate clicks and manual additions create no duplicate rows or errors.
- Every campaign and follow-up is prepared before sending; preparation failure sends nothing.
- Suppressed recipients are excluded across all sending mailboxes owned by the same Gmonster account.
- The Unsubscribes tab supports view, search, manual addition, and filtered CSV export.
- No local persistent suppression list is created.
- Older desktop versions retain their existing visible login behavior.

## Implementation Prerequisite

The live server repository must be available before implementation planning so its framework, account model, authentication flow, database migration conventions, route structure, and deployment constraints can be incorporated into the implementation plan.
