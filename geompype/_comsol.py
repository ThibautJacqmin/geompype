"""Reuse MPh's single client when a script is run again in the same interpreter."""

from ._comsol_config import server_settings

_client = None


def get_client(host=None, port=None, client=None):
    """Reuse the session client; an explicit client bypasses local settings."""
    global _client
    if client is not None:
        # An advanced caller may supply a client that it already manages.
        if _client is None:
            _client = client
        return client

    host, port = server_settings(host, port)
    if _client is not None and _client.standalone:
        raise RuntimeError("This Python session uses a standalone COMSOL client; pass client= explicitly.")
    if _client is not None and _client.port:
        if (_client.host, _client.port) != (host, port):
            raise ValueError(
                f"This Python session is connected to {_client.host}:{_client.port}. "
                "Use that server for this project, or start a new Python session."
            )
        return _client

    if _client is None:
        import mph
        # Keep the client even if connecting fails: MPh cannot start a second JVM.
        _client = mph.Client(host=None)
    # Authenticate directly: a disposable TCP probe can disturb a server whose
    # lifetime follows its client connection. The caller owns the connection.
    _client.connect(port=port, host=host)
    return _client
