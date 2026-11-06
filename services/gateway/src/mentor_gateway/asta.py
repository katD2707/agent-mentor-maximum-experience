"""Minimal MCP (Streamable HTTP) client for Ai2's Asta Scientific Corpus Tool, used by papers.py.

Asta: https://allenai.org/asta/resources/mcp. Licensed for academic and non-commercial use; Ai2 may use the inputs,
so callers send only search terms and paper ids, never learner data. Results must carry an attribution
(ASTA_ATTRIBUTION).

The protocol subset we need: JSON-RPC 2.0 over HTTP POST, `initialize` once (keeps `Mcp-Session-Id` if the server
issues one; the public server is stateless and issues none), then `tools/call`. A response is either
`application/json` or `text/event-stream` (SSE `data:` lines carrying JSON-RPC messages, with `: ping` comments while
the server waits on its own upstream). The official `mcp` SDK would pull in anyio/pydantic-settings/sse-starlette;
this is ~120 lines over the httpx we already use.
"""

import asyncio
import itertools
import json
from typing import Any
from urllib.parse import urlsplit

import httpx

ASTA_MCP_URL = "https://asta-tools.allen.ai/mcp/v1"
ASTA_ATTRIBUTION = "Asta Scientific Corpus Tool, Ai2 (Allen Institute for AI); data: Semantic Scholar"
PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "mentor-gateway", "version": "0.1"}


class AstaError(Exception):
    """`status` is the HTTP status the paper endpoints return (400, 404, 502, 503, 504)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def parse_sse(body: bytes) -> list[Any]:
    """JSON payloads of the SSE `data:` events in `body` (comments such as `: ping` are skipped)."""
    events, data = [], []
    for raw in body.decode("utf-8", "replace").splitlines() + [""]:
        line = raw.rstrip("\r")
        if not line:
            if data:
                try:
                    events.append(json.loads("\n".join(data)))
                except ValueError:
                    pass
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
    return events


def tool_result(result: Any) -> Any:
    """The payload of a `tools/call` result: `structuredContent.result`, else JSON text content."""
    if not isinstance(result, dict):
        raise AstaError(502, "Asta returned a malformed result")
    texts = [
        c.get("text") or "" for c in result.get("content") or [] if isinstance(c, dict) and c.get("type") == "text"
    ]
    if result.get("isError"):
        message = " ".join(texts)[:300] or "tool error"
        low = message.lower()
        if "not found" in low or "404" in low:
            raise AstaError(404, "paper not found")
        if "429" in low or "rate limit" in low or "too many" in low:
            raise AstaError(503, "Asta is rate limiting; try again in a minute")
        if "400" in low or "invalid" in low or "validation" in low:
            raise AstaError(400, f"Asta rejected the request: {message}")
        raise AstaError(502, f"Asta tool error: {message}")
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    parsed = []
    for text in texts:
        try:
            parsed.append(json.loads(text))
        except ValueError:
            continue
    if len(parsed) == 1:
        return parsed[0]
    return parsed


class AstaClient:
    def __init__(
        self,
        url: str = ASTA_MCP_URL,
        *,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 40.0,
        max_bytes: int = 2_000_000,
        user_agent: str = "mentor-gateway/0.1",
    ) -> None:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise ValueError(f"ASTA_MCP_URL must be an https URL, got {url!r}")
        self.url = url
        self.host = parts.hostname
        self.api_key = api_key
        self.transport = transport
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self._session_id: str | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._ids = itertools.count(1)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Run one tool with an overall deadline (SSE pings would otherwise keep the read timeout alive)."""
        try:
            return await asyncio.wait_for(self._call_tool(name, arguments), self.timeout_s)
        except TimeoutError as exc:
            raise AstaError(504, f"Asta did not answer within {self.timeout_s:.0f} s") from exc

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        await self._ensure_initialized()
        try:
            msg = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        except AstaError as exc:
            if exc.status != 404 or self._session_id is None:
                raise
            self._initialized, self._session_id = False, None  # session expired: start a new one, retry once
            await self._ensure_initialized()
            msg = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        return tool_result(msg)

    async def _ensure_initialized(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            await self._rpc(
                "initialize",
                {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO},
                keep_session=True,
            )
            await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_reply=False)
            self._initialized = True

    async def _rpc(self, method: str, params: dict[str, Any], *, keep_session: bool = False) -> Any:
        rid = next(self._ids)
        messages, session = await self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        if keep_session:
            self._session_id = session
        reply = next((m for m in messages if isinstance(m, dict) and m.get("id") == rid), None)
        if reply is None:
            raise AstaError(502, "Asta sent no reply")
        if "error" in reply:
            err = reply["error"] if isinstance(reply["error"], dict) else {}
            status = 400 if err.get("code") == -32602 else 502
            raise AstaError(status, f"Asta error: {str(err.get('message') or err)[:300]}")
        return reply.get("result")

    async def _post(self, payload: dict[str, Any], *, expect_reply: bool = True) -> tuple[list[Any], str | None]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "User-Agent": self.user_agent,
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            async with (
                httpx.AsyncClient(transport=self.transport, timeout=self.timeout_s, follow_redirects=False) as client,
                client.stream("POST", self.url, json=payload, headers=headers) as resp,
            ):
                status = resp.status_code
                if status == 429:
                    raise AstaError(503, "Asta is rate limiting; try again in a minute")
                if status in (401, 403):
                    raise AstaError(502, f"Asta refused access (HTTP {status}); check ASTA_API_KEY")
                if status == 404:
                    raise AstaError(404, "Asta session or endpoint not found")
                if status == 400:
                    body = (await resp.aread())[:300].decode("utf-8", "replace")
                    raise AstaError(400, f"Asta rejected the request: {body}")
                if not expect_reply and status in (200, 202, 204):
                    return [], resp.headers.get("mcp-session-id")
                if status != 200:
                    raise AstaError(502, f"Asta returned HTTP {status}")
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise AstaError(502, f"Asta response larger than {self.max_bytes} bytes")
                    chunks.append(chunk)
                body = b"".join(chunks)
                session = resp.headers.get("mcp-session-id")
                if "text/event-stream" in resp.headers.get("content-type", ""):
                    return parse_sse(body), session
                try:
                    data = json.loads(body)
                except ValueError as exc:
                    raise AstaError(502, "Asta returned invalid JSON") from exc
                return (data if isinstance(data, list) else [data]), session
        except httpx.TimeoutException as exc:
            raise AstaError(504, "Asta timed out") from exc
        except httpx.HTTPError as exc:
            raise AstaError(502, f"Asta unreachable: {exc.__class__.__name__}") from exc
