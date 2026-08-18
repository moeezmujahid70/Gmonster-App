from datetime import datetime, timezone

from subscription_cancel import (
    build_cancel_request_payload,
    build_cancel_request_url,
)


def test_build_cancel_request_url_uses_configured_backend_base():
    assert (
        build_cancel_request_url("https://backend.example.com/")
        == "https://backend.example.com/api/subscription/cancel-request"
    )
    assert (
        build_cancel_request_url("https://backend.example.com")
        == "https://backend.example.com/api/subscription/cancel-request"
    )


def test_build_cancel_request_payload_matches_api_contract():
    requested_at = datetime(2026, 6, 19, 12, 34, 56, tzinfo=timezone.utc)

    payload = build_cancel_request_payload(
        name="Jane Customer",
        email="jane@example.com",
        user_id="desktop-123",
        plan="Pro",
        requested_at=requested_at,
    )

    assert payload == {
        "name": "Jane Customer",
        "email": "jane@example.com",
        "user_id": "desktop-123",
        "plan": "Pro",
        "requested_at": "2026-06-19T12:34:56+00:00",
    }


def test_build_cancel_request_payload_trims_optional_fields():
    payload = build_cancel_request_payload(
        name="  Jane Customer  ",
        email="  ",
        user_id=" desktop-123 ",
        plan=" ",
        requested_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )

    assert payload["name"] == "Jane Customer"
    assert payload["email"] == ""
    assert payload["user_id"] == "desktop-123"
    assert payload["plan"] == ""
