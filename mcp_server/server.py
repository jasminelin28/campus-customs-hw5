"""MCP server for Campus Customs shop operations.

Every agent on the Campus Customs team reads and changes the shop through the
tools defined here. All tools work on the working copy of the shop database and
return only what is actually stored there -- no values are invented or
estimated. A lookup that finds nothing returns found=False with a plain message.

Money rules enforced in this file, not left to the agents:
  * No payment happens without a human approval recorded in the approvals table.
  * No payment may push a cash account below zero; the pay tool refuses.
  * Cash only goes out in this shop, so nothing here increases a balance.
  * A vendor with an open unpaid invoice will not ship new product.
"""

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

# The working copy. The original data/campus_customs.db is never touched.
db_path = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"

mcp = FastMCP("campus_customs")


def open_connection() -> sqlite3.Connection:
    """Open the working database with rows returned as dictionaries."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_workflow_tables() -> None:
    """Create the tables the agent workflow needs if they are not there yet.

    The shop database ships with nine tables. The agents also need somewhere to
    park requests waiting on a human and somewhere to leave customer drafts, so
    those two tables are created on demand. Doing it here means resetting the
    shop by copying the original database over the working copy still works.
    """
    with open_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                kind TEXT NOT NULL,
                ref_id INTEGER,
                amount REAL NOT NULL,
                account TEXT NOT NULL,
                reason TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                status TEXT NOT NULL,
                decided_by TEXT,
                decided_at TEXT,
                decision_note TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                vendor_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                size TEXT NOT NULL,
                qty INTEGER NOT NULL,
                unit_cost REAL NOT NULL,
                total_cost REAL NOT NULL,
                expected_arrival TEXT NOT NULL,
                status TEXT NOT NULL,
                approval_id INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                audience TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                written_by TEXT NOT NULL,
                written_at TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )


ensure_workflow_tables()


def get_date_today() -> str:
    """Return the shop's current date from the desk table.

    The shop runs on desk.date_today, not on the real calendar, so every date
    comparison in this server uses this value.
    """
    with open_connection() as connection:
        row = connection.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    return row["date_today"]


def days_between(start_date: str, end_date: str) -> int:
    """Whole days from start_date to end_date, both as YYYY-MM-DD strings."""
    start = date.fromisoformat(start_date[:10])
    end = date.fromisoformat(end_date[:10])
    return (end - start).days


def add_days(start_date: str, days: int) -> str:
    """Return the date that is `days` after start_date, as YYYY-MM-DD."""
    return (date.fromisoformat(start_date[:10]) + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# The board: tickets and the shop's date
# ---------------------------------------------------------------------------


@mcp.tool()
def get_desk_date() -> dict[str, Any]:
    """Return the shop's current date.

    Always call this instead of assuming today's date. Everything overdue in
    this shop is measured against it.
    """
    return {"date_today": get_date_today()}


@mcp.tool()
def list_tickets(status: str = "open") -> dict[str, Any]:
    """List tickets on the board.

    Args:
        status: Which tickets to return -- "open", "resolved", or "all".

    Returns:
        The matching tickets, newest last, with a count.
    """
    with open_connection() as connection:
        if status == "all":
            rows = connection.execute(
                "SELECT * FROM tickets ORDER BY id"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM tickets WHERE status = ? ORDER BY id", (status,)
            ).fetchall()

    tickets = [dict(row) for row in rows]
    return {"count": len(tickets), "status_filter": status, "tickets": tickets}


@mcp.tool()
def get_ticket(ticket_id: int) -> dict[str, Any]:
    """Look up one ticket in full.

    Args:
        ticket_id: The ticket number, for example 101.

    Returns:
        Every field on the ticket, including the sku, size, qty, lease_id, and
        invoice_id that link it to the rest of the shop.
    """
    with open_connection() as connection:
        row = connection.execute(
            "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()

    if row is None:
        return {
            "found": False,
            "ticket_id": ticket_id,
            "message": f"No ticket exists with id {ticket_id}.",
        }
    return {"found": True, **dict(row)}


@mcp.tool()
def update_ticket_status(ticket_id: int, status: str, note: str) -> dict[str, Any]:
    """Change a ticket's status and append a note explaining why.

    Use this to close a ticket out or to park it as blocked. The note is
    appended to the ticket's existing notes so the history is kept.

    Args:
        ticket_id: The ticket number.
        status: The new status, for example "resolved", "blocked", or "open".
        note: One or two sentences on what was decided and why.

    Returns:
        The ticket's new status and combined notes.
    """
    with open_connection() as connection:
        row = connection.execute(
            "SELECT notes FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if row is None:
            return {
                "ok": False,
                "ticket_id": ticket_id,
                "message": f"No ticket exists with id {ticket_id}.",
            }

        stamped = f"[{get_date_today()}] {note}"
        combined = f"{row['notes']} | {stamped}" if row["notes"] else stamped
        connection.execute(
            "UPDATE tickets SET status = ?, notes = ? WHERE id = ?",
            (status, combined, ticket_id),
        )

    return {"ok": True, "ticket_id": ticket_id, "status": status, "notes": combined}


# ---------------------------------------------------------------------------
# Inventory, pricing, vendors
# ---------------------------------------------------------------------------


@mcp.tool()
def check_stock_for_order(sku: str, size: str, qty_requested: int) -> dict[str, Any]:
    """Check whether an order quantity can be filled from stock on hand.

    Stock is tracked per SKU and size together, so both are required. Compares
    the requested quantity against inventory and reports the shortfall, which is
    the number of units that would have to be restocked from a vendor.

    Args:
        sku: Item code, for example "CC-HOOD-NAVY".
        size: Size code, for example "S", "M", "L", "XL", or "OS".
        qty_requested: How many units the ticket asks for.

    Returns:
        The quantity on hand, whether the order can be filled, and the shortfall.
    """
    with open_connection() as connection:
        row = connection.execute(
            "SELECT sku, name, size, qty, location FROM inventory "
            "WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()

    if row is None:
        return {
            "found": False,
            "sku": sku,
            "size": size,
            "qty_requested": qty_requested,
            "message": f"No inventory record exists for {sku} in size {size}.",
        }

    qty_on_hand = row["qty"]
    shortfall = max(0, qty_requested - qty_on_hand)
    return {
        "found": True,
        "sku": row["sku"],
        "name": row["name"],
        "size": row["size"],
        "qty_on_hand": qty_on_hand,
        "qty_requested": qty_requested,
        "can_fill": shortfall == 0,
        "shortfall": shortfall,
        "location": row["location"],
    }


@mcp.tool()
def list_stock_for_sku(sku: str) -> dict[str, Any]:
    """List every size of one SKU with its quantity on hand.

    Useful when one size is short and you want to see whether another size
    could be offered instead.

    Args:
        sku: Item code, for example "CC-TEE-WHITE".

    Returns:
        One entry per size, plus the total units of that SKU in the shop.
    """
    with open_connection() as connection:
        rows = connection.execute(
            "SELECT sku, name, size, qty, location FROM inventory "
            "WHERE sku = ? ORDER BY size",
            (sku,),
        ).fetchall()

    if not rows:
        return {
            "found": False,
            "sku": sku,
            "message": f"No inventory records exist for {sku}.",
        }

    sizes = [dict(row) for row in rows]
    return {
        "found": True,
        "sku": sku,
        "name": rows[0]["name"],
        "sizes": sizes,
        "total_qty": sum(row["qty"] for row in rows),
    }


@mcp.tool()
def get_pricing(sku: str) -> dict[str, Any]:
    """Look up unit cost, list price, and margin for one SKU.

    Use this to judge a discount request: margin_per_unit is the room available
    before a sale stops being profitable.

    Args:
        sku: Item code, for example "CC-HOOD-NAVY".

    Returns:
        Unit cost, list price, margin per unit, and margin as a percent of list.
    """
    with open_connection() as connection:
        row = connection.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?",
            (sku,),
        ).fetchone()

    if row is None:
        return {
            "found": False,
            "sku": sku,
            "message": f"No pricing record exists for {sku}.",
        }

    unit_cost = row["unit_cost"]
    list_price = row["list_price"]
    margin_per_unit = list_price - unit_cost
    return {
        "found": True,
        "sku": row["sku"],
        "unit_cost": unit_cost,
        "list_price": list_price,
        "margin_per_unit": margin_per_unit,
        "margin_percent": round(100 * margin_per_unit / list_price, 1),
    }


@mcp.tool()
def quote_discount(sku: str, qty: int, discount_percent: float) -> dict[str, Any]:
    """Price a proposed bulk discount and show whether it stays profitable.

    Works out the discounted unit price, the total order value, and the total
    margin left at that discount. Also reports the largest discount that still
    breaks even, so a counter-offer can be grounded in a real number.

    Args:
        sku: Item code, for example "CC-HOOD-NAVY".
        qty: How many units the customer wants.
        discount_percent: The discount off list price being considered, for
            example 15 for fifteen percent.

    Returns:
        Unit price after discount, order total, total margin, margin per unit,
        whether it is profitable, and the break-even discount percent.
    """
    pricing = get_pricing(sku=sku)
    if not pricing["found"]:
        return pricing

    unit_cost = pricing["unit_cost"]
    list_price = pricing["list_price"]
    discounted_price = round(list_price * (1 - discount_percent / 100), 2)
    margin_per_unit = round(discounted_price - unit_cost, 2)
    break_even_discount = round(100 * (list_price - unit_cost) / list_price, 1)

    return {
        "found": True,
        "sku": sku,
        "qty": qty,
        "discount_percent": discount_percent,
        "list_price": list_price,
        "unit_cost": unit_cost,
        "discounted_unit_price": discounted_price,
        "order_total": round(discounted_price * qty, 2),
        "margin_per_unit": margin_per_unit,
        "total_margin": round(margin_per_unit * qty, 2),
        "is_profitable": margin_per_unit > 0,
        "break_even_discount_percent": break_even_discount,
    }


@mcp.tool()
def list_vendors() -> dict[str, Any]:
    """List every vendor with their specialty and lead time in days."""
    with open_connection() as connection:
        rows = connection.execute(
            "SELECT id, name, specialty, lead_days FROM vendors ORDER BY id"
        ).fetchall()
    vendors = [dict(row) for row in rows]
    return {"count": len(vendors), "vendors": vendors}


@mcp.tool()
def get_vendor_status(vendor_id: int) -> dict[str, Any]:
    """Check whether a vendor will ship, and when an order would arrive.

    A vendor will not ship new product while they still have an open unpaid
    invoice, so this checks the invoices table before reporting can_ship. The
    expected arrival date is the shop's date plus the vendor's lead time.

    Args:
        vendor_id: The vendor id, for example 1.

    Returns:
        The vendor record, their open invoices and total owed, whether they can
        ship, and the expected arrival date if an order were placed today.
    """
    with open_connection() as connection:
        vendor = connection.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?",
            (vendor_id,),
        ).fetchone()
        if vendor is None:
            return {
                "found": False,
                "vendor_id": vendor_id,
                "message": f"No vendor exists with id {vendor_id}.",
            }
        open_invoices = connection.execute(
            "SELECT id, amount, due_date, status, description FROM invoices "
            "WHERE vendor_id = ? AND status = 'open' ORDER BY due_date",
            (vendor_id,),
        ).fetchall()

    date_today = get_date_today()
    blocking = [dict(row) for row in open_invoices]
    for invoice in blocking:
        invoice["days_overdue"] = days_between(invoice["due_date"], date_today)

    can_ship = len(blocking) == 0
    return {
        "found": True,
        "vendor_id": vendor["id"],
        "name": vendor["name"],
        "specialty": vendor["specialty"],
        "lead_days": vendor["lead_days"],
        "date_today": date_today,
        "open_invoices": blocking,
        "total_owed": round(sum(invoice["amount"] for invoice in blocking), 2),
        "can_ship": can_ship,
        "expected_arrival": add_days(date_today, vendor["lead_days"])
        if can_ship
        else None,
        "blocked_reason": None
        if can_ship
        else (
            f"{vendor['name']} has {len(blocking)} open unpaid invoice(s) "
            f"totaling {round(sum(i['amount'] for i in blocking), 2)}. "
            "They will not ship new product until it is paid."
        ),
    }


# ---------------------------------------------------------------------------
# Facilities
# ---------------------------------------------------------------------------


@mcp.tool()
def get_lease(lease_id: int) -> dict[str, Any]:
    """Look up a lease and how its next payment sits against today's date.

    Use this to verify a rent notice against the signed lease before any money
    is prepared, and to see how many days remain until the rent is due.

    Args:
        lease_id: The lease id, taken from the ticket's lease_id field.

    Returns:
        The lease terms plus days_until_due and whether the payment is overdue.
    """
    with open_connection() as connection:
        row = connection.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
            "FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()

    if row is None:
        return {
            "found": False,
            "lease_id": lease_id,
            "message": f"No lease exists with id {lease_id}.",
        }

    date_today = get_date_today()
    days_until_due = days_between(date_today, row["next_due"])
    return {
        "found": True,
        "lease_id": row["id"],
        "space_name": row["space_name"],
        "landlord": row["landlord"],
        "monthly_rent": row["monthly_rent"],
        "next_due": row["next_due"],
        "notes": row["notes"],
        "date_today": date_today,
        "days_until_due": days_until_due,
        "is_overdue": days_until_due < 0,
    }


@mcp.tool()
def list_leases() -> dict[str, Any]:
    """List every lease the shop holds with its rent and next due date."""
    with open_connection() as connection:
        rows = connection.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
            "FROM leases ORDER BY id"
        ).fetchall()
    date_today = get_date_today()
    leases = []
    for row in rows:
        lease = dict(row)
        lease["days_until_due"] = days_between(date_today, row["next_due"])
        lease["is_overdue"] = lease["days_until_due"] < 0
        leases.append(lease)
    return {"count": len(leases), "date_today": date_today, "leases": leases}


# ---------------------------------------------------------------------------
# Money: cash, invoices, approvals, payments
# ---------------------------------------------------------------------------


@mcp.tool()
def get_cash_balance(account: str = "checking") -> dict[str, Any]:
    """Look up the balance of a cash account.

    Cash only goes out in this shop, so this balance is the hard ceiling on
    everything the team can commit to.

    Args:
        account: Account name. Defaults to "checking".

    Returns:
        The account balance and the date it is stated as of.
    """
    with open_connection() as connection:
        row = connection.execute(
            "SELECT name, balance, date FROM cash_accounts WHERE name = ?",
            (account,),
        ).fetchone()

    if row is None:
        return {
            "found": False,
            "account": account,
            "message": f"No cash account named {account} exists.",
        }
    return {
        "found": True,
        "account": row["name"],
        "balance": row["balance"],
        "as_of": row["date"],
    }


@mcp.tool()
def list_invoices(status: str = "open") -> dict[str, Any]:
    """List invoices the shop owes, with vendor names and how overdue they are.

    Args:
        status: "open", "paid", or "all".

    Returns:
        The matching invoices with days_overdue measured against the shop's date.
    """
    with open_connection() as connection:
        query = (
            "SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, "
            "i.due_date, i.status, i.description "
            "FROM invoices i JOIN vendors v ON v.id = i.vendor_id"
        )
        if status == "all":
            rows = connection.execute(query + " ORDER BY i.due_date").fetchall()
        else:
            rows = connection.execute(
                query + " WHERE i.status = ? ORDER BY i.due_date", (status,)
            ).fetchall()

    date_today = get_date_today()
    invoices = []
    for row in rows:
        invoice = dict(row)
        invoice["days_overdue"] = days_between(row["due_date"], date_today)
        invoice["is_overdue"] = invoice["days_overdue"] > 0
        invoices.append(invoice)

    return {
        "count": len(invoices),
        "status_filter": status,
        "date_today": date_today,
        "total_amount": round(sum(i["amount"] for i in invoices), 2),
        "invoices": invoices,
    }


@mcp.tool()
def get_invoice(invoice_id: int) -> dict[str, Any]:
    """Look up one invoice by id, whatever its status.

    Use this when a ticket names an invoice. Listing only open invoices will
    not find one that has already been paid, and a missing row is not the same
    fact as a settled bill -- this tool tells the two apart.

    Args:
        invoice_id: The invoice id, for example 501.

    Returns:
        The invoice with its vendor, status, how overdue it was, and whether it
        is still blocking that vendor from shipping.
    """
    with open_connection() as connection:
        row = connection.execute(
            "SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, "
            "i.due_date, i.status, i.description "
            "FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
            "WHERE i.id = ?",
            (invoice_id,),
        ).fetchone()
        if row is None:
            return {
                "found": False,
                "invoice_id": invoice_id,
                "message": f"No invoice exists with id {invoice_id}.",
            }
        payment = connection.execute(
            "SELECT id, amount, paid_at, approved_by FROM payments "
            "WHERE kind = 'invoice' AND ref_id = ? ORDER BY id DESC LIMIT 1",
            (invoice_id,),
        ).fetchone()

    date_today = get_date_today()
    is_open = row["status"] == "open"
    return {
        "found": True,
        "invoice_id": row["id"],
        "vendor_id": row["vendor_id"],
        "vendor_name": row["vendor_name"],
        "amount": row["amount"],
        "due_date": row["due_date"],
        "status": row["status"],
        "description": row["description"],
        "date_today": date_today,
        "days_overdue": days_between(row["due_date"], date_today) if is_open else 0,
        "is_blocking_vendor": is_open,
        "payment": dict(payment) if payment is not None else None,
        "summary": (
            f"Invoice {row['id']} to {row['vendor_name']} for {row['amount']} is "
            + (
                "still open and is blocking that vendor from shipping."
                if is_open
                else f"paid, so it no longer blocks {row['vendor_name']} from shipping."
            )
        ),
    }


@mcp.tool()
def request_payment_approval(
    kind: str,
    amount: float,
    reason: str,
    requested_by: str,
    ticket_id: int | None = None,
    ref_id: int | None = None,
    account: str = "checking",
) -> dict[str, Any]:
    """Put a payment in front of a human for approval. Does NOT move money.

    This is the only way to start a payment. The request is parked with status
    "pending" until a person approves it on the dashboard. No agent may approve
    its own request.

    Args:
        kind: What the money is for -- "rent", "invoice", or "purchase_order".
        amount: The amount in dollars.
        reason: Why the shop should pay this, in one or two sentences.
        requested_by: Which agent is asking, for example "accounting".
        ticket_id: The ticket this relates to, if any.
        ref_id: The lease id for rent, or the invoice id for an invoice.
        account: Which cash account would be debited. Defaults to "checking".

    Returns:
        The approval id and status, plus the balance that would remain if it is
        approved and paid. A warning is included if the balance would not cover
        it.
    """
    balance_now = get_cash_balance(account=account)
    if not balance_now["found"]:
        return {"ok": False, "message": balance_now["message"]}

    if amount <= 0:
        return {
            "ok": False,
            "message": f"Amount must be positive; got {amount}.",
        }

    date_today = get_date_today()
    with open_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO approvals (ticket_id, kind, ref_id, amount, account, "
            "reason, requested_by, requested_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
            (
                ticket_id,
                kind,
                ref_id,
                amount,
                account,
                reason,
                requested_by,
                date_today,
            ),
        )
        approval_id = cursor.lastrowid

    remaining = round(balance_now["balance"] - amount, 2)
    return {
        "ok": True,
        "approval_id": approval_id,
        "status": "pending",
        "kind": kind,
        "amount": amount,
        "account": account,
        "ticket_id": ticket_id,
        "ref_id": ref_id,
        "requested_by": requested_by,
        "balance_before": balance_now["balance"],
        "balance_if_paid": remaining,
        "sufficient_cash": remaining >= 0,
        "message": (
            f"Approval {approval_id} is pending a human decision. "
            "No money has moved."
            + (
                ""
                if remaining >= 0
                else f" Warning: paying this would overdraw {account} by "
                f"{abs(remaining)}."
            )
        ),
    }


@mcp.tool()
def list_approvals(status: str = "pending") -> dict[str, Any]:
    """List approval requests waiting on, or already given, a human decision.

    Args:
        status: "pending", "approved", "rejected", "paid", or "all".

    Returns:
        The matching approval requests.
    """
    with open_connection() as connection:
        if status == "all":
            rows = connection.execute(
                "SELECT * FROM approvals ORDER BY id"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
    approvals = [dict(row) for row in rows]
    return {"count": len(approvals), "status_filter": status, "approvals": approvals}


@mcp.tool()
def decide_approval(
    approval_id: int, decision: str, decided_by: str, note: str = ""
) -> dict[str, Any]:
    """Record a human's approve or reject decision on a payment request.

    This is the human's tool, used from the dashboard. Agents must not call it
    on their own behalf -- decided_by must be a person's name, not an agent.
    Approving still does not move money; the payment is made separately by
    pay_approved_request.

    Args:
        approval_id: Which request is being decided.
        decision: "approved" or "rejected".
        decided_by: The name of the person deciding.
        note: Optional note on the reasoning.

    Returns:
        The updated approval record.
    """
    if decision not in ("approved", "rejected"):
        return {
            "ok": False,
            "message": f"Decision must be 'approved' or 'rejected'; got '{decision}'.",
        }

    agent_names = {
        "boss",
        "inventory",
        "accounting",
        "facilities",
        "customer_service",
    }
    if decided_by.strip().lower().replace(" ", "_") in agent_names:
        return {
            "ok": False,
            "message": (
                f"'{decided_by}' is an agent, not a person. Payment approval "
                "requires a human decision maker."
            ),
        }

    with open_connection() as connection:
        row = connection.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        if row is None:
            return {
                "ok": False,
                "message": f"No approval request exists with id {approval_id}.",
            }
        if row["status"] != "pending":
            return {
                "ok": False,
                "message": (
                    f"Approval {approval_id} is already '{row['status']}' and "
                    "cannot be decided again."
                ),
            }
        connection.execute(
            "UPDATE approvals SET status = ?, decided_by = ?, decided_at = ?, "
            "decision_note = ? WHERE id = ?",
            (decision, decided_by, get_date_today(), note, approval_id),
        )
        updated = connection.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()

    return {"ok": True, **dict(updated)}


@mcp.tool()
def cancel_approval(
    approval_id: int, cancelled_by: str, reason: str
) -> dict[str, Any]:
    """Withdraw a payment request that is not going to be paid.

    A request that a person approved but that the shop cannot afford would
    otherwise sit approved and unpayable forever. This is the human's way to
    take it off the board. Like approving, it must be done by a person, not an
    agent. Any purchase order attached to it is cancelled too.

    Args:
        approval_id: The request to withdraw.
        cancelled_by: The name of the person withdrawing it.
        reason: Why it is being withdrawn.

    Returns:
        The updated approval record.
    """
    agent_names = {
        "boss",
        "inventory",
        "accounting",
        "facilities",
        "customer_service",
    }
    if cancelled_by.strip().lower().replace(" ", "_") in agent_names:
        return {
            "ok": False,
            "message": (
                f"'{cancelled_by}' is an agent, not a person. Only a human may "
                "withdraw a payment request."
            ),
        }

    with open_connection() as connection:
        row = connection.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        if row is None:
            return {
                "ok": False,
                "message": f"No approval request exists with id {approval_id}.",
            }
        if row["status"] == "paid":
            return {
                "ok": False,
                "message": (
                    f"Approval {approval_id} has already been paid and cannot be "
                    "withdrawn."
                ),
            }
        connection.execute(
            "UPDATE approvals SET status = 'cancelled', decided_by = ?, "
            "decided_at = ?, decision_note = ? WHERE id = ?",
            (cancelled_by, get_date_today(), reason, approval_id),
        )
        if row["kind"] == "purchase_order" and row["ref_id"] is not None:
            connection.execute(
                "UPDATE purchase_orders SET status = 'cancelled' WHERE id = ?",
                (row["ref_id"],),
            )
        updated = connection.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()

    return {"ok": True, **dict(updated)}


@mcp.tool()
def pay_approved_request(approval_id: int) -> dict[str, Any]:
    """Pay a request that a human has already approved.

    Refuses unless the approval exists and its status is "approved". Refuses if
    the payment would push the account below zero -- no negative balances. On
    success it debits the cash account, writes a row to payments carrying the
    approving human's name, and updates the invoice or lease that was paid.

    Args:
        approval_id: The approved request to pay.

    Returns:
        The payment id, the new balance, and what was updated.
    """
    date_today = get_date_today()
    with open_connection() as connection:
        approval = connection.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        if approval is None:
            return {
                "ok": False,
                "message": f"No approval request exists with id {approval_id}.",
            }
        if approval["status"] == "pending":
            return {
                "ok": False,
                "approval_id": approval_id,
                "message": (
                    f"Approval {approval_id} has not been decided by a human "
                    "yet. Payment refused."
                ),
            }
        if approval["status"] != "approved":
            return {
                "ok": False,
                "approval_id": approval_id,
                "message": (
                    f"Approval {approval_id} is '{approval['status']}', not "
                    "'approved'. Payment refused."
                ),
            }

        account_row = connection.execute(
            "SELECT name, balance FROM cash_accounts WHERE name = ?",
            (approval["account"],),
        ).fetchone()
        if account_row is None:
            return {
                "ok": False,
                "message": f"No cash account named {approval['account']} exists.",
            }

        amount = approval["amount"]
        balance_before = account_row["balance"]
        balance_after = round(balance_before - amount, 2)
        if balance_after < 0:
            return {
                "ok": False,
                "approval_id": approval_id,
                "amount": amount,
                "balance_before": balance_before,
                "shortfall": round(abs(balance_after), 2),
                "message": (
                    f"Not enough cash. Paying {amount} from {account_row['name']} "
                    f"with {balance_before} on hand would leave {balance_after}. "
                    "Payment refused -- the shop does not go negative."
                ),
            }

        connection.execute(
            "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
            (balance_after, date_today, account_row["name"]),
        )
        cursor = connection.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, "
            "approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (
                approval["kind"],
                approval["ref_id"],
                amount,
                account_row["name"],
                date_today,
                approval["decided_by"],
            ),
        )
        payment_id = cursor.lastrowid

        updated_record = None
        if approval["kind"] == "invoice" and approval["ref_id"] is not None:
            connection.execute(
                "UPDATE invoices SET status = 'paid' WHERE id = ?",
                (approval["ref_id"],),
            )
            updated_record = f"invoice {approval['ref_id']} marked paid"
        elif approval["kind"] == "purchase_order" and approval["ref_id"] is not None:
            connection.execute(
                "UPDATE purchase_orders SET status = 'ordered' WHERE id = ?",
                (approval["ref_id"],),
            )
            order = connection.execute(
                "SELECT sku, size, qty, expected_arrival FROM purchase_orders "
                "WHERE id = ?",
                (approval["ref_id"],),
            ).fetchone()
            if order is not None:
                updated_record = (
                    f"purchase order {approval['ref_id']} placed: {order['qty']} x "
                    f"{order['sku']} size {order['size']}, expected "
                    f"{order['expected_arrival']}"
                )
        elif approval["kind"] == "rent" and approval["ref_id"] is not None:
            lease = connection.execute(
                "SELECT next_due FROM leases WHERE id = ?", (approval["ref_id"],)
            ).fetchone()
            if lease is not None:
                current_due = date.fromisoformat(lease["next_due"][:10])
                month = current_due.month + 1
                year = current_due.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                next_due = date(year, month, current_due.day).isoformat()
                connection.execute(
                    "UPDATE leases SET next_due = ? WHERE id = ?",
                    (next_due, approval["ref_id"]),
                )
                updated_record = (
                    f"lease {approval['ref_id']} next_due moved to {next_due}"
                )

        connection.execute(
            "UPDATE approvals SET status = 'paid' WHERE id = ?", (approval_id,)
        )

    return {
        "ok": True,
        "payment_id": payment_id,
        "approval_id": approval_id,
        "kind": approval["kind"],
        "amount": amount,
        "account": account_row["name"],
        "paid_at": date_today,
        "approved_by": approval["decided_by"],
        "balance_before": balance_before,
        "balance_after": balance_after,
        "updated": updated_record,
    }


@mcp.tool()
def draft_purchase_order(
    sku: str,
    size: str,
    qty: int,
    vendor_id: int,
    requested_by: str,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    """Draft a restock order with a vendor and park it for human approval.

    Prices the order from the pricing table, checks the vendor will actually
    ship, and creates both a purchase order and the payment approval that must
    be signed off before it is placed. Nothing is ordered and no money moves
    until a person approves it.

    Args:
        sku: Item code to restock.
        size: Size to restock.
        qty: How many units to order.
        vendor_id: Which vendor should supply it.
        requested_by: Which agent is asking, for example "inventory".
        ticket_id: The ticket this restock is for, if any.

    Returns:
        The purchase order, its cost, the expected arrival date, and the
        approval id a human must decide on.
    """
    if qty <= 0:
        return {"ok": False, "message": f"Quantity must be positive; got {qty}."}

    pricing = get_pricing(sku=sku)
    if not pricing["found"]:
        return {"ok": False, "message": pricing["message"]}

    vendor = get_vendor_status(vendor_id=vendor_id)
    if not vendor["found"]:
        return {"ok": False, "message": vendor["message"]}
    if not vendor["can_ship"]:
        return {
            "ok": False,
            "vendor_id": vendor_id,
            "message": (
                f"Cannot order from {vendor['name']}: {vendor['blocked_reason']}"
            ),
        }

    unit_cost = pricing["unit_cost"]
    total_cost = round(unit_cost * qty, 2)
    expected_arrival = vendor["expected_arrival"]
    date_today = get_date_today()

    with open_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO purchase_orders (ticket_id, vendor_id, sku, size, qty, "
            "unit_cost, total_cost, expected_arrival, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?)",
            (
                ticket_id,
                vendor_id,
                sku,
                size,
                qty,
                unit_cost,
                total_cost,
                expected_arrival,
                date_today,
            ),
        )
        purchase_order_id = cursor.lastrowid

    approval = request_payment_approval(
        kind="purchase_order",
        amount=total_cost,
        reason=(
            f"Restock {qty} x {sku} size {size} from {vendor['name']} for ticket "
            f"{ticket_id}. Expected arrival {expected_arrival} "
            f"({vendor['lead_days']} day lead time)."
        ),
        requested_by=requested_by,
        ticket_id=ticket_id,
        ref_id=purchase_order_id,
    )

    with open_connection() as connection:
        connection.execute(
            "UPDATE purchase_orders SET approval_id = ? WHERE id = ?",
            (approval.get("approval_id"), purchase_order_id),
        )

    return {
        "ok": True,
        "purchase_order_id": purchase_order_id,
        "sku": sku,
        "size": size,
        "qty": qty,
        "vendor_id": vendor_id,
        "vendor_name": vendor["name"],
        "unit_cost": unit_cost,
        "total_cost": total_cost,
        "expected_arrival": expected_arrival,
        "status": "pending_approval",
        "approval_id": approval.get("approval_id"),
        "balance_if_paid": approval.get("balance_if_paid"),
        "message": (
            f"Purchase order {purchase_order_id} drafted for {total_cost}. "
            f"Approval {approval.get('approval_id')} is pending a human decision. "
            "Nothing has been ordered and no money has moved."
        ),
    }


@mcp.tool()
def list_purchase_orders(status: str = "all") -> dict[str, Any]:
    """List restock orders and where each one stands.

    Args:
        status: "pending_approval", "ordered", "rejected", or "all".
    """
    with open_connection() as connection:
        if status == "all":
            rows = connection.execute(
                "SELECT * FROM purchase_orders ORDER BY id"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM purchase_orders WHERE status = ? ORDER BY id",
                (status,),
            ).fetchall()
    orders = [dict(row) for row in rows]
    return {"count": len(orders), "status_filter": status, "purchase_orders": orders}


@mcp.tool()
def list_payments() -> dict[str, Any]:
    """List every payment the shop has made, with who approved each one."""
    with open_connection() as connection:
        rows = connection.execute(
            "SELECT id, kind, ref_id, amount, account, paid_at, approved_by "
            "FROM payments ORDER BY id"
        ).fetchall()
    payments = [dict(row) for row in rows]
    return {
        "count": len(payments),
        "total_paid": round(sum(p["amount"] for p in payments), 2),
        "payments": payments,
    }


# ---------------------------------------------------------------------------
# Customer drafts
# ---------------------------------------------------------------------------


@mcp.tool()
def save_customer_draft(
    ticket_id: int, audience: str, subject: str, body: str, written_by: str
) -> dict[str, Any]:
    """Save a draft message for a human to review. Nothing is sent.

    Messages in this shop are never emailed or delivered. The draft stays on the
    board for a person to read, edit, and send themselves.

    Args:
        ticket_id: The ticket this message answers.
        audience: Who it is addressed to, for example "Tauhid Zaman".
        subject: Subject line.
        body: The message itself, in plain professional English.
        written_by: Which agent wrote it, normally "customer_service".

    Returns:
        The draft id and a confirmation that it was saved, not sent.
    """
    with open_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO drafts (ticket_id, audience, subject, body, "
            "written_by, written_at, status) VALUES (?, ?, ?, ?, ?, ?, 'draft')",
            (ticket_id, audience, subject, body, written_by, get_date_today()),
        )
        draft_id = cursor.lastrowid

    return {
        "ok": True,
        "draft_id": draft_id,
        "ticket_id": ticket_id,
        "audience": audience,
        "subject": subject,
        "status": "draft",
        "message": "Draft saved to the board. It was not sent to anyone.",
    }


@mcp.tool()
def list_drafts(ticket_id: int | None = None) -> dict[str, Any]:
    """List saved message drafts, optionally for one ticket.

    Args:
        ticket_id: Limit to one ticket, or leave out for all drafts.
    """
    with open_connection() as connection:
        if ticket_id is None:
            rows = connection.execute("SELECT * FROM drafts ORDER BY id").fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM drafts WHERE ticket_id = ? ORDER BY id", (ticket_id,)
            ).fetchall()
    drafts = [dict(row) for row in rows]
    return {"count": len(drafts), "drafts": drafts}


if __name__ == "__main__":
    mcp.run()
