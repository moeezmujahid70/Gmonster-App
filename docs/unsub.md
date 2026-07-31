
# Feature Spec: Unsubscribe Link

## Overview

Add an optional unsubscribe link to outgoing campaign emails, controlled by a switch in the Settings tab. Recipients who click the link are permanently excluded from all future campaign sends for that user account. Enforcement is automatic — no manual list management required by the user.

## 1. Settings Tab — Toggle

- Add a switch labeled **"Insert unsubscribe link"** to the Settings tab
- Default state: off (or on, TBD by product owner)
- State persists per user account
- When ON: every campaign email sent by this user has an unsubscribe link appended to the bottom of the email body
- When OFF: no link is inserted, no behavior change from current app

## 2. Database Schema

New table: `unsubscribes`

| Column          | Type                      | Notes                                                               |
| --------------- | ------------------------- | ------------------------------------------------------------------- |
| id              | integer, PK               | auto-increment                                                      |
| user_id         | integer, FK               | references the Gmoster account that owns the campaign               |
| email           | string                    | recipient's email address                                           |
| campaign_id     | integer, FK, nullable     | which campaign triggered the unsubscribe, if applicable             |
| unsubscribed_at | timestamp                 | when the unsubscribe occurred                                       |
| source          | enum:`link`, `manual` | how the address was added (clicked link vs. manually added by user) |

Index: composite index on `(user_id, email)` for fast lookup at send time.

## 3. Unsubscribe Link Generation

- When the "Insert unsubscribe link" setting is ON, generate a unique per-recipient token at send time
- Token encodes/maps to: `user_id`, recipient `email`, `campaign_id`
- Token should not be reversible/guessable (signed token or opaque ID mapped server-side — do not base64-encode the raw email)
- Link format: `https://<gmoster-domain>/unsubscribe?token=<token>`
- Insert link into a footer section of the email body (e.g., "Don't want future emails? Unsubscribe here.")

## 4. Unsubscribe Endpoint

`GET /unsubscribe?token=<token>`

Behavior:

1. Decode/validate token
2. If invalid/expired token → show a generic error page, no data written
3. If valid → insert row into `unsubscribes` (`user_id`, `email`, `campaign_id`, `unsubscribed_at = now()`, `source = 'link'`)
4. Handle duplicate clicks idempotently (if already unsubscribed, don't insert a duplicate row, just show the confirmation page)
5. Show recipient a confirmation page (e.g., "You've been unsubscribed and won't receive further emails from this sender.")

## 5. Send-Time Enforcement

- Before sending any campaign, filter the recipient list against the `unsubscribes` table for the sending `user_id`
- Exclude any recipient whose email exists in that user's unsubscribe list
- This check applies regardless of whether the "Insert unsubscribe link" setting is currently on or off (once someone is unsubscribed, they stay excluded even if the sender later toggles the setting off)

## 6. Unsubscribes Management Tab (UI)

New tab/page in the app:

- Table view of all unsubscribed addresses for the logged-in user: email, unsubscribed_at, source (link/manual), campaign (if available)
- Search input (reuse the same expanding search icon component used elsewhere in the app)
- "Add manually" button/form — lets the user add an email address directly (for opt-outs received via reply or other channels), inserts with `source = 'manual'`
- "Export to CSV" button — exports the current list

## 7. Out of Scope

- No re-subscribe flow (not requested)
- No integration with Google Sheets (decided against per client discussion — internal DB only)
- No cross-account unsubscribe (unsubscribing from one Gmoster user's campaigns does not affect other users' ability to email that address)

## Acceptance Criteria

- [ ] Settings tab has working toggle, persisted per user
- [ ] When enabled, unsubscribe link appears in sent campaign emails
- [ ] Clicking the link records the unsubscribe and shows a confirmation page
- [ ] Unsubscribed addresses are automatically excluded from all future campaign sends for that user
- [ ] Unsubscribes tab supports view, search, manual add, and CSV export
- [ ] Duplicate link clicks do not create duplicate records or errorsyeshcbee
