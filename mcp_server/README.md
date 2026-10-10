# Campus Customs MCP Server

## What it is for

This MCP server is the single way the Campus Customs agent team reads the shop. The
Boss, Inventory, Accounting, Facilities, and Customer Service agents do not query the
database directly — they call the tools here. That keeps every agent looking at the same
numbers and makes sure no agent invents data: every value a tool returns comes out of a
table, and a lookup that finds nothing returns `found: False` with a plain message
instead of a guess.

## Database it uses

`data/campus_customs_new.db` — the working copy. The path is resolved relative to this
file, so the server can be started from any directory.

The original `data/campus_customs.db` is never opened by this server. To reset the shop,
copy the original over the working copy.

The server also reads `desk.date_today` (2026-08-31) as the shop's current date. Every
date comparison uses that value rather than the real calendar.

## Tools

All tools read `desk.date_today` (2026-08-31) as the shop's current date rather than the
real calendar.

### The board
| tool | table(s) |
|---|---|
| `get_desk_date()` | `desk` |
| `list_tickets(status)` | `tickets` |
| `get_ticket(ticket_id)` | `tickets` |
| `update_ticket_status(ticket_id, status, note)` | `tickets` |

### Inventory, pricing, vendors
| tool | table(s) |
|---|---|
| `check_stock_for_order(sku, size, qty_requested)` | `inventory` |
| `list_stock_for_sku(sku)` | `inventory` |
| `get_pricing(sku)` | `pricing` |
| `quote_discount(sku, qty, discount_percent)` | `pricing` |
| `list_vendors()` | `vendors` |
| `get_vendor_status(vendor_id)` | `vendors`, `invoices`, `desk` |

`get_vendor_status` is the one that enforces the shipping rule: a vendor with an open
unpaid invoice comes back `can_ship: false`, with the blocking invoice named.

### Facilities
| tool | table(s) |
|---|---|
| `get_lease(lease_id)` | `leases`, `desk` |
| `list_leases()` | `leases`, `desk` |

### Money
| tool | table(s) |
|---|---|
| `get_cash_balance(account)` | `cash_accounts` |
| `list_invoices(status)` | `invoices`, `vendors`, `desk` |
| `request_payment_approval(...)` | `approvals`, `cash_accounts` |
| `list_approvals(status)` | `approvals` |
| `decide_approval(approval_id, decision, decided_by, note)` | `approvals` |
| `pay_approved_request(approval_id)` | `payments`, `cash_accounts`, `invoices`, `leases`, `approvals` |
| `list_payments()` | `payments` |

The money rules are enforced here, not left to the agents:

- `request_payment_approval` parks a request and **moves no money**. It is as far as any
  agent can go.
- `decide_approval` **refuses agent names** — `boss`, `accounting`, and the rest — so an
  agent cannot approve its own request. A person must decide.
- `pay_approved_request` refuses anything not already `approved`, and refuses any payment
  that would push the balance below zero. On success it debits cash, writes a `payments`
  row carrying the approving person's name, and marks the invoice paid or rolls the
  lease's next due date forward.

### Customer drafts
| tool | table(s) |
|---|---|
| `save_customer_draft(ticket_id, audience, subject, body, written_by)` | `drafts` |
| `list_drafts(ticket_id)` | `drafts` |

Drafts are saved to the board and **never sent**. No customer is emailed and no vendor is
contacted.

### Tables this server creates

`approvals` and `drafts` are not in the original database. The server creates them with
`CREATE TABLE IF NOT EXISTS` at start-up, so resetting the shop by copying the original
file over the working copy still works.

## Running it

```bash
.venv/Scripts/python.exe mcp_server/server.py
```

Requires `fastmcp` (installed in the project virtual environment `.venv`).
