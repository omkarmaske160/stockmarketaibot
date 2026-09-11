"""
Lets the Streamlit dashboard read and write files (watchlist.txt,
price_targets.json) directly in your GitHub repo, so changes you make on
the dashboard are picked up by the hourly checker automatically.

Needs a GitHub Personal Access Token with "Contents: Read and write"
permission on your repo, stored as the GITHUB_TOKEN secret, plus
GITHUB_REPO (e.g. "yourusername/stock-ai-dashboard").
"""

import base64
import requests

API_BASE = "https://api.github.com"


def _headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }


def get_file(token, repo, path):
    """Returns (content_str, sha). Both None if the file doesn't exist or on error."""
    url = f"{API_BASE}/repos/{repo}/contents/{path}"
    try:
        resp = requests.get(url, headers=_headers(token), timeout=10)
        if resp.status_code != 200:
            return None, None
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]
    except Exception:
        return None, None


def update_file(token, repo, path, new_content, message):
    """
    Creates or updates a file in the repo.
    Returns (success: bool, error_message: str or None) so the dashboard
    can show exactly why a save failed instead of a generic message.
    """
    url = f"{API_BASE}/repos/{repo}/contents/{path}"
    _, sha = get_file(token, repo, path)
    payload = {
        "message": message,
        "content": base64.b64encode(new_content.encode("utf-8")).decode("utf-8"),
    }
    if sha:
        payload["sha"] = sha

    try:
        resp = requests.put(url, headers=_headers(token), json=payload, timeout=10)
        if resp.status_code in (200, 201):
            return True, None

        try:
            detail = resp.json().get("message", resp.text)
        except Exception:
            detail = resp.text

        if resp.status_code == 401:
            hint = "Your GITHUB_TOKEN is invalid or expired - generate a new one."
        elif resp.status_code == 404:
            hint = (
                "Repo not found - check GITHUB_REPO is exactly "
                "'yourusername/reponame' and the token has access to it."
            )
        elif resp.status_code == 403:
            hint = (
                "Permission denied - your token needs 'Contents: Read and write' "
                "access on this specific repo."
            )
        else:
            hint = ""

        error_message = f"HTTP {resp.status_code}: {detail}" + (f" ({hint})" if hint else "")
        return False, error_message

    except Exception as e:
        return False, f"Network/connection error: {e}"
