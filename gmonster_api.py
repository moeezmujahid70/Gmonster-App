"""Authenticated desktop requests to the Gmonster server.

The bearer token is intentionally kept only in ``var`` memory; neither this
module nor its callers log it.
"""

from typing import Any, Optional

import requests

import var


TOKEN_HEADER = "X-Gmonster-Access-Token"


def capture_access_token(response: requests.Response) -> bool:
    """Retain a non-empty login response token in memory."""
    token = str(response.headers.get(TOKEN_HEADER, "")).strip()
    if not token:
        return False
    var.api_access_token = token
    return True


def _login_payload() -> dict[str, str]:
    return {
        "email": var.login_email,
        "password": var.login_password,
        "machine_uuid": var.login_machine_uuid,
        "processor_id": var.login_processor_id,
        "version": var.version,
        "type": "main",
    }


def refresh_access_token(session: Any = requests) -> bool:
    """Refresh once through the existing compatible login endpoint."""
    response = session.post(
        var.api + "verify/login",
        json=_login_payload(),
        timeout=var.API_TIMEOUT,
    )
    return (
        response.status_code == 200
        and response.text == "Success"
        and capture_access_token(response)
    )


def authenticated_request(
    method: str,
    path: str,
    *,
    json: Optional[dict] = None,
    timeout: Optional[tuple] = None,
    session: Any = requests,
) -> requests.Response:
    """Send one authorized request and retry exactly once after a 401."""
    def send() -> requests.Response:
        return session.request(
            method,
            var.api + path.lstrip("/"),
            json=json,
            headers={"Authorization": "Bearer {}".format(var.api_access_token)},
            timeout=timeout or var.API_TIMEOUT,
        )

    response = send()
    if response.status_code == 401 and refresh_access_token(session=session):
        response = send()
    return response
