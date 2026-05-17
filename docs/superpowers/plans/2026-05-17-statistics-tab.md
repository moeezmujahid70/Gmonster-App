# Statistics Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a polished white-label Statistics tab with campaign KPIs, potential earnings, logo branding, and PDF export.

**Architecture:** Keep analytics logic in a new standalone module so `main.py` only handles PyQt wiring. Add the Statistics page dynamically at startup to avoid broad generated UI churn, while preserving the existing sidebar and stacked-widget patterns.

**Tech Stack:** Python 3.10, PyQt5, pandas, unittest, existing CSV reports in `data/email_results/`, existing app config in `data/gmonster_config/config.json`.

---

### Task 1: Statistics Calculator

**Files:**
- Create: `statistics_report.py`
- Create: `tests/test_statistics_report.py`

- [ ] Write `unittest` coverage for CSV parsing, repeated header skipping, date filtering, sentiment classification, follow-up counts, and potential earnings.
- [ ] Implement `StatisticsCalculator` and `StatisticsSummary` with no GUI dependency.
- [ ] Use `data/email_results/report.csv` and `data/email_results/followup_report.csv` as optional sources; missing files produce zero counts.
- [ ] Treat `STATUS == "sent"` as successful sent/follow-up rows.
- [ ] Count replies from `var.inbox_data_table`-style DataFrames where `is_sent == False`.
- [ ] Match existing inbox sentiment semantics: blacklist words force negative; neutral counts as positive.
- [ ] Run `python3 -m unittest tests.test_statistics_report`.

### Task 2: Statistics Page UI

**Files:**
- Modify: `main.py`

- [ ] Add a dynamic Statistics sidebar item immediately after `Auto-reply`.
- [ ] Switch sidebar navigation from fragile fixed indices to item text for existing pages/actions.
- [ ] Build an Executive Report-style page with date controls, logo controls, product price input, KPI cards, chart preview, Refresh, and Export PDF.
- [ ] Persist `statistics.product_price`, `statistics.logo_path`, and `statistics.date_filter` in the existing config file through `update_config_json()`.
- [ ] Refresh statistics on tab entry and button click.

### Task 3: PDF Export

**Files:**
- Modify: `statistics_report.py`
- Modify: `main.py`

- [ ] Add pure-PyQt PDF export using `QPrinter`/`QPainter`, matching the Executive Client Report visual direction.
- [ ] Include optional uploaded logo in the PDF header.
- [ ] Export an A4 portrait report with title, date range, KPI cards, chart sections, and footer timestamp.
- [ ] Show a clear empty-data report instead of failing when no campaign data exists.

### Task 4: Verification

**Files:**
- Modify as needed: `main.py`, `statistics_report.py`

- [ ] Run `python3 -m unittest tests.test_statistics_report`.
- [ ] Run `python3 -m py_compile main.py gui.py statistics_report.py tests/test_statistics_report.py`.
- [ ] If PyQt PDF classes are unavailable in the local environment, keep calculator tests passing and report the PDF verification limitation.
- [ ] Manually inspect the new tab by launching `python3 var.py` when dependencies are available.
