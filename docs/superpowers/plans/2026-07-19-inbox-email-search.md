# Inbox Email Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact Inbox tab search control that filters the currently selected email list by sender, recipient, subject, and body.

**Architecture:** Put the DataFrame search logic in a small pure helper module so it can be unit tested without PyQt. Keep PyQt widget creation and signal wiring in `main.py`, inserted dynamically near the existing Inbox filters. Feed the search filter into the existing `inbox_show_changed()` pipeline before sorting and rendering.

**Tech Stack:** Python 3.10, PyQt5, pandas, unittest.

## Global Constraints

- The feature applies only to the Inbox tab email list.
- Search filters in-memory email data already loaded into the current inbox group.
- Search does not add server-side search, database schema changes, or a separate search page.
- Search is case-insensitive.
- Empty or whitespace-only search disables search filtering.
- Search checks `from_name`, `from_mail`, `to_mail`, `subject`, and `body` when those fields exist.
- Missing searchable fields are treated as empty strings.
- Search composes with the current `All`, `Sent`, `Positive`, and `Negative` filters.
- Avoid broad manual edits to generated `gui.py`.

---

## File Structure

- Create `inbox_search.py`: owns normalized query handling and pandas DataFrame filtering.
- Create `tests/test_inbox_search.py`: unit tests for search behavior without requiring a Qt app.
- Modify `main.py`: imports the helper, creates dynamic search widgets, wires signals, and applies search in `inbox_show_changed()`.

### Task 1: Search Filtering Helper

**Files:**
- Create: `inbox_search.py`
- Create: `tests/test_inbox_search.py`

**Interfaces:**
- Produces: `normalize_inbox_search_query(query) -> str`
- Produces: `filter_inbox_emails(emails_df, query) -> pandas.DataFrame`
- Consumes: pandas DataFrames with optional columns `from_name`, `from_mail`, `to_mail`, `subject`, and `body`

- [x] **Step 1: Write the failing tests**

Add this test file:

```python
import unittest

import pandas as pd

from inbox_search import filter_inbox_emails, normalize_inbox_search_query


class InboxSearchTest(unittest.TestCase):
    def setUp(self):
        self.emails = pd.DataFrame(
            [
                {
                    "from_name": "Alice Sales",
                    "from_mail": "alice@example.com",
                    "to_mail": "lead@example.com",
                    "subject": "Pricing follow up",
                    "body": "Can we discuss pricing tomorrow?",
                },
                {
                    "from_name": "Bob Ops",
                    "from_mail": "bob@example.com",
                    "to_mail": "sales@example.com",
                    "subject": "Meeting notes",
                    "body": "Internal notes only.",
                },
                {
                    "from_name": "Carol",
                    "from_mail": "carol@example.com",
                    "to_mail": "buyer@example.com",
                    "subject": "Demo",
                    "body": "The buyer asked about onboarding.",
                },
            ]
        )

    def test_normalize_query_strips_and_lowercases(self):
        self.assertEqual(normalize_inbox_search_query("  PriCing  "), "pricing")

    def test_empty_query_returns_original_dataframe(self):
        result = filter_inbox_emails(self.emails, "   ")

        self.assertIs(result, self.emails)

    def test_search_matches_sender_subject_recipient_and_body(self):
        self.assertEqual(
            filter_inbox_emails(self.emails, "alice")["subject"].tolist(),
            ["Pricing follow up"],
        )
        self.assertEqual(
            filter_inbox_emails(self.emails, "sales@example.com")["subject"].tolist(),
            ["Meeting notes"],
        )
        self.assertEqual(
            filter_inbox_emails(self.emails, "pricing")["subject"].tolist(),
            ["Pricing follow up"],
        )
        self.assertEqual(
            filter_inbox_emails(self.emails, "onboarding")["subject"].tolist(),
            ["Demo"],
        )

    def test_missing_searchable_columns_do_not_fail(self):
        partial = pd.DataFrame([{"subject": "Only subject"}, {"date": "2026-07-19"}])

        self.assertEqual(
            filter_inbox_emails(partial, "only")["subject"].tolist(),
            ["Only subject"],
        )
        self.assertEqual(len(filter_inbox_emails(partial, "missing")), 0)

    def test_no_searchable_columns_returns_original_dataframe(self):
        no_search_columns = pd.DataFrame([{"date": "2026-07-19"}])

        result = filter_inbox_emails(no_search_columns, "anything")

        self.assertIs(result, no_search_columns)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_inbox_search -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'inbox_search'`.

- [x] **Step 3: Add the minimal helper implementation**

Create `inbox_search.py` with:

```python
SEARCHABLE_INBOX_FIELDS = ("from_name", "from_mail", "to_mail", "subject", "body")


def normalize_inbox_search_query(query):
    return str(query or "").strip().lower()


def filter_inbox_emails(emails_df, query):
    normalized_query = normalize_inbox_search_query(query)
    if not normalized_query:
        return emails_df

    searchable_fields = [
        field for field in SEARCHABLE_INBOX_FIELDS if field in emails_df.columns
    ]
    if not searchable_fields:
        return emails_df

    matches = None
    for field in searchable_fields:
        field_matches = (
            emails_df[field]
            .fillna("")
            .astype(str)
            .str.lower()
            .str.contains(normalized_query, regex=False, na=False)
        )
        matches = field_matches if matches is None else matches | field_matches

    return emails_df[matches].copy()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_inbox_search -v`

Expected: PASS with 5 tests.

### Task 2: Dynamic Inbox Search UI

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `GUI.frame`, `GUI.verticalLayout_17`, `GUI.widget_3`, and the existing Inbox filter widgets.
- Produces: `GUI.pushButton_inbox_search`, `GUI.lineEdit_inbox_search`, and `GUI.widget_inbox_search`.
- Produces: methods `setup_inbox_search()`, `toggle_inbox_search()`, and `get_inbox_search_text()`.

- [x] **Step 1: Import the helper and line edit widget support**

In `main.py`, add:

```python
from inbox_search import filter_inbox_emails, normalize_inbox_search_query
```

Extend the `PyQt5.QtWidgets` import list with:

```python
QLineEdit,
```

- [x] **Step 2: Call setup during main window initialization**

In the constructor after `self.setup_inbox_date_header()`, add:

```python
self.setup_inbox_search()
```

- [x] **Step 3: Add the dynamic widget methods**

Add these methods near `setup_inbox_date_header()`:

```python
    def setup_inbox_search(self):
        if hasattr(GUI, "lineEdit_inbox_search"):
            return

        search_widget = QtWidgets.QWidget(GUI.frame)
        search_widget.setObjectName("widget_inbox_search")
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 4, 0, 4)
        search_layout.setSpacing(6)

        search_button = QPushButton(search_widget)
        search_button.setObjectName("pushButton_inbox_search")
        search_button.setCursor(Qt.PointingHandCursor)
        search_button.setFixedSize(34, 34)
        search_button.setToolTip("Search emails")
        search_button.setText("")
        search_button.setFlat(True)
        search_button.setStyleSheet(
            "QPushButton { border: none; color: #555; }"
            "QPushButton:hover { color: #000; background-color: #e6eaf2; }"
        )
        if qta is not None:
            search_button.setIcon(qta.icon("fa5s.search", color="#555"))
            search_button.setIconSize(QtCore.QSize(16, 16))
        else:
            search_button.setText("Search")

        search_input = QLineEdit(search_widget)
        search_input.setObjectName("lineEdit_inbox_search")
        search_input.setPlaceholderText("Search emails")
        search_input.setClearButtonEnabled(True)
        search_input.setMinimumHeight(34)
        search_input.setStyleSheet(
            "QLineEdit { background-color: #fff; border: 1px solid #d6dce8; "
            "border-radius: 4px; padding: 6px 10px; color: #222; }"
            "QLineEdit:focus { border-color: #9aa8c0; }"
        )
        search_input.hide()

        search_layout.addWidget(search_button)
        search_layout.addWidget(search_input)
        GUI.verticalLayout_17.insertWidget(1, search_widget)

        GUI.widget_inbox_search = search_widget
        GUI.pushButton_inbox_search = search_button
        GUI.lineEdit_inbox_search = search_input

        search_button.clicked.connect(self.toggle_inbox_search)
        search_input.textChanged.connect(self.inbox_show_changed)

    def toggle_inbox_search(self):
        search_input = GUI.lineEdit_inbox_search
        should_show = not search_input.isVisible()
        search_input.setVisible(should_show)
        if should_show:
            search_input.setFocus()
            search_input.selectAll()
        else:
            search_input.clear()

    def get_inbox_search_text(self):
        if not hasattr(GUI, "lineEdit_inbox_search"):
            return ""
        return normalize_inbox_search_query(GUI.lineEdit_inbox_search.text())
```

- [x] **Step 4: Run an import smoke check**

Run: `python -m py_compile main.py inbox_search.py`

Expected: PASS with no output.

### Task 3: Integrate Search With Inbox Filtering

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `filter_inbox_emails(emails_df, query) -> pandas.DataFrame`
- Consumes: `self.get_inbox_search_text() -> str`
- Produces: `inbox_show_changed()` applies category, warmup, search, then sort/render.

- [x] **Step 1: Apply search in the inbox data pipeline**

In `inbox_show_changed()`, after the warmup filtering block and before `self.sort_inbox_data(self.option)`, add:

```python
        search_text = self.get_inbox_search_text()
        if search_text and not var.inbox_data[var.inbox_group].empty:
            var.inbox_data[var.inbox_group] = filter_inbox_emails(
                var.inbox_data[var.inbox_group],
                search_text,
            )
```

- [x] **Step 2: Run the search unit tests**

Run: `python -m unittest tests.test_inbox_search -v`

Expected: PASS with 5 tests.

- [x] **Step 3: Run a compile check**

Run: `python -m py_compile main.py inbox_search.py`

Expected: PASS with no output.

- [x] **Step 4: Manually inspect the final diff**

Run: `git diff -- main.py inbox_search.py tests/test_inbox_search.py`

Expected: Diff only contains the inbox search helper, tests, dynamic search widgets, and the `inbox_show_changed()` integration.

- [x] **Step 5: Commit implementation**

Run:

```bash
git add main.py inbox_search.py tests/test_inbox_search.py docs/superpowers/plans/2026-07-19-inbox-email-search.md
git commit -m "Add inbox email search"
```
