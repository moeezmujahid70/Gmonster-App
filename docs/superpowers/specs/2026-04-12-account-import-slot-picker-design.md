# Account Import Slot Picker — Design Spec
**Date:** 2026-04-12

## Context

When a user clicks "Import" in the Database tab, the app auto-loads all available rows from `group_a.xlsx` into Group A first, then fills Group B with whatever slots remain under the plan limit. This makes it impossible to intentionally split slots — e.g., load 10 into A and 10 into B when the plan limit is 20.

The fix: show a slot-picker dialog at import time so the user explicitly sets how many accounts to load per group before loading begins.

---

## Data & Constraints

- **Plan limit** — single integer fetched from `_fetch_accounts_limit()` (`database.py:499`). Represents the combined A + B ceiling. Default 20 if API unreachable.
- **No per-group caps** — user can assign all slots to A, all to B, or any split. Constraint: `a_slots + b_slots <= plan_limit`.
- **Sheet underflow** — if the user requests more than the sheet contains, load all available rows silently (no error).
- **Checkbox state** — if Group A or Group B is unchecked in the DB tab, its spinbox is shown but disabled (greyed out, value locked at 0).
- **Replace semantics** — import always clears and replaces; no appending.

---

## Design

### 1. `get_sheet_counts()` — `database.py`

New helper (add near `_fetch_accounts_limit`, around line 517):

```python
def get_sheet_counts() -> dict:
    """Return {'group_a': int, 'group_b': int} row counts from the xlsx sheets.
    Returns 0 for any sheet that is missing or unreadable."""
```

- Reads `group_a.xlsx` and `group_b.xlsx` via pandas (same paths as `file_to_db`)
- Filters to rows with a non-empty `PROXY:PORT` column (same filter as the real import)
- Returns `{'group_a': N, 'group_b': M}` — fast, no DB writes

### 2. `file_to_db(a_limit, b_limit)` — `database.py:519`

Add two required int parameters `a_limit` and `b_limit`. These replace the internal `remaining_slots` auto-computation:

- Remove the `_fetch_accounts_limit()` call inside `file_to_db` (limit is now determined by the caller/dialog)
- Group A: truncate to `min(len(group_a), a_limit)` instead of `remaining_slots`
- Group B: truncate to `min(len(group_b), b_limit)` instead of `remaining_slots`
- Remove `total_loaded` tracking (no longer needed)
- Keep the existing `limit_messages` list for any truncation due to sheet underflow (optional informational message)

### 3. `load_db(a_limit, b_limit)` — `database.py:950`

Add `a_limit` and `b_limit` params, pass them through to `file_to_db(a_limit, b_limit)`.

### 4. `ImportSlotsDialog` — `main.py`

New `QDialog` subclass added near `load_db()` (around line 2516). Opened on the main thread before spawning the import thread.

**Constructor receives:**
- `plan_limit: int`
- `sheet_counts: dict` — `{'group_a': N, 'group_b': M}`
- `group_a_enabled: bool` — from `var.db_file_loading_config["group_a"]`
- `group_b_enabled: bool` — from `var.db_file_loading_config["group_b"]`

**UI layout:**
```
┌─ Import Accounts ────────────────────────────────────┐
│  Plan limit: 20 accounts total                       │
│                                                      │
│  Group A  [spinbox 0–20]   (Sheet has 15 available)  │
│  Group B  [spinbox 0–20]   (Sheet has 12 available)  │
│                                                      │
│  Total selected: 10 / 20                            │
│                                                      │
│                          [Cancel]  [Import]          │
└──────────────────────────────────────────────────────┘
```

**Behaviour:**
- Both spinboxes have range `0` to `plan_limit`
- If a group's checkbox was unchecked, its spinbox is disabled and locked at `0`
- `valueChanged` on either spinbox updates the "Total selected: X / 20" label
- If total > plan_limit: label turns red, Import button disabled
- If total <= plan_limit: label is normal, Import button enabled
- `result()` exposes `(a_slots, b_slots)` after accept

### 5. `load_db()` method — `main.py:2516`

Replace the simple `confirm("Are you sure?")` with:

1. Fetch plan limit + sheet counts (fast, on main thread — both are reads)
2. Open `ImportSlotsDialog`
3. If accepted: spawn `Thread(target=database.load_db, args=(a_slots, b_slots), daemon=True).start()`
4. If cancelled: do nothing

---

## Files Modified

| File | What changes |
|------|-------------|
| `database.py` | Add `get_sheet_counts()` ~line 517; modify `file_to_db()` sig + internals ~line 519; modify `load_db()` sig ~line 950 |
| `main.py` | Add `ImportSlotsDialog` class; modify `load_db()` method ~line 2516 |

No changes to `gui.py`, `gui.ui`, `var.py`, or any other file.

---

## Verification

1. Run the app: `python var.py`
2. Navigate to the Database tab
3. Click Import — the slot-picker dialog should appear showing the plan limit and sheet row counts
4. Enter a split (e.g., 5 for A, 5 for B) — total label should update live
5. Try entering a total > plan limit — Import button should disable
6. Click Import — database loads only the requested number of rows per group
7. Verify the DB table shows the correct counts via the radio button group views
8. Repeat with one group unchecked — its spinbox should be greyed out and show 0
