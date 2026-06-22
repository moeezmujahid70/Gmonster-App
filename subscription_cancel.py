from datetime import datetime, timezone


CANCEL_REQUEST_PATH = "api/subscription/cancel-request"


def build_cancel_request_url(api_base):
    return f"{api_base.rstrip('/')}/{CANCEL_REQUEST_PATH}"


def build_cancel_request_payload(name, email, user_id, plan, requested_at=None):
    if requested_at is None:
        requested_at = datetime.now(timezone.utc)
    return {
        "name": name.strip(),
        "email": email.strip(),
        "user_id": user_id.strip(),
        "plan": plan.strip(),
        "requested_at": requested_at.isoformat(),
    }
