"""FastAPI backend for the Campus Customs dashboard.

Start it from the backend/ folder with:

    uvicorn main:app --reload --port 8000

The dashboard calls these routes to show the board, put the agent team on a
ticket, watch what the agents did, approve payments, read the cash balance, and
reset the shop for a fresh run.

Shop data is read and written through the MCP server, the same path the agents
use. The one thing this backend does that the agents cannot is actually move
money -- and only after a human has clicked approve.
"""

from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from agents import resolve_ticket
from audit import recent_events
from models import approval_decision

project_root = Path(__file__).resolve().parent.parent
original_db = project_root / "data" / "campus_customs.db"
working_db = project_root / "data" / "campus_customs_new.db"
audit_file = project_root / "output" / "audit_trail.json"

# One MCP connection is opened at start-up and reused for every request.
# Opening a fresh subprocess per call made the dashboard crawl.
mcp_client: Client | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Hold one connection to the MCP server for the life of the backend."""
    global mcp_client
    async with shop_client() as client:
        mcp_client = client
        yield
    mcp_client = None


app = FastAPI(
    title="Campus Customs Operations",
    description="Backend for the multi-agent shop dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)

# The dashboard runs on its own port in development, so the browser needs the
# Vite origin explicitly allowed before it will let the page call these routes.
dashboard_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=dashboard_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def shop_client() -> Client:
    """Open a client on the MCP server -- the only path to shop data."""
    return Client(
        StdioTransport(
            command=str(project_root / ".venv" / "Scripts" / "python.exe"),
            args=[str(project_root / "mcp_server" / "server.py")],
        )
    )


async def call_shop_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Call one MCP tool on the shared connection and return its result."""
    if mcp_client is None:
        raise HTTPException(
            status_code=503, detail="The shop MCP server is not connected."
        )
    result = await mcp_client.call_tool(tool_name, arguments)
    return result.data


@app.get("/")
async def root() -> dict[str, Any]:
    """Confirm the backend is up and list the routes the dashboard uses."""
    return {
        "service": "Campus Customs Operations",
        "shop_database": working_db.name,
        "routes": [
            "GET /tickets",
            "POST /tickets/{ticket_id}/run",
            "GET /events",
            "GET /approvals",
            "POST /approvals/decide",
            "POST /approvals/{approval_id}/cancel",
            "GET /cash",
            "GET /drafts",
            "POST /reset",
        ],
    }


@app.get("/tickets")
async def get_tickets() -> dict[str, Any]:
    """Return every ticket on the board with its status.

    The dashboard uses this to draw the board, so it returns all tickets, not
    just open ones, along with a count of how many are still open.
    """
    result = await call_shop_tool("list_tickets", {"status": "all"})
    tickets = result["tickets"]
    desk = await call_shop_tool("get_desk_date", {})
    return {
        "date_today": desk["date_today"],
        "count": len(tickets),
        "open_count": sum(1 for t in tickets if t["status"] == "open"),
        "tickets": [
            {
                "id": t["id"],
                "type": t["type"],
                "requester": t["requester"],
                "subject": t["subject"],
                "sku": t["sku"],
                "size": t["size"],
                "qty": t["qty"],
                "lease_id": t["lease_id"],
                "invoice_id": t["invoice_id"],
                "status": t["status"],
                "is_open": t["status"] == "open",
                "notes": t["notes"],
                "created_at": t["created_at"],
            }
            for t in tickets
        ],
    }


@app.post("/tickets/{ticket_id}/run")
async def run_team_on_ticket(ticket_id: int) -> dict[str, Any]:
    """Put the agent team on one ticket and return the Boss's resolution.

    The Boss reads the ticket, delegates to the specialists it needs, and makes
    the call. Agents may prepare payments but never make them, so a ticket that
    needs money comes back as awaiting_approval with an approval id for a human.
    """
    ticket = await call_shop_tool("get_ticket", {"ticket_id": ticket_id})
    if not ticket.get("found"):
        raise HTTPException(
            status_code=404, detail=f"No ticket exists with id {ticket_id}."
        )

    try:
        return await resolve_ticket(ticket_id)
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"The agent run failed: {error}"
        ) from error


@app.get("/events")
async def get_events(
    limit: int = 60,
    run_id: str | None = None,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Return recent agent events so the board can refresh.

    Each event says which agent acted, who asked it to, how deep the delegation
    went, and which MCP tool was called with what result.

    Args:
        limit: How many events to return, newest last.
        run_id: Limit to one run, or leave out for all runs.
        ticket_id: Limit to one ticket, or leave out for all tickets.
    """
    events = recent_events(limit=limit, run_id=run_id, ticket_id=ticket_id)
    return {
        "count": len(events),
        "run_id": run_id,
        "ticket_id": ticket_id,
        "events": events,
    }


@app.get("/approvals")
async def get_approvals(status: str = "all") -> dict[str, Any]:
    """Return payment requests the agents have prepared for a human."""
    return await call_shop_tool("list_approvals", {"status": status})


@app.post("/approvals/decide")
async def decide_and_pay(decision: approval_decision) -> dict[str, Any]:
    """Record a human's decision on a payment, and pay it if approved.

    This route is the only place money actually moves. The agents can only
    prepare a request; a person clicking approve here is what changes cash.

    A rejected request is closed and nothing is paid. An approved request is
    paid straight away, unless the balance will not cover it -- the MCP pay tool
    refuses rather than letting the account go negative.
    """
    recorded = await call_shop_tool(
        "decide_approval",
        {
            "approval_id": decision.approval_id,
            "decision": decision.decision,
            "decided_by": decision.decided_by,
            "note": decision.note,
        },
    )
    if not recorded.get("ok"):
        raise HTTPException(status_code=400, detail=recorded["message"])

    if decision.decision == "rejected":
        return {
            "approval_id": decision.approval_id,
            "decision": "rejected",
            "decided_by": decision.decided_by,
            "payment": None,
            "message": "Request rejected. No money moved.",
        }

    payment = await call_shop_tool(
        "pay_approved_request", {"approval_id": decision.approval_id}
    )
    if not payment.get("ok"):
        # Approved by a person, but the shop cannot afford it.
        return {
            "approval_id": decision.approval_id,
            "decision": "approved",
            "decided_by": decision.decided_by,
            "payment": None,
            "message": payment["message"],
        }

    return {
        "approval_id": decision.approval_id,
        "decision": "approved",
        "decided_by": decision.decided_by,
        "payment": payment,
        "message": (
            f"Paid {payment['amount']} for {payment['kind']}. "
            f"Balance is now {payment['balance_after']}."
        ),
    }


@app.post("/approvals/{approval_id}/cancel")
async def cancel_payment_request(
    approval_id: int, cancelled_by: str, reason: str = ""
) -> dict[str, Any]:
    """Withdraw a payment request the shop is not going to pay.

    Used when a request was approved but the balance will not cover it, so it
    does not sit on the board forever. A person must do this, not an agent.
    """
    result = await call_shop_tool(
        "cancel_approval",
        {
            "approval_id": approval_id,
            "cancelled_by": cancelled_by,
            "reason": reason,
        },
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/cash")
async def get_cash(account: str = "checking") -> dict[str, Any]:
    """Return the current cash balance and what has been paid out so far."""
    balance = await call_shop_tool("get_cash_balance", {"account": account})
    if not balance.get("found"):
        raise HTTPException(status_code=404, detail=balance["message"])

    payments = await call_shop_tool("list_payments", {})
    return {
        "account": balance["account"],
        "balance": balance["balance"],
        "as_of": balance["as_of"],
        "total_paid": payments["total_paid"],
        "payments": payments["payments"],
    }


@app.get("/drafts")
async def get_drafts(ticket_id: int | None = None) -> dict[str, Any]:
    """Return customer message drafts. Nothing here has been sent."""
    arguments = {} if ticket_id is None else {"ticket_id": ticket_id}
    return await call_shop_tool("list_drafts", arguments)


@app.post("/reset")
async def reset_shop(clear_audit: bool = False) -> dict[str, Any]:
    """Reset the shop to its original values for a fresh run.

    Copies the untouched data/campus_customs.db over the working copy, which
    puts back the original cash, inventory, invoices, and open tickets, and
    clears the approvals and drafts the agents created.

    Args:
        clear_audit: Also delete output/audit_trail.json. Off by default,
            because the audit trail is meant to accumulate across runs.
    """
    if not original_db.exists():
        raise HTTPException(
            status_code=500, detail="The original database is missing."
        )

    shutil.copyfile(original_db, working_db)
    cleared = False
    if clear_audit and audit_file.exists():
        audit_file.unlink()
        cleared = True

    cash = await call_shop_tool("get_cash_balance", {"account": "checking"})
    tickets = await call_shop_tool("list_tickets", {"status": "open"})
    return {
        "ok": True,
        "message": "Shop reset to original values.",
        "balance": cash["balance"],
        "open_tickets": tickets["count"],
        "audit_trail_cleared": cleared,
    }
