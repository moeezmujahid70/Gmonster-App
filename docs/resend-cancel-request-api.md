# Resend Cancellation Request API

The desktop app already calls:

```http
POST /verify/request_subscription_cancel
```

The backend should use Resend for this endpoint. Do not put the Resend API key
in the desktop app.

## Environment

```env
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxx
RESEND_FROM_EMAIL="Gmonster <noreply@gmonster.co>"
CANCEL_REQUEST_TO=order@gmonster.co
```

## Expected Request Body

```json
{
  "email": "client@example.com",
  "user_id": "desktop-or-user-id",
  "requested_at": "2026-06-19T18:00:00+00:00",
  "message": "Client client@example.com requested manual subscription cancellation at 2026-06-19T18:00:00+00:00."
}
```

## Python Resend Send

```python
import os
import resend

resend.api_key = os.environ["RESEND_API_KEY"]


def send_subscription_cancel_request(payload):
    client_email = payload.get("email", "unknown")
    user_id = payload.get("user_id", "N/A")
    requested_at = payload.get("requested_at", "N/A")

    body = f"""Hello Admin,

The following client requested subscription cancellation from the Gmonster app:

Client Email: {client_email}
User ID: {user_id}
Requested At: {requested_at}

Please cancel this subscription manually.

Regards,
Gmonster App
"""

    return resend.Emails.send({
        "from": os.getenv("RESEND_FROM_EMAIL", "Gmonster <noreply@gmonster.co>"),
        "to": [os.getenv("CANCEL_REQUEST_TO", "order@gmonster.co")],
        "subject": f"Subscription Cancellation Request - {client_email}",
        "text": body,
    })
```

Return a JSON success response after Resend accepts the email:

```json
{
  "success": true,
  "message": "Your cancellation request has been sent. Our team will process it manually."
}
```
