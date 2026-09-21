"""
api/index.py — Vercel's Python entrypoint.

Vercel serves this file's `app` variable as an ASGI application.
We import the actual MCP server from main.py and wrap it for HTTP,
since main.py's own mcp.run() only knows how to speak stdio (for
Claude Desktop / test_client.py) — deploying needs a different
transport, not a different server.
"""

import os
import sys

# Vercel runs this from inside api/; add the project root so
# "from main import mcp" can find main.py one level up.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.server.transport_security import TransportSecuritySettings
from main import mcp

# Vercel sets VERCEL_URL automatically to this deployment's real
# hostname — we don't have to know it in advance or hardcode it.
vercel_host = os.environ.get("VERCEL_URL", "localhost")

security = TransportSecuritySettings(
    allowed_hosts=[vercel_host, f"{vercel_host}:*"],
    allowed_origins=[f"https://{vercel_host}"],
)

app = mcp.streamable_http_app(transport_security=security)