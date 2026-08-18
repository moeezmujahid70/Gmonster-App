"""Display state calculation for campaign progress."""


def campaign_progress_state(sent: int, total: int, stopped: bool) -> tuple[int, str, str]:
    """Return a safe progress value and a terminal label for empty sends."""
    if total <= 0:
        return 0, "0/0", "No eligible recipients"
    value = int(sent / total * 100)
    if value >= 100:
        status = "Finished"
    elif stopped:
        status = "Stopped"
    else:
        status = "Sending"
    return value, "{}/{}".format(sent, total), status
