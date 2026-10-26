"""
Request tracking and command dispatch for the game WebSocket.

After login the game batches its commands into JSON lists, and the server answers in kind. Each reply carries the `qid` of the command it
answers, so pairing them lets a handler know what was asked. Handlers are registered by command name ("item/unequip_piece" or just "gacha").

The request-pairing idea (qid -> command, cleared on `helo`) is ported from Vribbels-CZN-Optimizer, MIT, (c) 2025 Vorbroker, 2026 Ikkoru.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# The most requests remembered at once. A long capture would otherwise grow this forever.
MAX_TRACKED = 2000

# The first command of every connection. The game's qids start again at 1 after it.
HELO = "helo"


@dataclass
class PendingRequest:
    """One client command, remembered until its reply arrives."""

    # The id the server echoes back on its reply.
    qid: Any
    # The command family, such as "item".
    cmd: str
    # The command inside the family, such as "disassemble_piece". None when the command has no inner command.
    inner: Optional[str] = None
    # The request parameters as the client sent them.
    params: Dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """The dispatch name, "cmd/inner" when there is an inner command and "cmd" otherwise."""
        return f"{self.cmd}/{self.inner}" if self.inner else self.cmd


Handler = Callable[[Dict[str, Any], PendingRequest], None]


def unwrap_frame(data: Any) -> List[dict]:
    """
    Split one decoded frame into its individual messages.

    Args:
        data: The JSON-decoded frame. A single message is a dict and a batch is a list.

    Returns:
        The dict messages in order. Anything that is not a dict is dropped.
    """
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


class RequestTracker:
    """Remembers client commands by `qid` so each server reply can be paired with what asked for it."""

    def __init__(self):
        self._requests: "OrderedDict[Any, PendingRequest]" = OrderedDict()

    def note_frame(self, data: Any):
        """
        Record every command in a client frame, and forget everything on `helo`.

        Args:
            data: The JSON-decoded client frame.
        """
        for entry in unwrap_frame(data):
            if entry.get("cmd") == HELO:
                self.clear()
                continue
            qid = entry.get("qid")
            if qid is None or entry.get("cmd") is None:
                continue
            params = entry.get("params")
            params = params if isinstance(params, dict) else {}
            inner = params.get("cmd")
            self._requests[qid] = PendingRequest(qid=qid, cmd=str(entry["cmd"]), inner=str(inner) if inner else None, params=params)
            self._requests.move_to_end(qid)
            while len(self._requests) > MAX_TRACKED:
                self._requests.popitem(last=False)

    def get(self, qid: Any) -> Optional[PendingRequest]:
        """
        Look up the request a reply answers.

        Args:
            qid: The `qid` carried by the server reply.

        Returns:
            The matching request, or None when it was never seen (for example the game was already running).
        """
        return self._requests.get(qid)

    def pop(self, qid: Any) -> Optional[PendingRequest]:
        """
        Look up and forget the request a reply answers, so a repeated reply is not paired twice.

        Args:
            qid: The `qid` carried by the server reply.

        Returns:
            The matching request, or None when it was never seen.
        """
        return self._requests.pop(qid, None)

    def clear(self):
        """Forget every request. A new connection restarts its qids, so old ones would pair with the wrong reply."""
        self._requests.clear()


class CommandDispatch:
    """Maps command names to handlers. Later features register their own handlers here."""

    def __init__(self):
        self._handlers: Dict[str, List[Handler]] = {}

    def register(self, name: str, handler: Handler):
        """
        Add a handler for a command.

        Args:
            name: "cmd/inner" for a call with an inner command, or "cmd" for one without.
            handler: Called with the server reply and the request it answers.
        """
        self._handlers.setdefault(name, []).append(handler)

    def dispatch(self, request: Optional[PendingRequest], payload: Dict[str, Any]):
        """
        Run the handlers registered for a reply's request name.

        Args:
            request: The request the reply answers, or None when it is unknown.
            payload: The server reply.
        """
        if request is None:
            return
        for handler in self._handlers.get(request.name, ()):
            handler(payload, request)
