"""Interfaces the gateway implements for libraries it wires in."""

from typing import Protocol

from mentor_schemas.sandbox_api import JobRequest


class JobQueue(Protocol):
    def enqueue(self, job: JobRequest) -> None: ...
