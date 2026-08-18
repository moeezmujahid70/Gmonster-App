"""Strict, server-backed unsubscribe API contract."""

from dataclasses import dataclass
from typing import Any, Iterable

from gmonster_api import authenticated_request


BATCH_SIZE = 1000
ALLOWED_STATUSES = {"allowed", "suppressed", "invalid"}


class PreparationError(RuntimeError):
    """Campaign preparation failed before SMTP was allowed to start."""


@dataclass(frozen=True)
class PreparedRecipient:
    ref: str
    email: str
    status: str
    unsubscribe_url: str = ""


def _chunks(values: list[dict], size: int = BATCH_SIZE) -> Iterable[list[dict]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _json(response: Any) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        raise PreparationError("Unsubscribe service returned an invalid response") from exc
    if not isinstance(data, dict):
        raise PreparationError("Unsubscribe service returned an invalid response")
    return data


def prepare_batches(
    assignments: list[dict], campaign_id: str, subject: str, kind: str
) -> tuple[bool, dict[str, PreparedRecipient]]:
    """Prepare all recipients before sending any email.

    Batches are segregated by sender because sender identity is part of the
    server contract. No recipient email or URL is written to logs.
    """
    if kind not in {"initial", "follow_up"}:
        raise PreparationError("Invalid unsubscribe preparation kind")
    if not assignments:
        return False, {}

    grouped: dict[str, list[dict]] = {}
    for row in assignments:
        ref = str(row.get("ref", ""))
        email = str(row.get("email", "")).strip()
        sender_email = str(row.get("sender_email", "")).strip()
        if not ref or not email or not sender_email:
            raise PreparationError("Campaign recipient data is incomplete")
        if any(ref == str(existing.get("ref", "")) for existing in assignments if existing is not row):
            raise PreparationError("Campaign recipient references must be unique")
        grouped.setdefault(sender_email, []).append({**row, "ref": ref, "email": email})

    prepared: dict[str, PreparedRecipient] = {}
    effective_setting = None
    for sender_email, sender_rows in grouped.items():
        for batch in _chunks(sender_rows):
            payload = {
                "campaign_id": campaign_id,
                "campaign_subject": subject,
                "sender_email": sender_email,
                "kind": kind,
                "recipients": [{"ref": row["ref"], "email": row["email"]} for row in batch],
            }
            response = authenticated_request("POST", "api/unsubscribe/prepare", json=payload)
            if response.status_code != 200:
                raise PreparationError("Unable to prepare campaign recipients")
            data = _json(response)
            setting = data.get("insert_unsubscribe_link")
            if not isinstance(setting, bool):
                raise PreparationError("Preparation response omitted setting")
            if effective_setting is not None and setting != effective_setting:
                raise PreparationError("Unsubscribe setting changed during preparation; please retry")
            effective_setting = setting

            results = data.get("results")
            if not isinstance(results, list) or len(results) != len(batch):
                raise PreparationError("Preparation response was incomplete")
            expected = {row["ref"] for row in batch}
            seen: set[str] = set()
            for result in results:
                if not isinstance(result, dict):
                    raise PreparationError("Preparation response was invalid")
                ref = str(result.get("ref", ""))
                status = str(result.get("status", ""))
                if ref not in expected or ref in seen or ref in prepared or status not in ALLOWED_STATUSES:
                    raise PreparationError("Preparation response contained invalid recipients")
                seen.add(ref)
                url = str(result.get("unsubscribe_url") or "")
                if status == "allowed" and setting and not url:
                    raise PreparationError("Allowed recipient omitted unsubscribe URL")
                prepared[ref] = PreparedRecipient(ref, str(result.get("email") or ""), status, url)
            if seen != expected:
                raise PreparationError("Preparation response was incomplete")

    if len(prepared) != len(assignments):
        raise PreparationError("Not every recipient was prepared")
    return bool(effective_setting), prepared


def _response_data(response: Any, failure: str) -> dict:
    if response.status_code != 200:
        raise RuntimeError(failure)
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(failure) from exc
    if not isinstance(data, dict):
        raise RuntimeError(failure)
    return data


def _setting_value(data: dict, failure: str) -> bool:
    for key in ("insert_unsubscribe_link", "enabled"):
        value = data.get(key)
        if isinstance(value, bool):
            return value
    raise RuntimeError(failure)


def get_setting() -> bool:
    return _setting_value(
        _response_data(
            authenticated_request("GET", "api/unsubscribe/setting"),
            "Unable to load unsubscribe setting",
        ),
        "Unable to load unsubscribe setting",
    )


def update_setting(enabled: bool) -> bool:
    return _setting_value(
        _response_data(
            authenticated_request(
                "PUT", "api/unsubscribe/setting", json={"enabled": bool(enabled)}
            ),
            "Unable to save unsubscribe setting",
        ),
        "Unable to save unsubscribe setting",
    )


def get_records() -> list[dict]:
    records = _response_data(authenticated_request("GET", "api/unsubscribe/records"), "Unable to load unsubscribes").get("records")
    if not isinstance(records, list):
        raise RuntimeError("Unable to load unsubscribes")
    return records


def add_manual(email: str) -> dict:
    data = _response_data(authenticated_request("POST", "api/unsubscribe/manual", json={"email": email.strip()}), "Enter a valid email address")
    record = data.get("record")
    if not isinstance(record, dict):
        raise ValueError("Enter a valid email address")
    return record
