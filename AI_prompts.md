# AI Prompts Log — Homework 5: Campus Customs Multi-Agent Operations

Class: MGT409 AI Foundations for Managers
Model used for all agent calls: `gpt-6-luna` via Portkey

This file logs the prompts I typed to my vibe coder while building the assignment.
One section per problem.

---

## Problem 1 — AI prompts log and project setup

**Prompt I typed:**

> I'm starting homework 5 for my AI class. It's a multi-agent shop called Campus
> Customs with an MCP server, a FastAPI backend, and a React dashboard. Before we
> write any code, work only inside the Homework 5 folder. Download the class data
> zip from the course site, unzip it so I have data/campus_customs.db, then make a
> copy called data/campus_customs_new.db. The copy is the one everything writes to,
> and the original stays untouched so I can reset. After that, show me the table
> schema so I know what I'm working with, and start an AI_prompts.md file where you
> log the prompts I type for each problem.

**Follow-up prompt:**

> The schema dump is useful but I also want to see how many rows each table has, so
> I know which tables are actually populated before I design the agents.

*What was lacking after the first prompt:* the first pass only printed the `CREATE
TABLE` statements, so I could see the columns but not whether tables like `payments`
and `invoices` already had data in them.

**Result:** `data/campus_customs.db` (original, untouched) and
`data/campus_customs_new.db` (working copy). Tables: `desk`, `tickets`, `inventory`,
`pricing`, `vendors`, `leases`, `cash_accounts`, `payments`, `invoices`.

---

## Problem 2 — Explore the database and start the harness

**Prompt I typed:**

> Go through every table in the shop database and dump the actual rows, not just the
> schema — it's small enough. Then read the three open tickets closely and work out how
> each one connects to the other tables through its sku, lease_id and invoice_id. Write
> all of this into output/harness.md: a section per table listing the fields with one
> line on why that table matters to the agents, then a section explaining the three
> tickets. Also re-copy the original database over the working copy so I'm starting
> clean.

**Follow-up prompt:**

> The ticket write-ups read like summaries of the ticket text. Trace the actual chain for
> me instead — for the tee order, say what inventory shows, which vendor would restock
> it, and why that vendor's invoice matters. And check whether the cash balance can
> actually cover the rent and the invoice together, because that seems like the real
> constraint.

*What was lacking after the first prompt:* the first version described each ticket in
isolation and missed the dependencies — that invoice 501 belongs to the same vendor who
would reprint the out-of-stock tee, and that rent plus that invoice nearly drains the
account.

**Result:** `output/harness.md` with all nine tables documented, the current state of
the shop as of 2026-08-31, and the three ticket chains including the cash squeeze
($3,240 of obligations against a $3,400 balance).

---

## Problem 3 — MCP server with the first three tools

**Prompt I typed:**

> Build a FastMCP server in mcp_server/ that reads the working copy of the database,
> data/campus_customs_new.db, with the path worked out relative to the server file so it
> runs from anywhere. Give it exactly three tools, one aimed at each open ticket: a stock
> check that takes sku, size and the quantity requested and tells me the shortfall; a
> lease lookup that also says how many days until rent is due; and a pricing lookup that
> gives me the margin. Use the desk table for today's date, never the real date. If a
> lookup finds nothing it should say so rather than make something up. Also write
> mcp_server/README.md and add a section to output/harness.md tying each tool to the
> ticket it unlocks.

**Follow-up prompt:**

> Two problems. You gave me four tools when I asked for three — drop the plain stock
> lookup since the order version already covers it. And the harness lines are too thin:
> don't just say the tool "reads inventory", explain why checking sku and size together
> matters for ticket 101, since the tee only looks out of stock if you check the size.

*What was lacking after the first prompt:* it overshot the tool count, and the harness
entries described what each tool reads without connecting that to why the ticket is
stuck.

**Result:** `mcp_server/server.py` with `check_stock_for_order`, `get_lease`, and
`get_pricing`; `mcp_server/README.md`; and section 4 of `output/harness.md`. Smoke-tested
against the database — shortfalls of 1 (ticket 101) and 12 (ticket 103), rent due in 2
days (ticket 102), and $36.00 margin per hoodie.

---

## Problem 4 — Connect the MCP server and smoke-test the tools

**Prompt I typed:**

> Register the Campus Customs MCP server with my vibe coder by writing a .mcp.json at the
> project root that launches mcp_server/server.py with the project's virtual environment
> python. Then actually connect to it and call all three tools — the size S tee for ticket
> 101, lease 1 for ticket 102, and the navy hoodie pricing for ticket 103. Save the
> evidence in output/mcp_smoke.json with the prompt I asked, the tool name, and the tool
> output for each one.

**Follow-up prompt:**

> Don't just trust the tool output — run the matching SQL against
> data/campus_customs_new.db and put the raw row in the evidence file next to each tool
> result so a grader can see the numbers actually come from the database. Also confirm the
> server really lists all three tools over the protocol, not just that the functions run
> when imported.

*What was lacking after the first prompt:* the first pass called the functions directly in
Python, which proves the code works but not that the MCP server handshakes and exposes the
tools; and the saved output had no independent check that the values came from the database.

**Result:** `.mcp.json` at the project root and `output/mcp_smoke.json`. The server
completed the MCP stdio handshake and listed exactly `check_stock_for_order`, `get_lease`,
and `get_pricing`. All three outputs match the database rows: tee size S at qty 0 in Aisle
B, lease 1 at $2,400.00 due 2026-09-02 (2 days out from desk.date_today), hoodie at $22.00
cost against $58.00 list.

---

## Problem 6 — Expected plan page (written before wiring the backend)

**Prompt I typed:**

> Before the agents are wired up, I want to write down what I think should happen, so I
> can compare later. Build output/desk_tickets.html as a plain double-clickable page with
> tabs for ticket 101, 102 and 103, plus empty Cash and Reflection tabs saying they come
> later. Each ticket tab gets an Expected section now and an empty Actual section I fill
> in after the run. In the Expected section say who the Boss should call first and why,
> every delegation I expect, and which MCP tools that run should use. Keep the colors pale
> but still colorful and don't add clickable things beyond the tabs.

**Follow-up prompt:**

> The plans are too safe — don't have the Boss call all five agents on every ticket, say
> explicitly which agents should NOT be involved and why. And for each ticket commit to an
> outcome I can be wrong about, like whether the ticket can actually reach resolved or
> whether it has to stop at awaiting_approval.

*What was lacking after the first prompt:* the first version listed delegations without
ruling anything out, which makes the plan impossible to score against the real run — a
prediction that includes everyone can't be wrong.

**Result:** `output/desk_tickets.html` with five tabs. Each ticket names a first call with
a reason, the specific delegations expected, the agents deliberately left out, a table of
expected MCP tools, and a falsifiable predicted outcome (101 and 102 stop at
`awaiting_approval`; 103 is the only one that can reach `resolved`).

---

## Problem 5 — The agent team

**Prompt I typed:**

> Build the five agents with PydanticAI: boss, inventory, accounting, facilities and
> customer service. Put each agent's system prompt in its own file under backend/prompts/
> and write them in my own words with the shop rules that agent actually needs — the
> accounting one has to say it can never pay, only prepare a payment for a human. Shared
> types go in backend/models.py. Every agent uses gpt-6-luna through Portkey and nothing
> else. All five agents must be able to delegate to all the others, not just through the
> boss. They reach the database only through the MCP server — do not write a second set of
> shop functions that bypass it. Add whatever MCP tools the agents need to actually work
> the three tickets, including the approval and payment flow. Every step should append to
> output/audit_trail.json without wiping it.

**Follow-up prompt:**

> The audit trail is attributing delegations to "human" instead of the agent that made the
> call, and the delegation count goes down when two agents are called at once. Fix both —
> I want the trail to show who asked whom. Also the money rules should be enforced in the
> tools themselves, not just described in the prompts: the pay tool must refuse if the
> request was not approved by a person, and must refuse any payment that would make the
> balance negative. Test that an agent trying to approve its own request gets rejected.

*What was lacking after the first prompt:* delegation events were logged against the
run's original caller rather than the calling agent, and because each delegation kept its
own copy of the counter, two concurrent delegations overwrote each other's tally. The
guardrails also existed only as prompt instructions, which is a suggestion rather than a
control.

**Result:** `backend/agents.py`, `backend/models.py`, `backend/audit.py`, and five prompt
files. Guardrails verified: an agent naming itself as approver is refused, paying before
approval is refused, and a $99,999 payment against a $2,560 balance is refused.

---

## Problem 7 — FastAPI backend

**Prompt I typed:**

> Write backend/main.py with FastAPI so the React board has something to call. I need
> routes to list the tickets with their status, run the agent team on one ticket, return
> recent agent events so the board can refresh, let a human approve a payment and actually
> move the cash, show the checking balance, and reset the database to the original values.
> Keep reading shop data through the MCP server rather than opening sqlite directly. Then
> actually start it and exercise every route with curl — including approving a payment and
> showing the balance drop.

**Follow-up prompt:**

> Every request is spawning a brand new MCP subprocess and the calls are timing out. Open
> one connection when the app starts and reuse it. Also the events route needs a ticket_id
> filter — once a few runs have piled up, asking for the last 200 events no longer reaches
> back to the first ticket's run, so the board shows nothing for it.

*What was lacking after the first prompt:* a fresh MCP subprocess per request made simple
calls take longer than the curl timeout, and the event feed could only be filtered by run,
which breaks as soon as the log grows.

**Result:** nine routes, all exercised end-to-end. The approval route is the only place
cash moves; a request naming an agent as approver is rejected with a 400.

---

## Problem 8 — React dashboard

**Prompt I typed:**

> Build the dashboard in frontend/ with React, Vite and TypeScript, calling the backend on
> localhost:8000. It needs to list the three tickets, let me pick one and start the agent
> team on it, show what each agent is saying and which tools it used while the ticket runs,
> mark a ticket resolved when the run finishes, let me approve a payment, and show the
> checking balance dropping after I approve. Make it feel like a real desk someone would
> want to sit at — pastel versions of the Google colours, a proper serif for headings, and
> use left-to-right carousels rather than long vertical lists. Allow the Vite origin on the
> backend so the browser lets the page call it. Write output/design.md explaining the
> choices.

**Follow-up prompt:**

> Two things. Give each agent its own fixed colour that follows it everywhere — lane,
> avatar, even the tool chip borders — so I can tell at a glance who did what without
> reading. And make the cash balance react when a payment goes through; right now it just
> silently changes number, and money leaving the shop should be noticeable.

*What was lacking after the first prompt:* the lanes were all the same neutral card, so
telling Accounting from Inventory meant reading every heading, and an approved payment
updated the balance with no acknowledgement at all.

**Result:** `frontend/` with the board, agent lanes, verdict, approvals, drafts and ledger.
Verified in the browser: the lanes fill while the team runs, approving $840.00 drops the
header from $3,400.00 to $2,560.00 with an amber flash, and all three cards turn green.

---

## Problem 9 — The full run

**Prompt I typed:**

> Reset the working database so we start from $3,400 with all three tickets open, then run
> the whole board — 101, 102 and 103 — through the dashboard until each one is actually
> resolved, approving the payments as the human when the agents ask. Fill in the Actual
> section of each ticket tab in output/desk_tickets.html from what really happened: which
> agents worked it, what they delegated, which tools they used. Then itemize the money on
> the Cash tab, starting balance through to ending balance, and the ending number has to
> match cash_accounts exactly. Also save output/resolved_tickets.json and
> output/resolved_board.html with screenshots of the board for each resolved ticket.

**Follow-up prompt:**

> The agents are stalling on things that are my fault, not theirs. Accounting says invoice
> 501 is a "data discrepancy" because it can only list open invoices and the paid one
> disappeared from that list — give it a way to ask about one invoice by id. And ticket 101
> can never close because nothing in the system can actually order the restock; the agents
> can only recommend one. Add a purchase order tool that prices the order and parks it for
> approval, and tell inventory to use it.

*What was lacking after the first prompt:* the run exposed two missing tools. Without
`get_invoice` the agents read a settled bill as corrupted data, and without
`draft_purchase_order` the team could describe the fix for ticket 101 indefinitely but had
no way to carry it out, so the ticket could not legitimately resolve.

**Result:** all three tickets resolved. $3,400.00 − $840.00 − $8.00 − $2,400.00 = $152.00,
matching the database. A fourth payment, a $264.00 hoodie restock, was approved by a human
and still refused by the pay tool because the balance would have gone to −$112.00.

---

## Problem 10 — Reflection

**Prompt I typed:**

> Fill in the Reflection tab on output/desk_tickets.html. Grade how the agents actually did
> on each of the three tickets and say why, then compare what happened against the Expected
> plan I wrote before any of this was built — including the parts I got wrong. Say honestly
> which of these tickets would have been simpler with one agent and tools instead of five
> agents. Then three new problems this shop could hit that my team could solve with the
> tools it has, and three it could not, with the specific tools and agents I would need to
> add. Use the real numbers from this shop, not general statements about AI.

**Follow-up prompt:**

> The "could not solve" section is too easy on me. The honest one is that purchase order 1
> is marked ordered and nothing in my system can ever receive it — the tee stays at qty 0
> forever. And we agreed to sell 8 hoodies and the shop's cash does not move, because there
> is no way to record revenue at all. Lead with the gaps that are already sitting in the
> database right now.

*What was lacking after the first prompt:* the gaps were written as hypothetical future
problems rather than as broken states already present in the working database at the end of
the run.

**Result:** the Reflection tab, with per-ticket grades, a point-by-point expected-vs-actual
table, and the finding that across 15 runs and 900 audit steps there was exactly one
peer-to-peer delegation — the full connectivity I built was almost entirely unused.

---

## Problem 11 — GitHub

**Prompt I typed:**

> Get this ready to push to a public GitHub repo so a grader can clone it and run it. Write
> a requirements.txt with the versions actually installed, a .env.example with no real key,
> and a .gitignore that keeps .env out but still commits both database files so the app
> runs straight after cloning. The README should cover copying the original database over
> the working copy for a clean run, starting the MCP server, the backend and the React
> board, and resetting before a full three-ticket run. Match the file layout in the
> assignment image. Then push it and put the URL in output/github_url.txt.

**Follow-up prompt:**

> Before pushing, check the repo for anything that should not be public — confirm no real
> API key is in any committed file, including the .mcp.json and the audit trail, since the
> agents have been running against a real key all evening.

*What was lacking after the first prompt:* I had set up `.gitignore` but had not actually
verified that no key had leaked into the committed files — the audit trail in particular is
a 900-entry log that nobody had read line by line.

**Result:** the repository, with both database files included and `.env` excluded.
