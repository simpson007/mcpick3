"""Read local credentials without evaluating shell code or logging secrets."""

import os
from pathlib import Path


def get_mcp_token(directory: Path | None = None) -> str | None:
    """Environment wins; otherwise read the project's ignored .env.local.

    The file is plain text, not a shell script. Only MCD_MCP_TOKEN is read,
    variables are not expanded, and the process environment is not modified.
    """
    token = os.getenv("MCD_MCP_TOKEN", "").strip()
    if token:
        return token
    root = directory or Path.cwd()
    path = root / ".env.local"
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key == "MCD_MCP_TOKEN":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value.strip() or None
    return None
