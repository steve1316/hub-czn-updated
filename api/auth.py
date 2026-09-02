"""
Token check for the local API.

The sidecar runs elevated and listens on localhost, so without this any other program on the machine
- or any web page the user happens to open - could call it. Tauri reads the token off the sidecar's
stdout and sends it back on every request.
"""

import secrets
from urllib.parse import parse_qs

from starlette.responses import JSONResponse

# Game images are loaded by <img> tags that cannot send headers, and there is nothing private in them.
OPEN_PREFIXES = ("/assets",)

HEADER_NAME = b"x-hub-token"


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

        if scope.get("path", "").startswith(OPEN_PREFIXES) or self._token_ok(scope):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            response = JSONResponse({"detail": "Missing or invalid API token."}, status_code=401)
            await response(scope, receive, send)

    def _token_ok(self, scope) -> bool:
        """
        Look for the token in the header, then the query string. WebSockets and image tags cannot set
        headers, so they pass it as ?token=.

        Args:
            scope: The ASGI connection scope.

        Returns:
            True if the supplied token matches.
        """
        supplied = ""
        for key, value in scope.get("headers") or []:
            if key.lower() == HEADER_NAME:
                supplied = value.decode("latin-1")
                break
        if not supplied:
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            supplied = (query.get("token") or [""])[0]
        return secrets.compare_digest(supplied, self.token)
