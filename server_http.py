"""
server_http.py — HTTP entrypoint for deployment (Render, Fly.io, or any
platform that runs a plain long-running process rather than Vercel-style
serverless functions).

Unlike Vercel, there's no rewrite/routing layer to fight here: this
process runs uvicorn directly, and the app answers at exactly the path
we tell it to — no mismatch between what a platform forwards and what
the app expects.

Run with:
    uvicorn server_http:app --host 0.0.0.0 --port $PORT
"""

import os
from mcp.server.transport_security import TransportSecuritySettings
from main import mcp

# Render sets this automatically once deployed; falls back to localhost
# for local testing.
host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost")

security = TransportSecuritySettings(
    allowed_hosts=[host, f"{host}:*"],
    allowed_origins=[f"https://{host}"],
)

# Default streamable_http_path ("/mcp") is fine here — no rewrite layer
# means what we ask for is what we get.
app = mcp.streamable_http_app(transport_security=security)