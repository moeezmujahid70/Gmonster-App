# Statistics Tab UI Improvement — Design Spec

**Date:** 2026-06-12  
**Status:** Approved

## Problem

The current statistics metric tabs use an oversized label + value-box layout with verbose "- manual" / "- calculated" suffixes on every field label, excessive vertical spacing, and large rounded value boxes that waste space. The result looks sparse and unprofessional.

## Design Decision: Option C — Two-column KPI Chips

Each metric is displayed as a compact chip card (QFrame) with:
- Small label text (10px, gray `#6b7280`) on top
- Bold value or input widget below (13–15px)
- Chips arranged in a 2-column grid
- Tight internal padding (10px horizontal, 8px vertical)
- 8px gap between chips

### Visual Differentiation

| Type | Chip background | Chip border | Value color |
|---|---|---|---|
| Manual input | `#fafafa` | `1px #d1d5db` | `#374151` (dark gray) |
| Calculated | `#f8fafc` | `1px #e2e8f0` | `#0369a1` (blue) |

Section headers use a small colored dot (8×8px circle) + uppercase label:
- Manual section dot: `#6366f1` (indigo)
- Calculated section dot: `#028fc3` (blue)

### Label Cleanup

Remove all `"- manual"` and `"- calculated"` suffixes. Labels become clean, short strings (e.g. "Leads Sourced" not "Leads Sourced - calculated").

### Spacing

Grid changes from 4-column to 2-column. Spacing: 8px vertical, 8px horizontal between chips. Section header has 6px bottom margin.

## Files Changed

- `main.py`: `_build_statistics_metric_tabs`, `_add_statistics_manual_field`, `_add_statistics_calculated_field`, `_statistics_section_header`

## Out of Scope

- KPI card strip at top of statistics page (separate frame, not the tabs)
- Controls panel (date range, product price)
- PDF export report rendering
- Tab bar styling
