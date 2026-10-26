# Hub CZN dev MCP server

Lets a coding agent drive the running sidecar: capture status/start/stop, setup status, latest snapshot, rescue records, capture log tail and
battle replay. Dev tool only, not bundled into the sidecar.

## Install

```
pip install -r requirements-dev.txt
```

## Run the sidecar

```
HUB_CZN_API_TOKEN=dev python -m api.main
```

## Register with Claude Code

```
claude mcp add hub-czn --scope local -e HUB_CZN_API_URL=http://127.0.0.1:7842 -e HUB_CZN_API_TOKEN=dev -- python <repo>/tools/mcp/server.py
```

`HUB_CZN_API_URL` and `HUB_CZN_API_TOKEN` default to the values above. If the sidecar bound a different port, change the URL.

`replay_capture` runs `scripts/replay_capture.py` as a subprocess.
