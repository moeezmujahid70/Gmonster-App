# Inbox Email Search Design

## Goal

Add a compact search control to the Inbox tab so users can search the emails currently shown in the email list. The control should support Inbox and Sent searches without adding permanent clutter to the existing panel.

## Scope

This feature applies only to the Inbox tab email list. It filters the in-memory email data already loaded into the current inbox group and does not add server-side search, database schema changes, or a separate search page.

## User Experience

The Inbox tab shows a small magnifying-glass button near the existing email filters. By default, only the icon is visible. When the user clicks the icon, a search input appears with placeholder text such as `Search emails`.

Typing in the input filters the current email list immediately. Clearing the input restores the full list for the selected filter. The search remains active when switching between `All`, `Sent`, `Positive`, and `Negative`, but it always searches only inside the selected category.

## Search Behavior

Search is case-insensitive and trims leading/trailing whitespace. Empty or whitespace-only text disables search filtering.

The search checks these fields when present:

- `from_name`
- `from_mail`
- `to_mail`
- `subject`
- `body`

Missing fields are treated as empty strings so malformed or partial email rows do not break rendering.

## Placement

The search control should be inserted dynamically in `main.py` near the existing `All / Sent / Positive / Negative` filter controls in the Inbox left panel. This avoids broad manual edits to generated `gui.py` while keeping the UI close to the email list it controls.

## Data Flow

`inbox_show_changed()` remains the main place where the visible inbox dataset is built.

The filter order should be:

1. Apply the existing selected category filter: `All`, `Sent`, `Positive`, or `Negative`.
2. Apply the existing warmup-email hiding behavior.
3. Apply the new search filter.
4. Sort through the existing `sort_inbox_data()` path.
5. Render through the existing `display_email_in_table()` path.

This keeps search composable with the current filters and sorting behavior.

## Implementation Notes

Add small helper methods on the main window class:

- Create and insert the inbox search widgets.
- Toggle the search input visibility.
- Return the current normalized search text.
- Apply the search filter to a DataFrame.

The search input `textChanged` signal should call `inbox_show_changed()` so results update as the user types. The search icon should focus the input when opening it.

## Error Handling

Search filtering should catch missing columns by using only fields that exist in the DataFrame. If no searchable fields exist, the current filtered DataFrame should be returned unchanged. Any unexpected display errors should continue to flow through the app's existing logging path.

## Testing

Manual verification is sufficient because this repository has no automated GUI test suite for the Inbox tab.

Verify:

- The Inbox tab opens with only the search icon visible.
- Clicking the icon shows and focuses the search field.
- Searching by sender, recipient, subject, and body filters rows.
- Clearing the field restores rows.
- Search works within `All`, `Sent`, `Positive`, and `Negative`.
- Sorting still works while search is active.
- Empty inbox data does not raise errors.
