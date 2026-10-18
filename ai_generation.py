"""Request options for latency-sensitive email generation."""


def email_reasoning_options(model: str) -> dict[str, str]:
    """Reduce GPT-5 reasoning without passing unsupported options to other models."""
    if model.startswith("gpt-5") and "-chat-" not in model:
        return {"reasoning_effort": "low"}
    return {}
