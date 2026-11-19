"""Read optional overrides from the process environment or a local .env file."""

import os


def read_env_file(path):
    """Parse simple KEY=VALUE lines; missing or unreadable files yield {}."""
    values = {}
    try:
        with open(path, encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key.startswith("export "):
                    key = key[len("export "):].strip()
                values[key] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def get_setting(key, env_file_path=None):
    """Return a non-empty value from os.environ, else from the .env file, else None."""
    value = os.environ.get(key, "").strip()
    if value:
        return value
    if env_file_path:
        value = read_env_file(env_file_path).get(key, "").strip()
        if value:
            return value
    return None


def normalize_api_url(url):
    """Ensure the API base URL ends with a slash, since endpoints are appended."""
    return url if url.endswith("/") else url + "/"
