"""Extension point for external trackers such as Jira, Bugzilla and GitHub Issues.

A connector turns a tracker's issues into ``ExternalIssue`` records. Pass each one to
``services.bugs.create_bug`` with ``source`` and ``external_id`` set, and imported
reports go through the same NLP pipeline as reports submitted in the app.
No connectors are implemented yet.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ExternalIssue:
    external_id: str
    title: str
    description: str
    stack_trace: str = ""


class BugTrackerConnector(Protocol):
    source: str

    def fetch_issues(self, since: str | None = None) -> Iterable[ExternalIssue]:
        """Yield issues changed since the given ISO timestamp."""
