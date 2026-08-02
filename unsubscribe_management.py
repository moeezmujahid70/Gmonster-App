"""Pure helpers for the unsubscribes management view."""

import csv
import os


COLUMNS = ("email", "unsubscribed_at", "source", "campaign_subject")


def default_export_path(downloads_folder: str) -> str:
    """Provide a user-facing default without writing into the app folder."""
    return os.path.join(downloads_folder, "unsubscribes.csv")


def filter_records(records: list[dict], query: str) -> list[dict]:
    needle = str(query or "").strip().lower()
    if not needle:
        return list(records)
    return [row for row in records if any(needle in str(row.get(column) or "").lower() for column in COLUMNS)]


def export_records(path: str, records: list[dict]) -> int:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({column: row.get(column) or "" for column in COLUMNS} for row in records)
    return len(records)
