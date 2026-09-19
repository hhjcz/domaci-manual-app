"""Placeholder for the documentation API.

Nothing is served here yet. The planned first endpoint is ``POST /api/chat``,
backed by retrieval over the Markdown sources (SQLite FTS5 first, embeddings
only if that proves insufficient) and an OpenAI-compatible LLM provider. See
the "Future: AI assistant" section of the README.

Keeping the seam explicit means adding the chat later is a new module plus one
route registration, not a restructuring: the aiohttp application, the built
site and the Markdown checkout are all reachable from here.
"""

from __future__ import annotations

from aiohttp import web


def setup_routes(app: web.Application) -> None:
    """Register API routes. Intentionally empty in v1."""
