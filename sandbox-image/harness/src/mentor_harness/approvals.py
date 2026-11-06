"""Approval queue: `request_approval` waits here until POST /v1/approvals resolves it."""

import asyncio
import uuid
from datetime import timedelta
from typing import Any, Literal

from mentor_schemas import ApprovalDecision, ApprovalRequest

from mentor_harness.config import now_local

Outcome = Literal["approve", "deny", "timeout"]


class ApprovalBroker:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[ApprovalDecision]] = {}
        self._session_grants: set[tuple[str, str]] = set()  # (session_id, action) approved with scope=session
        self._owners: dict[str, tuple[str, str]] = {}

    def is_granted(self, session_id: str, action: str) -> bool:
        return (session_id, action) in self._session_grants

    def create(
        self, session_id: str, action: str, summary: str, details: dict[str, Any], timeout_s: float
    ) -> ApprovalRequest:
        approval_id = uuid.uuid4().hex
        self._pending[approval_id] = asyncio.get_running_loop().create_future()
        self._owners[approval_id] = (session_id, action)
        return ApprovalRequest(
            approval_id=approval_id,
            action=action,
            summary=summary,
            details=details,
            expires_at=now_local() + timedelta(seconds=timeout_s),
        )

    async def wait(self, approval_id: str, timeout_s: float) -> Outcome:
        fut = self._pending[approval_id]
        try:
            decision = await asyncio.wait_for(asyncio.shield(fut), timeout_s)
        except TimeoutError:
            return "timeout"
        finally:
            self._pending.pop(approval_id, None)
            owner = self._owners.pop(approval_id, None)
        if decision.decision == "approve" and decision.scope == "session" and owner:
            self._session_grants.add(owner)
        return decision.decision

    def resolve(self, decision: ApprovalDecision) -> bool:
        """Deliver a decision; False if the approval is unknown or already finished."""
        fut = self._pending.get(decision.approval_id)
        if fut is None or fut.done():
            return False
        fut.set_result(decision)
        return True
