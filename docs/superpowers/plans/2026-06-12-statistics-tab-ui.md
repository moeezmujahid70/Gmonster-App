# Statistics Tab UI — KPI Chip Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the oversized label+value-box layout in the statistics metric tabs with compact two-column KPI chip cards that look clean and professional.

**Architecture:** Four methods in `main.py` are refactored. Each metric becomes a `QFrame` chip containing a small gray label on top and the value/input widget below, arranged in a 2-column `QGridLayout`. Section headers gain a colored dot badge. No business logic, no other files touched.

**Tech Stack:** PyQt5 (QFrame, QVBoxLayout, QGridLayout, QLabel, QDoubleSpinBox, QLineEdit)

---

### Task 1: Update `_statistics_section_header` to show colored dot badges

**Files:**
- Modify: `main.py:2373-2380`

No unit test exists for PyQt5 widget construction — verify visually when the app runs in Task 5.

- [ ] **Step 1: Replace `_statistics_section_header` with the new implementation**

In `main.py`, replace lines 2373–2380:

```python
    def _statistics_section_header(self, text, kind="calc"):
        container = QtWidgets.QWidget()
        container.setStyleSheet("QWidget { background: transparent; }")
        h = QtWidgets.QHBoxLayout(container)
        h.setContentsMargins(0, 6, 0, 4)
        h.setSpacing(6)
        dot = QtWidgets.QLabel()
        dot.setFixedSize(8, 8)
        color = "#6366f1" if kind == "manual" else "#028fc3"
        dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        lbl = QtWidgets.QLabel(text.upper())
        lbl.setStyleSheet(
            "QLabel { color: #374151; font-family: Arial; font-size: 10px; "
            "font-weight: bold; letter-spacing: 0.7px; background: transparent; border: none; }"
        )
        h.addWidget(dot)
        h.addWidget(lbl)
        h.addStretch()
        return container
```

---

### Task 2: Refactor `_add_statistics_manual_field` to chip layout

**Files:**
- Modify: `main.py:2382-2403`

- [ ] **Step 1: Replace `_add_statistics_manual_field` with chip implementation**

In `main.py`, replace lines 2382–2403:

```python
    def _add_statistics_manual_field(self, layout, row, column, key, label, kind):
        chip = QtWidgets.QFrame()
        chip.setStyleSheet(
            "QFrame { background: #fafafa; border: 1px solid #d1d5db; border-radius: 8px; }"
            "QFrame QLabel { background: transparent; border: none; }"
        )
        chip_layout = QtWidgets.QVBoxLayout(chip)
        chip_layout.setContentsMargins(10, 8, 10, 8)
        chip_layout.setSpacing(4)
        lbl = QtWidgets.QLabel(label)
        lbl.setStyleSheet(
            "QLabel { color: #6b7280; font-family: Arial; font-size: 10px; font-weight: 600; }"
        )
        chip_layout.addWidget(lbl)
        if kind == "text":
            field = QtWidgets.QLineEdit()
            field.setStyleSheet(
                "QLineEdit { border: none; background: transparent; padding: 0; "
                "font-family: Arial; font-size: 13px; font-weight: 600; color: #374151; }"
            )
            field.editingFinished.connect(self.refresh_statistics)
        else:
            field = QtWidgets.QDoubleSpinBox()
            field.setMaximum(1000000000)
            field.setDecimals(2 if kind in ("currency", "decimal") else 0)
            field.setSingleStep(100 if kind == "currency" else 1)
            if kind == "currency":
                field.setPrefix("$ ")
            if kind == "percent":
                field.setSuffix(" %")
                field.setMaximum(100)
            field.setStyleSheet(
                "QDoubleSpinBox { border: none; background: transparent; padding: 0; "
                "font-family: Arial; font-size: 13px; font-weight: 600; color: #374151; }"
                "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button "
                "{ width: 18px; border: none; background: transparent; }"
            )
            field.editingFinished.connect(self.refresh_statistics)
        self.statistics_manual_fields[key] = field
        chip_layout.addWidget(field)
        layout.addWidget(chip, row, column)
```

---

### Task 3: Refactor `_add_statistics_calculated_field` to chip layout

**Files:**
- Modify: `main.py:2405-2415`

- [ ] **Step 1: Replace `_add_statistics_calculated_field` with chip implementation**

In `main.py`, replace lines 2405–2415:

```python
    def _add_statistics_calculated_field(self, layout, row, column, key, label, kind):
        chip = QtWidgets.QFrame()
        chip.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }"
            "QFrame QLabel { background: transparent; border: none; }"
        )
        chip_layout = QtWidgets.QVBoxLayout(chip)
        chip_layout.setContentsMargins(10, 8, 10, 8)
        chip_layout.setSpacing(3)
        lbl = QtWidgets.QLabel(label)
        lbl.setStyleSheet(
            "QLabel { color: #6b7280; font-family: Arial; font-size: 10px; font-weight: 600; }"
        )
        value = QtWidgets.QLabel("0")
        value.setStyleSheet(
            "QLabel { color: #0369a1; font-family: Arial; font-size: 15px; font-weight: 700; }"
        )
        chip_layout.addWidget(lbl)
        chip_layout.addWidget(value)
        self.statistics_calculated_labels[key] = (value, kind)
        layout.addWidget(chip, row, column)
```

---

### Task 4: Update `_build_statistics_metric_tabs` to use 2-column grid

**Files:**
- Modify: `main.py:2338-2371`

- [ ] **Step 1: Replace `_build_statistics_metric_tabs` with 2-column version**

In `main.py`, replace lines 2338–2371:

```python
    def _build_statistics_metric_tabs(self, parent):
        tabs = QtWidgets.QTabWidget(parent)
        tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #dde3ea; background: #ffffff; "
            "border-radius: 8px; } "
            "QTabBar::tab { background: #eef2f6; color: #344054; padding: 9px 14px; "
            "font-family: Arial; font-size: 11px; font-weight: bold; border-top-left-radius: 6px; "
            "border-top-right-radius: 6px; margin-right: 3px; } "
            "QTabBar::tab:selected { background: #ffffff; color: #028fc3; }"
        )
        for section_title, manual_fields, calculated_fields in self._statistics_sections():
            page = QtWidgets.QWidget()
            layout = QtWidgets.QGridLayout(page)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setHorizontalSpacing(8)
            layout.setVerticalSpacing(8)
            for column in range(2):
                layout.setColumnStretch(column, 1)
            row = 0
            if manual_fields:
                manual_header = self._statistics_section_header("Manual inputs", kind="manual")
                layout.addWidget(manual_header, row, 0, 1, 2)
                row += 1
                for index, (key, label, kind) in enumerate(manual_fields):
                    self._add_statistics_manual_field(layout, row + index // 2, index % 2, key, label, kind)
                row += (len(manual_fields) + 1) // 2
            if calculated_fields:
                calc_header = self._statistics_section_header("Calculated metrics", kind="calc")
                layout.addWidget(calc_header, row, 0, 1, 2)
                row += 1
                for index, (key, label, kind) in enumerate(calculated_fields):
                    self._add_statistics_calculated_field(layout, row + index // 2, index % 2, key, label, kind)
            tabs.addTab(page, section_title)
        return tabs
```

---

### Task 5: Verify visually and commit

**Files:**
- No changes — run and inspect

- [ ] **Step 1: Run the app and open the Statistics tab**

```bash
cd /Users/moeezmujahid/Projects/emailSaas/Gmonster
source .venv/bin/activate
python var.py
```

Navigate to **Statistics** in the left sidebar. Click through each tab (Deliverability, Lead Quality, Campaign, Replies, Sales/ROI, Warm-up) and confirm:
- Metrics appear as compact two-column chip cards
- Calculated chips have a blue value (`#0369a1`)
- Manual input chips have a light gray background with clean input fields
- Section headers show a colored dot (indigo for Manual, blue for Calculated) + uppercase label
- No `"- manual"` or `"- calculated"` suffixes anywhere
- Labels are short and readable
- Spacing is tight and professional

- [ ] **Step 2: Run existing tests to confirm no regressions**

```bash
cd /Users/moeezmujahid/Projects/emailSaas/Gmonster
source .venv/bin/activate
python -m pytest tests/test_statistics_report.py -v
```

Expected: all tests pass (these test calculation logic, not UI widgets).

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: refactor statistics metric tabs to compact two-column KPI chip layout"
```
