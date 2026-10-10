"""Data types shared across the Campus Customs agent team."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

agent_name = Literal[
    "boss",
    "inventory",
    "accounting",
    "facilities",
    "customer_service",
]


# ---------------------------------------------------------------------------
# What the agents hand back
# ---------------------------------------------------------------------------


class specialist_report(BaseModel):
    """What a specialist agent returns to whoever asked it for help."""

    summary: str = Field(
        description="What was found or done, in plain professional English."
    )
    facts_used: list[str] = Field(
        default_factory=list,
        description=(
            "The specific shop facts this answer rests on, each with its number, "
            "for example 'CC-TEE-WHITE size S is at qty 0'."
        ),
    )
    actions_taken: list[str] = Field(
        default_factory=list,
        description="Changes actually written to the shop, if any.",
    )
    blocked_by: str | None = Field(
        default=None,
        description="What is stopping this work, if anything is.",
    )
    needs_human_approval: bool = Field(
        default=False,
        description="True if an approval request is now waiting on a person.",
    )


class ticket_resolution(BaseModel):
    """The Boss's final call on one ticket."""

    ticket_id: int
    decision: str = Field(description="The call made, in one or two sentences.")
    reasoning: str = Field(description="Why this is the right call for the shop.")
    agents_consulted: list[str] = Field(
        default_factory=list, description="Which specialists were asked for help."
    )
    actions_taken: list[str] = Field(
        default_factory=list, description="Changes written to the shop."
    )
    pending_approvals: list[int] = Field(
        default_factory=list,
        description="Approval ids now waiting on a human decision.",
    )
    status: Literal["resolved", "blocked", "awaiting_approval"] = Field(
        description=(
            "Where the ticket stands after this run. Use 'resolved' once the shop's "
            "own work is finished, including when an ordered restock is still in "
            "transit -- a delivery date in the future is not a blocker. Use "
            "'awaiting_approval' while a person still has to decide on money. Use "
            "'blocked' only when something genuinely stops progress, such as an "
            "unpaid invoice holding up a vendor or a record that does not exist."
        )
    )


# ---------------------------------------------------------------------------
# Run context passed to every agent
# ---------------------------------------------------------------------------


@dataclass
class delegation_budget:
    """A delegation counter shared by every agent in one run.

    Agents can delegate concurrently, so the count has to live in one object
    they all point at. If each level kept its own copy, two delegations started
    at the same time would overwrite each other's tally.
    """

    used: int = 0
    limit: int = 8

    def try_spend(self) -> bool:
        """Take one delegation from the budget, or report that it is spent."""
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


@dataclass
class shop_deps:
    """Context carried through one run of the team.

    Attributes:
        ticket_id: The ticket being worked, if the run is about one ticket.
        run_id: Groups every audit entry from a single run.
        depth: How many delegations deep we are. Guards against agents handing
            work back and forth forever.
        max_depth: The ceiling on depth. Beyond it, delegation is refused.
        budget: The run's shared delegation budget, capping token use.
        caller: Which agent asked for this work, so the audit trail shows who
            handed what to whom.
    """

    ticket_id: int | None = None
    run_id: str = ""
    depth: int = 0
    max_depth: int = 3
    budget: delegation_budget = field(default_factory=delegation_budget)
    caller: str = "human"


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


@dataclass
class audit_entry:
    """One recorded step of an agent loop."""

    run_id: str
    ticket_id: int | None
    step: int
    agent: str
    event: str
    detail: dict[str, Any] = field(default_factory=dict)
    caller: str = ""
    depth: int = 0
    timestamp: str = ""
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "step": self.step,
            "timestamp": self.timestamp,
            "agent": self.agent,
            "caller": self.caller,
            "depth": self.depth,
            "event": self.event,
            "model": self.model,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Shapes the dashboard reads
# ---------------------------------------------------------------------------


class approval_decision(BaseModel):
    """A human's decision on a pending payment, sent from the dashboard."""

    approval_id: int
    decision: Literal["approved", "rejected"]
    decided_by: str = Field(description="The name of the person deciding.")
    note: str = ""


class run_request(BaseModel):
    """A request from the dashboard to put the team on a ticket."""

    ticket_id: int
