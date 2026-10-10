"""The Campus Customs agent team, built with PydanticAI.

Five agents -- boss, inventory, accounting, facilities, customer_service -- all
running the same model through Portkey. Every agent reaches the shop through the
MCP server, which is the only path to the database. Every agent can delegate to
every other agent, so the team is fully connected, with depth and delegation
limits so a run cannot loop forever or burn tokens without end.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPToolset, StdioTransport
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from audit import append_audit_entry, next_step_number, summarise_value
from models import (
    audit_entry,
    delegation_budget,
    shop_deps,
    specialist_report,
    ticket_resolution,
)

project_root = Path(__file__).resolve().parent.parent
prompts_dir = Path(__file__).resolve().parent / "prompts"

# The class .env lives at the AI Foundations root, one level above this project.
load_dotenv(project_root.parent / ".env")
load_dotenv(project_root / ".env")

# Every agent in this homework uses this one model, through Portkey.
model_name = "gpt-6-luna"

# Token guardrails. A multi-agent chat can spiral, so each run is capped.
# Specialists share the Boss's usage tally, so this is one run-wide ceiling on
# model requests, not a per-agent one. Breadth is capped separately by
# shop_deps.max_delegations and depth by shop_deps.max_depth.
run_usage_limits = UsageLimits(request_limit=40)


def build_model() -> OpenAIChatModel:
    """Build the shared model, pointed at Portkey."""
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PORTKEY_API_KEY is not set. Put it in the AI Foundations .env file."
        )
    provider = OpenAIProvider(
        base_url="https://api.portkey.ai/v1",
        api_key=api_key,
    )
    return OpenAIChatModel(
        model_name,
        provider=provider,
        # gpt-6-luna rejects function tools on /chat/completions unless
        # reasoning effort is switched off, so set it explicitly.
        settings=OpenAIChatModelSettings(openai_reasoning_effort="none"),
    )


def load_prompt(agent_file_name: str) -> str:
    """Read one agent's system prompt from backend/prompts/."""
    return (prompts_dir / f"{agent_file_name}.md").read_text(encoding="utf-8")


# The MCP server is the only way any agent touches shop data.
shop_tools = MCPToolset(
    StdioTransport(
        command=str(project_root / ".venv" / "Scripts" / "python.exe"),
        args=[str(project_root / "mcp_server" / "server.py")],
    )
)

shared_model = build_model()


def build_agent(name: str, output_type: Any) -> Agent:
    """Create one agent with its prompt, the MCP tools, and the shared model."""
    return Agent(
        shared_model,
        name=name,
        deps_type=shop_deps,
        output_type=output_type,
        system_prompt=load_prompt(name),
        toolsets=[shop_tools],
    )


boss_agent = build_agent("boss", ticket_resolution)
inventory_agent = build_agent("inventory", specialist_report)
accounting_agent = build_agent("accounting", specialist_report)
facilities_agent = build_agent("facilities", specialist_report)
customer_service_agent = build_agent("customer_service", specialist_report)

agent_registry: dict[str, Agent] = {
    "boss": boss_agent,
    "inventory": inventory_agent,
    "accounting": accounting_agent,
    "facilities": facilities_agent,
    "customer_service": customer_service_agent,
}


# ---------------------------------------------------------------------------
# Audit recording
# ---------------------------------------------------------------------------


def record(
    deps: shop_deps, agent: str, event: str, detail: dict[str, Any]
) -> None:
    """Append one step of an agent loop to the audit trail."""
    append_audit_entry(
        audit_entry(
            run_id=deps.run_id,
            ticket_id=deps.ticket_id,
            step=next_step_number(deps.run_id),
            agent=agent,
            event=event,
            detail=summarise_value(detail),
            caller=deps.caller,
            depth=deps.depth,
            model=model_name,
        )
    )


def record_message_history(deps: shop_deps, agent: str, messages: list) -> None:
    """Record every tool call and tool result from one agent loop.

    PydanticAI keeps the whole loop in the message history, so walking it after
    the run captures which MCP tools the agent reached for and what came back --
    which is what makes the run auditable later.
    """
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolCallPart):
                record(
                    deps,
                    agent,
                    "tool_call",
                    {"tool": part.tool_name, "arguments": part.args_as_dict()},
                )
            elif isinstance(part, ToolReturnPart):
                record(
                    deps,
                    agent,
                    "tool_result",
                    {"tool": part.tool_name, "result": part.content},
                )


# ---------------------------------------------------------------------------
# Delegation: every agent can call every other agent
# ---------------------------------------------------------------------------


async def delegate(
    context: RunContext[shop_deps],
    caller_name: str,
    target: str,
    question: str,
) -> specialist_report | str:
    """Hand a question to another agent and return its report.

    Args:
        context: The calling agent's run context.
        caller_name: Which agent is asking. Known at registration time, so the
            audit trail names the real caller rather than guessing.
        target: Which agent is being asked.
        question: The question being put to them.
    """
    deps = context.deps

    if deps.depth >= deps.max_depth:
        return (
            f"Delegation refused: already {deps.depth} levels deep, which is the "
            "limit. Answer with what you have, or say what is blocked."
        )
    if not deps.budget.try_spend():
        return (
            f"Delegation refused: this run has already used its "
            f"{deps.budget.limit} delegations. Answer with what you have."
        )

    child_deps = shop_deps(
        ticket_id=deps.ticket_id,
        run_id=deps.run_id,
        depth=deps.depth + 1,
        max_depth=deps.max_depth,
        budget=deps.budget,
        caller=caller_name,
    )

    record(
        deps,
        caller_name,
        "delegation_sent",
        {"to": target, "question": question},
    )

    result = await agent_registry[target].run(
        question,
        deps=child_deps,
        usage=context.usage,
        usage_limits=run_usage_limits,
    )

    record_message_history(child_deps, target, result.all_messages())
    record(
        child_deps,
        target,
        "delegation_answered",
        {
            "to_caller": caller_name,
            "summary": result.output.summary,
            "facts_used": result.output.facts_used,
            "actions_taken": result.output.actions_taken,
            "blocked_by": result.output.blocked_by,
            "needs_human_approval": result.output.needs_human_approval,
        },
    )
    return result.output


def register_delegation_tools() -> None:
    """Give every agent a tool for asking each of the others.

    This is what makes the team fully connected: any agent may call any other,
    without routing through the Boss.
    """
    descriptions = {
        "boss": "the Boss, who decides priorities and makes the final call on a ticket",
        "inventory": "the Inventory agent, for stock by SKU and size, shortfalls, "
        "vendors, lead times, and whether a vendor is able to ship",
        "accounting": "the Accounting agent, for cash, invoices, margins, discounts, "
        "and preparing a payment for human approval",
        "facilities": "the Facilities agent, for leases, rent, landlords, and the shop "
        "space",
        "customer_service": "the Customer Service agent, for drafting a message to a "
        "customer",
    }

    for caller_name, caller_agent in agent_registry.items():
        for target_name, target_description in descriptions.items():
            if target_name == caller_name:
                continue

            def make_tool(caller: str, target: str, description: str):
                async def ask_agent(
                    context: RunContext[shop_deps], question: str
                ) -> specialist_report | str:
                    return await delegate(context, caller, target, question)

                ask_agent.__name__ = f"ask_{target}"
                ask_agent.__doc__ = (
                    f"Ask {description}.\n\n"
                    "Ask one specific question with the detail they need, for "
                    "example the sku, size, quantity, ticket id, or amount. Do not "
                    "ask them to 'look at the ticket'.\n\n"
                    "Args:\n"
                    "    question: The question to put to them.\n\n"
                    "Returns:\n"
                    "    Their report: a summary, the facts they used, anything they "
                    "wrote to the shop, and what blocked them if anything did."
                )
                return ask_agent

            caller_agent.tool(make_tool(caller_name, target_name, target_description))


register_delegation_tools()


# ---------------------------------------------------------------------------
# Running the team on a ticket
# ---------------------------------------------------------------------------


async def resolve_ticket(ticket_id: int) -> dict[str, Any]:
    """Put the team on one ticket and return the Boss's resolution.

    The Boss reads the ticket, delegates to whichever specialists it needs, and
    returns the final call. Every step is appended to output/audit_trail.json.
    """
    run_id = f"run_{ticket_id}_{uuid.uuid4().hex[:8]}"
    deps = shop_deps(ticket_id=ticket_id, run_id=run_id, depth=0, caller="human")

    record(deps, "boss", "run_started", {"ticket_id": ticket_id})

    task = (
        f"Work ticket {ticket_id}. Read it first, check the shop's date, then "
        "delegate the parts of the work to the specialists who own them. Make the "
        "final call, record it on the ticket, and make sure anything waiting on a "
        "person is clearly flagged."
    )

    async with boss_agent:
        result = await boss_agent.run(
            task, deps=deps, usage_limits=run_usage_limits
        )

    record_message_history(deps, "boss", result.all_messages())

    resolution = result.output
    record(
        deps,
        "boss",
        "run_finished",
        {
            "decision": resolution.decision,
            "status": resolution.status,
            "agents_consulted": resolution.agents_consulted,
            "actions_taken": resolution.actions_taken,
            "pending_approvals": resolution.pending_approvals,
            "delegations_used": deps.budget.used,
            "total_tokens": result.usage.total_tokens,
        },
    )

    return {
        "run_id": run_id,
        "ticket_id": ticket_id,
        "resolution": resolution.model_dump(),
        "delegations_used": deps.budget.used,
        "total_tokens": result.usage.total_tokens,
    }
