"""AI email generation: request options and the server-side AI client.

The server (POST ``verify/ai_response``) owns provider selection and fallback, so
this module never talks to an AI provider and never holds provider API keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests

import var

# The server may keep working after the client gives up, so a timed-out request
# is reported to the user instead of being resent behind their back.

_GENERIC_ERROR = "The AI service failed temporarily. Please try again later."
_EMPTY_ANSWER_ERROR = "The AI returned an empty response. Please try again."
_UNEXPECTED_RESPONSE_ERROR = (
    "The server sent an unexpected response. Please try again in a moment."
)
_TIMEOUT_ERROR = (
    "The AI is taking longer than expected, and the server may still be working on "
    "your request. Please wait a moment before sending it again."
)
_CONNECTION_ERROR = "Network error. Please check your internet connection and try again."


def email_reasoning_options(model: str) -> dict[str, str]:
    """Reduce GPT-5 reasoning without passing unsupported options to other models."""
    if model.startswith("gpt-5") and "-chat-" not in model:
        return {"reasoning_effort": "low"}
    return {}


class AIRequestError(Exception):
    """A failed AI request, with text that is safe to show to the user."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.error_code = error_code
        self.status_code = status_code


@dataclass(frozen=True)
class AIResult:
    answer: str
    status: str = "ok"
    source: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


def _friendly_error_message(status_code: Optional[int], error_code: Optional[str]) -> str:
    if status_code == 504 or error_code == "ai_upstream_timeout":
        return "The AI is taking too long to respond. Please try again."
    if status_code == 429 or error_code == "ai_rate_limited":
        return "The AI service is busy right now. Please wait a moment and retry."
    if status_code == 503 or error_code == "ai_connection_error":
        return "The server could not reach the AI service. Please try again."
    return _GENERIC_ERROR


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _error_from_payload(data: dict, status_code: Optional[int]) -> AIRequestError:
    error_code = _text(data.get("error_code")) or _text(data.get("error"))
    message = (
        _text(data.get("message"))
        or _text(data.get("error"))
        or _friendly_error_message(status_code, error_code)
    )
    return AIRequestError(
        message,
        retryable=data.get("retryable") is True,
        error_code=error_code,
        status_code=status_code,
    )


def _json_object(response) -> Optional[dict]:
    try:
        data = response.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def ai_error_from_exception(error: Exception) -> AIRequestError:
    """Convert any exception into an AIRequestError without leaking internals."""
    if isinstance(error, AIRequestError):
        return error
    if isinstance(error, requests.exceptions.Timeout):
        return AIRequestError(_TIMEOUT_ERROR)
    if isinstance(error, requests.exceptions.ConnectionError):
        return AIRequestError(_CONNECTION_ERROR)
    return AIRequestError(_GENERIC_ERROR)


def request_server_ai(prompt: str) -> AIResult:
    """Ask the server to generate an email. Sends exactly one request."""
    try:
        response = requests.post(
            var.api + "verify/ai_response",
            json={
                "email": var.login_email,
                "password": var.login_password,
                "machine_uuid": var.login_machine_uuid,
                "processor_id": var.login_processor_id,
                "prompt": prompt,
            },
            timeout=var.API_AI_TIMEOUT,
        )
    except Exception as error:
        raise ai_error_from_exception(error) from error

    data = _json_object(response)
    if not response.ok:
        if data is None:
            # Gateways (502/504, maintenance pages) answer with HTML, not JSON.
            raise AIRequestError(
                _friendly_error_message(response.status_code, None),
                status_code=response.status_code,
            )
        raise _error_from_payload(data, response.status_code)

    if data is None:
        raise AIRequestError(_UNEXPECTED_RESPONSE_ERROR, status_code=response.status_code)

    status = data.get("status")
    has_error_fields = any(data.get(key) for key in ("error", "error_code", "message"))
    if (status is not None and status != "ok") or (status is None and has_error_fields):
        raise _error_from_payload(data, response.status_code)

    answer = data.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise AIRequestError(_EMPTY_ANSWER_ERROR, status_code=response.status_code)
    return AIResult(
        answer=answer,
        status=status or "ok",
        source=_text(data.get("source")),
        provider=_text(data.get("provider")),
        model=_text(data.get("model")),
    )
