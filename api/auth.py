"""
Token check for the local API.

The sidecar runs elevated and listens on localhost, so without this any other program on the machine
- or any web page the user happens to open - could call it. Tauri reads the token off the sidecar's
stdout and sends it back on every request.
"""

import secrets

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

# Where main.py mounts the static game art. Imported there too so the two cannot drift apart.
# Those files are loaded by <img> tags that cannot send headers, and none of it is private.
ASSETS_PREFIX = "/assets"

HEADER_NAME = "x-hub-token"


class TokenAuthMiddleware:
    """Rejects HTTP and WebSocket traffic that does not carry the API token."""

    def __init__(self, app, token: str):
        """
        Args:
            app: The ASGI app to wrap.
            token: Expected token. An empty string turns the check off, which is what the tests use.
        """
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        """Pass the request through when the token matches, otherwise reject it."""
        if not self.token or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if scope.get("path", "").startswith(ASSETS_PREFIX) or self._token_ok(scope):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            response = JSONResponse({"detail": "Missing or invalid API token."}, status_code=401)
            await response(scope, receive, send)

    def _token_ok(self, scope) -> bool:
        """
        Look for the token in the header, then the query string. WebSockets cannot set headers, so they
        pass it as ?token= instead.

        Args:
            scope: The ASGI connection scope.

        Returns:
            True if the supplied token matches.
        """
        # HTTPConnection is the shared base of Request and WebSocket, so it handles both scope types.
        conn = HTTPConnection(scope)
        supplied = conn.headers.get(HEADER_NAME) or conn.query_params.get("token", "")
        return secrets.compare_digest(supplied, self.token)
