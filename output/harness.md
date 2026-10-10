# Campus Customs — Agent Harness

Working database: `data/campus_customs_new.db` (copy of the untouched original
`data/campus_customs.db`). Reset by re-copying the original over the working copy.

Shop "today": **2026-08-31** (from `desk.date_today`). Anything dated before this is
overdue.

---

## 1. Tables and fields

### `desk`
| field | type | meaning |
|---|---|---|
| `date_today` | TEXT | the shop's current date, `2026-08-31` |
| `notes` | TEXT | free-text desk notes |

*Why it matters:* this is the only clock the agents have. Every overdue check — rent,
invoices, lead times — is measured against `date_today`, not the real calendar.

### `tickets`
| field | type | meaning |
|---|---|---|
| `id` | INTEGER | ticket number |
| `type` | TEXT | `customer_order`, `rent_notice`, `price_override` |
| `requester` | TEXT | who opened it |
| `subject` | TEXT | one-line summary |
| `sku`, `size`, `qty` | TEXT/TEXT/INT | the item requested, if any |
| `lease_id` | INTEGER | link to `leases.id`, if any |
| `invoice_id` | INTEGER | link to `invoices.id`, if any |
| `status` | TEXT | `open` / resolved |
| `notes` | TEXT | the request in words |
| `created_at` | TEXT | timestamp opened |

*Why it matters:* this is the agents' work queue. The Boss reads the ticket type and
routes it, and the foreign keys tell each agent which other table to open.

### `inventory`
| field | type | meaning |
|---|---|---|
| `sku` | TEXT | item code (part of primary key) |
| `name` | TEXT | product name |
| `size` | TEXT | `S`/`M`/`L`/`XL`/`OS` (part of primary key) |
| `qty` | INTEGER | units on hand |
| `location` | TEXT | aisle |

*Why it matters:* stock is tracked per SKU **and** size, so the Inventory agent has to
check the exact pair. This is where a shortfall gets detected.

### `pricing`
| field | type | meaning |
|---|---|---|
| `sku` | TEXT | item code |
| `unit_cost` | REAL | what the shop pays |
| `list_price` | REAL | what the shop charges |

*Why it matters:* the Accounting agent needs both numbers to compute margin and decide
whether a requested discount still leaves the shop profitable.

### `vendors`
| field | type | meaning |
|---|---|---|
| `id` | INTEGER | vendor id |
| `name` | TEXT | vendor name |
| `specialty` | TEXT | what they supply |
| `lead_days` | INTEGER | days from order to delivery |

*Why it matters:* restocking decisions come from here — who can make the item and how
long it takes. A vendor with an open unpaid invoice will not ship.

### `leases`
| field | type | meaning |
|---|---|---|
| `id` | INTEGER | lease id |
| `space_name` | TEXT | the space |
| `landlord` | TEXT | who gets paid |
| `monthly_rent` | REAL | amount due |
| `next_due` | TEXT | next due date |
| `notes` | TEXT | free text |

*Why it matters:* the Facilities agent uses this to confirm a rent notice is real and to
hand Accounting the correct amount and due date.

### `cash_accounts`
| field | type | meaning |
|---|---|---|
| `name` | TEXT | account name (`checking`) |
| `balance` | REAL | money available |
| `date` | TEXT | as-of date |

*Why it matters:* the hard constraint on everything. Cash only goes out in this shop, so
the pay tool must refuse any payment that would push the balance below zero.

### `payments`
| field | type | meaning |
|---|---|---|
| `id` | INTEGER | payment id |
| `kind` | TEXT | what was paid (rent, invoice) |
| `ref_id` | INTEGER | the lease or invoice paid |
| `amount` | REAL | amount |
| `account` | TEXT | account debited |
| `paid_at` | TEXT | date paid |
| `approved_by` | TEXT | the human who approved |

*Why it matters:* the audit trail. Starts empty. A row only appears after a human
approves, and `approved_by` is the proof that approval happened.

### `invoices`
| field | type | meaning |
|---|---|---|
| `id` | INTEGER | invoice id |
| `vendor_id` | INTEGER | link to `vendors.id` |
| `amount` | REAL | amount owed |
| `due_date` | TEXT | when it was due |
| `status` | TEXT | `open` / `paid` |
| `description` | TEXT | what it covers |

*Why it matters:* an open invoice blocks that vendor from shipping, so it couples
Accounting directly to Inventory's restock plan.

---

## 2. Current state of the shop (2026-08-31)

- **Cash:** checking, $3,400.00
- **Open invoice:** #501, vendor 1 (Bulldog Print Co), $840.00, due 2026-08-28 —
  **3 days overdue**
- **Lease:** Chapel Street shop, Elm City Properties, $2,400.00/mo, next due 2026-09-02
  — **due in 2 days**
- **Payments made so far:** none
- **Stock at zero:** `CC-TEE-WHITE` size S, `CC-MUG-CREST` size OS

---

## 3. The three open tickets and how they link

### Ticket 101 — customer order, Tauhid Zaman, "Bulldog tee"
Wants 1 × `CC-TEE-WHITE` size S. Links to `invoice_id` **501**.

The chain: `inventory` says that SKU/size is at **qty 0**, so the order cannot be filled
from stock. Restocking means `vendors` id 1, Bulldog Print Co (apparel reprint,
**5 day** lead time) — and invoice 501 is *their* unpaid, overdue $840 bill, which is
exactly the thing that stops them shipping. So this ticket cannot be closed by Inventory
alone: Accounting has to clear invoice 501 first, which needs human approval, and only
then does a 5-day reprint become possible. Customer Service writes Tauhid the timeline.

### Ticket 102 — rent notice, Elm City Properties, "Rent due"
Links to `lease_id` **1**.

The chain: `leases` id 1 confirms $2,400.00 due 2026-09-02, two days out from
`desk.date_today`. Facilities verifies the notice against the lease; Accounting checks
`cash_accounts` and prepares the payment for human approval. On approval a row lands in
`payments` with `kind='rent'`, `ref_id=1`.

### Ticket 103 — price override, Yale AI Club, "Bulk hoodie discount"
Wants 20 × `CC-HOOD-NAVY` size M, asking for a bulk discount. No foreign keys.

The chain: `inventory` shows only **8** in size M (4 S, 14 L, 6 XL) — a shortfall of 12
even before price is discussed. `pricing` gives unit_cost $22.00 vs list $58.00, so
there is $36.00 of margin per unit to negotiate inside. Inventory sizes the gap,
Accounting sets the discount floor, Customer Service drafts the reply.

### The cash squeeze that ties them together
Invoice 501 ($840) plus rent ($2,400) is **$3,240** against a **$3,400** balance. Both
fit, but barely, leaving $160 — so any purchase order for the tee reprint or the hoodie
shortfall has to be weighed after those two, and the pay tool must refuse anything that
would overdraw. Ordering matters, and the Boss has to sequence it.

---

## 4. MCP tools (first three)

Server: `mcp_server/server.py` (FastMCP), reading `data/campus_customs_new.db`.
Every agent reaches the shop through these tools, so no agent can invent a number.

### `check_stock_for_order(sku, size, qty_requested)`
- **Reads:** `inventory`
- **Unlocks:** ticket **101**, and also ticket **103**
- **Why it is the right tool:** ticket 101 asks for one `CC-TEE-WHITE` in size S, and
  stock is keyed by SKU *and* size together — checking the SKU alone would show 10 tees
  across the shop and wrongly look fillable, when size S is specifically at qty 0. The
  tool compares the request against the exact SKU/size row and returns `shortfall: 1`,
  which is the fact that turns 101 from "pick it off the shelf" into a restock problem.
  The same call on ticket 103 returns `shortfall: 12` against the 8 size-M hoodies on
  hand, sizing the gap before any discount is discussed.

### `get_lease(lease_id)`
- **Reads:** `leases`, and `desk` for the current date
- **Unlocks:** ticket **102**
- **Why it is the right tool:** ticket 102 is only an *email* claiming rent is due in two
  days, and no money should move on the strength of an email. The ticket carries
  `lease_id = 1`, so this tool pulls the signed lease and confirms the real obligation —
  Elm City Properties, $2,400.00, next due 2026-09-02 — and computes `days_until_due: 2`
  against `desk.date_today`, which both verifies the sender's claim and gives Accounting
  the exact amount to prepare for approval.

### `get_pricing(sku)`
- **Reads:** `pricing`
- **Unlocks:** ticket **103**
- **Why it is the right tool:** the Yale AI Club asks for a bulk discount on 20 hoodies,
  and that request cannot be answered without knowing what the shop pays. This tool
  returns `unit_cost: 22.00` against `list_price: 58.00`, so there is `margin_per_unit:
  36.00` (62.1%) of room — the floor below which a discount sells the hoodies at a loss.
  Without it, any discount Customer Service offers would be a guess.

---

## 5. The agent team

Built with PydanticAI. Every agent runs the same model — **`gpt-6-luna` through
Portkey** — and reaches the shop only through the MCP server. Prompts live in
`backend/prompts/`, one file per agent.

| agent | owns | must not |
|---|---|---|
| **boss** | Reads the ticket, routes it, makes the final call, records it | Approve payments; do specialist work itself |
| **inventory** | Stock by SKU and size, shortfalls, vendor choice, lead times | Spend money; promise a restock from a blocked vendor |
| **accounting** | Cash, invoices, margins, discounts, preparing payments | Pay anything — it may only request approval |
| **facilities** | Leases, rent, landlords, the shop space | Pay rent on its own say-so |
| **customer_service** | Drafting messages customers will read | Send anything; promise an unconfirmed date |

**Full connectivity.** Every agent carries an `ask_<agent>` tool for each of the other
four, so any agent may delegate to any other without routing through the Boss. The
delegation that matters most in this shop is Inventory → Accounting: a vendor blocked by
an unpaid invoice is an inventory problem whose solution is money.

**Audit trail.** Every step appends to `output/audit_trail.json` — run id, step number,
agent, who called it, delegation depth, the MCP tool called with its arguments, and the
result. The file is appended to and never wiped, so runs accumulate.

---

## 6. MCP tools and the tables they use

| tool | table(s) | what it is for |
|---|---|---|
| `get_desk_date` | `desk` | The shop's current date; every overdue check uses it |
| `list_tickets` | `tickets` | The board, filtered by status |
| `get_ticket` | `tickets` | One ticket in full, including its sku/lease/invoice links |
| `update_ticket_status` | `tickets` | Close or park a ticket, appending a dated note |
| `check_stock_for_order` | `inventory` | On-hand vs requested, and the shortfall |
| `list_stock_for_sku` | `inventory` | Every size of one SKU, for offering alternatives |
| `get_pricing` | `pricing` | Unit cost, list price, margin per unit |
| `quote_discount` | `pricing` | Prices a proposed discount and gives the break-even |
| `list_vendors` | `vendors` | Who supplies what, and their lead times |
| `get_vendor_status` | `vendors`, `invoices`, `desk` | Whether a vendor will ship, and when an order would land |
| `get_lease` | `leases`, `desk` | Lease terms plus days until rent is due |
| `list_leases` | `leases`, `desk` | Every lease with its next due date |
| `get_cash_balance` | `cash_accounts` | The hard ceiling on everything |
| `list_invoices` | `invoices`, `vendors`, `desk` | What is owed, to whom, how overdue |
| `request_payment_approval` | `approvals`, `cash_accounts` | Parks a payment for a human. Moves no money |
| `list_approvals` | `approvals` | What is waiting on, or has already been given, a decision |
| `decide_approval` | `approvals` | A **human's** approve/reject. Refuses agent names |
| `pay_approved_request` | `payments`, `cash_accounts`, `invoices`, `leases`, `approvals` | The only tool that moves money |
| `list_payments` | `payments` | The audit trail of what was paid and who approved it |
| `save_customer_draft` | `drafts` | Saves a message to the board. Sends nothing |
| `list_drafts` | `drafts` | Drafts waiting for a person to review |

`approvals` and `drafts` are created by the server with `CREATE TABLE IF NOT EXISTS`, so
resetting the shop by copying the original database still works.

---

## 7. Safety and cost limits

### Guardrails a real business would want

- **No agent can move money.** The split is enforced in code, not in a prompt: agents can
  only reach `request_payment_approval`, which writes a pending row. `pay_approved_request`
  refuses anything not already marked `approved` by a person. A prompt saying "ask before
  paying" is a suggestion; this is a wall.
- **The approver must be a human.** `decide_approval` rejects `boss`, `accounting`, and the
  other agent names outright, so an agent cannot launder its own request through the
  approval route.
- **No negative balances, ever.** The pay tool refuses rather than overdrawing, so a
  mistaken approval cannot put the shop underwater. Cash only leaves this shop.
- **Nothing reaches a customer or vendor.** Messages are saved as drafts for a person to
  review and send. No email, no vendor contact.
- **No invented facts.** Every number comes from a tool reading a table; a missing record
  returns `found: False` rather than a plausible guess. This matters most for customer
  messages, where a confident wrong delivery date is worse than saying "we will confirm".
- **A full audit trail.** Every tool call, argument, result, and delegation is recorded
  with who asked whom, so a decision can be reconstructed afterwards — including the name
  of the person who approved each payment.
- **The original data is never touched.** Agents write only to the working copy.

### What a real business would still want to add

Spending caps per ticket and per day; a second approver above a threshold; rate limits on
how often the team can be run; alerting when an agent is refused something; and a periodic
human review of the drafts, since a polite, fluent, wrong message is the failure mode
least likely to be noticed.

### Keeping token use in check

- **One model everywhere** — `gpt-6-luna` — so no run quietly escalates to a costlier one.
- **A delegation budget shared across the run** (`max_delegations = 8`), held in one object
  so concurrent delegations cannot each spend it. When it runs out, further delegation is
  refused with a message telling the agent to answer with what it has.
- **A depth limit** (`max_depth = 3`) so agents cannot hand work back and forth forever.
- **A run-wide request ceiling** (`request_limit = 40`), since specialists share the Boss's
  usage tally rather than each getting a fresh budget.
- **Narrow questions.** Every prompt tells the agent to ask one specific question and stop,
  rather than forwarding the whole ticket, which is what makes multi-agent chats expensive.
- **Truncated audit values**, so one large tool result cannot bloat the log.

---

## 8. Backend routes

Run from `backend/` with `uvicorn main:app --reload --port 8000`.

| route | what it does |
|---|---|
| `GET /` | Health check; lists the routes the dashboard uses |
| `GET /tickets` | Every ticket with its status and whether it is open, plus the shop date |
| `POST /tickets/{ticket_id}/run` | Puts the agent team on that ticket; returns the Boss's resolution, delegations used, and tokens spent |
| `GET /events` | Recent agent events — which agent, which tool, what result — so the board can refresh (`?limit=`, `?run_id=`) |
| `GET /approvals` | Payment requests the agents prepared, by status (`?status=pending`) |
| `POST /approvals/decide` | A human approves or rejects; **this is the only route that moves cash**, and it pays immediately on approval |
| `GET /cash` | The current checking balance plus every payment made and who approved it |
| `GET /drafts` | Customer message drafts; nothing here has been sent |
| `POST /reset` | Copies the original database over the working copy for a fresh run (`?clear_audit=true` also clears the log) |

---

## 9. Tools added during the run

Three tools were missing and only showed up once the agents were actually working tickets.
They are part of the server now.

| tool | table(s) | why it had to exist |
|---|---|---|
| `get_invoice(invoice_id)` | `invoices`, `vendors`, `payments`, `desk` | Agents could only list *open* invoices. Once invoice 501 was paid it vanished from that list, and Accounting reported a "data discrepancy" instead of "it is paid". This tool answers about one invoice whatever its status, and shows the payment that settled it. |
| `draft_purchase_order(sku, size, qty, vendor_id, requested_by, ticket_id)` | `purchase_orders`, `pricing`, `vendors`, `invoices`, `approvals` | The team could diagnose a shortfall but had no way to *order* the restock, so ticket 101 could never close. Prices the order, refuses if the vendor is blocked, and parks a payment approval for a human. |
| `list_purchase_orders(status)` | `purchase_orders` | Lets agents see what has already been ordered instead of drafting a duplicate. |
| `cancel_approval(approval_id, cancelled_by, reason)` | `approvals`, `purchase_orders` | A request a human approved but the shop cannot afford would otherwise sit approved and unpayable forever. Human-only, same as approving. |

`purchase_orders` is also created with `CREATE TABLE IF NOT EXISTS`, so a reset still works.

When a purchase-order approval is paid, `pay_approved_request` marks the order `ordered`
and records the expected arrival.

---

## 10. The dashboard

React + Vite + TypeScript in `frontend/`, talking to `http://localhost:8000`. Full design
reasoning is in `output/design.md`.

- **The board** — the three tickets as cards in a left-to-right carousel, colour-coded by
  status, resolved cards washed green.
- **Agent lanes** — one column per agent in its own fixed colour, holding what it
  concluded, what blocked it, the facts it used with their numbers, and chips for every
  MCP tool it called. The chips make the audit trail glanceable.
- **The verdict** — the Boss's decision, reasoning, actions, and the delegation and token
  count for the run.
- **Waiting on you** — approval cards that state the arithmetic (`$3,400.00 → $2,560.00`)
  before you click. The approver's name is an editable field because it is written into
  the permanent `payments` record.
- **Cash** — in the header, the largest number on the page; it flashes amber when a
  payment goes through.
- **Drafts and ledger** — every draft labelled unsent, every payment showing who approved
  it.

Start it with `npm run dev` from `frontend/`; the backend allows `http://localhost:5173`.

---

## 11. What the full run showed

Starting balance **$3,400.00**, ending balance **$152.00**, all three tickets resolved.

| ticket | passes | agents | cash |
|---|---|---|---|
| 101 | 7 | boss, inventory, accounting, customer_service | −$840.00 invoice, −$8.00 restock |
| 102 | 3 | boss, facilities, accounting | −$2,400.00 rent |
| 103 | 5 | boss, accounting, inventory, customer_service | $0.00 — the $264.00 restock was refused |

$3,400.00 − $840.00 − $8.00 − $2,400.00 = **$152.00**, matching `cash_accounts`.

Two findings worth recording:

1. **Full connectivity was barely used.** Every agent can call every other, but across 15
   runs and 900 audit steps there was exactly **one** sideways delegation
   (`customer_service → inventory`). Everything else was the Boss fanning out and
   combining the answers. The capability is there; the work did not call for it.
2. **The code-level guardrails did the real work.** A human approved a $264.00 purchase
   order and the pay tool refused it anyway, because $152.00 would not cover it. The rules
   written into tools held every time; the rules written only into prompts (call Inventory
   first, sequence competing obligations) were followed inconsistently.
