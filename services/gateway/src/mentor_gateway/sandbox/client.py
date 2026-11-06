"""HTTP client for the sandbox API (CONTRACTS.md section 2)."""

import json
from collections.abc import AsyncIterator

import httpx
from mentor_schemas import ApprovalDecision, JobRequest, JobResult, SandboxEvent, TurnRequest


class SandboxClient:
    def __init__(self, base_url: str, *, token: str | None = None, job_timeout: float = 660.0,
                 turn_timeout: float = 660.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.job_timeout = job_timeout
        self.turn_timeout = turn_timeout
        # MENTOR_HARNESS_TOKEN of this sandbox: sent on every call except the health check
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def health(self, timeout: float = 2.0) -> bool:
        try:
            async with httpx.AsyncClient(timeout=timeout) as c:
                r = await c.get(f"{self.base_url}/v1/health")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def turn(self, req: TurnRequest) -> AsyncIterator[SandboxEvent]:
        timeout = httpx.Timeout(self.turn_timeout, connect=10.0)
        async with (
            httpx.AsyncClient(timeout=timeout) as c,
            c.stream("POST", f"{self.base_url}/v1/turn", json=req.model_dump(mode="json"), headers=self.headers) as r,
        ):
            if r.status_code != 200:
                body = (await r.aread()).decode("utf-8", "replace")
                yield SandboxEvent(type="error", error=f"sandbox HTTP {r.status_code}: {body[:300]}")
                return
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                try:
                    event = SandboxEvent.model_validate(json.loads(data))
                except ValueError as exc:
                    yield SandboxEvent(type="error", error=f"bad sandbox event: {exc}")
                    return
                yield event
                if event.type in ("done", "error"):
                    return

    async def job(self, req: JobRequest) -> JobResult:
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.job_timeout, connect=10.0)) as c:
            r = await c.post(f"{self.base_url}/v1/jobs", json=req.model_dump(mode="json"), headers=self.headers)
            r.raise_for_status()
            return JobResult.model_validate(r.json())

    async def approval(self, decision: ApprovalDecision) -> None:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(f"{self.base_url}/v1/approvals", json=decision.model_dump(mode="json"),
                             headers=self.headers)
            r.raise_for_status()
