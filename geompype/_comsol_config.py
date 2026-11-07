"""Resolve local server settings without importing MPh or opening a connection."""

import json
import os
from pathlib import Path


def server_settings(host=None, port=None):
    """Return a validated ``(host, port)`` pair for a new Project or client.

    Each field uses its explicit argument, then ``GEOMPYPE_COMSOL_HOST`` or
    ``GEOMPYPE_COMSOL_PORT``, then ``comsol.local.json`` in the current working
    directory, then ``localhost`` or ``2036``. The local file is read only if
    at least one field still needs a value. Settings are not cached.
    """
    host = host if host is not None else os.environ.get("GEOMPYPE_COMSOL_HOST")
    port = port if port is not None else os.environ.get("GEOMPYPE_COMSOL_PORT")
    settings = {}
    if host is None or port is None:
        path = Path("comsol.local.json")
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            pass
        else:
            try:
                settings = json.loads(content)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path} must contain a valid JSON object.") from error
            if not isinstance(settings, dict) or set(settings) - {"host", "port"}:
                raise ValueError(f"{path} accepts only the keys 'host' and 'port'.")

    if host is None:
        host = settings.get("host", "localhost")
    if port is None:
        port = settings.get("port", 2036)
    if not isinstance(host, str) or not host or any(char.isspace() for char in host):
        raise ValueError("COMSOL host must be a nonempty string without whitespace.")
    if isinstance(port, str) and port.isascii() and port.isdecimal():
        port = int(port)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("COMSOL port must be an integer from 1 to 65535.")
    return host, port
