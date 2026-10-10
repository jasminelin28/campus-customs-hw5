# Campus Customs — Multi-Agent Operations

MGT409 AI Foundations for Managers · Homework 5

A small campus apparel shop run by a team of five AI agents, with a human holding the
cheque book. Tickets land on a board — customer orders, rent notices, discount requests —
and the agents read the shop, work out who should handle what, and prepare the work. They
can never spend money on their own: every payment waits for a person to click approve.

Three pieces talk to each other:

| piece | what it is | folder |
|---|---|---|
| **MCP server** | The only path to the shop database. Every agent reads and writes through these tools. | `mcp_server/` |
| **FastAPI backend** | The agent team (PydanticAI) plus the routes the dashboard calls. | `backend/` |
| **React dashboard** | The desk a human sits at to watch the agents and approve payments. | `frontend/` |

All five agents run **`gpt-6-luna` through Portkey**, and nothing else.

---

## The two database files

| file | what it is |
|---|---|
| `data/campus_customs.db` | The **original** shop. Never written to. This is your reset point. |
| `data/campus_customs_new.db` | The **working copy**. The MCP server and backend point here. |

**To get a clean run, copy the original over the working copy:**

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

On Windows PowerShell:

```powershell
Copy-Item data/campus_customs.db data/campus_customs_new.db -Force
```

The backend also exposes `POST /reset`, which does exactly this, and the dashboard has a
**Reset shop** button in the top-right corner that calls it.

Both database files are committed, so you can clone this repository and run it immediately.

---

## Setup

### 1. Python environment

From the project folder:

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

On macOS or Linux the interpreter is `.venv/bin/python` instead.

### 2. Your API key

```bash
cp .env.example .env
```

Then put your Portkey key in it:

```
PORTKEY_API_KEY=your_portkey_api_key_here
```

The real `.env` is in `.gitignore` and is never committed. The backend also checks the
folder one level up, so a shared class `.env` works too.

### 3. Frontend packages

```bash
cd frontend
npm install
```

---

## Running it

### Start the MCP server

The backend launches the MCP server automatically as a subprocess, so **you do not normally
need to start it by hand**. To run it on its own to check it works:

```bash
.venv/Scripts/python.exe mcp_server/server.py
```

It speaks MCP over stdio. `.mcp.json` in the project root registers it with Claude Code,
Cursor or any other MCP client under the name `campus_customs`.

### Start the FastAPI backend

From the `backend/` folder:

```bash
uvicorn main:app --reload --port 8000
```

The API is then on <http://localhost:8000>, with interactive docs at
<http://localhost:8000/docs>. It opens one connection to the MCP server at start-up and
reuses it.

### Start the React board

From the `frontend/` folder:

```bash
npm run dev
```

The desk opens at <http://localhost:5173>. The backend allows that origin so the browser
will let the page call the API. **Start the backend first** — otherwise the board shows a
message telling you it cannot reach it.

---

## Doing a full three-ticket run

1. **Reset the database first**, so cash and tickets start from the original values:

   ```bash
   cp data/campus_customs.db data/campus_customs_new.db
   ```

   Or click **Reset shop** on the dashboard. The starting checking balance is
   **$3,400.00** with all three tickets open.

2. Start the backend, then the frontend.

3. On the board, click a ticket, then **Start the team**. The Boss reads it, delegates to
   whichever specialists it needs, and the lanes fill in as the agents work.

4. When an agent prepares a payment it appears under **Waiting on you**. Put your name in
   the "approving as" field and click **Approve & pay**. That click is the only thing in
   the whole system that moves money. The balance in the header drops.

5. Run the ticket again after approving. A ticket usually takes more than one pass,
   because each pass advances the work only as far as the next human decision.

6. Repeat for tickets 102 and 103.

A full run of the three tickets ends at **$152.00**: $840.00 for the overdue invoice,
$8.00 for the tee restock, $2,400.00 for rent. A fourth payment — a $264.00 hoodie
restock — is refused by the pay tool because the balance will not cover it.

---

## How the money rules are enforced

These live in `mcp_server/server.py`, in code rather than in prompts:

- `request_payment_approval` is as far as any agent can go. It writes a pending row and
  moves nothing.
- `decide_approval` **refuses agent names** outright, so an agent cannot approve its own
  request. A person must decide.
- `pay_approved_request` refuses anything not already approved by a human, and refuses any
  payment that would push the balance below zero. No negative balances.
- A vendor with an open unpaid invoice will not ship — `get_vendor_status` enforces it.
- Customer messages are saved as drafts and **never sent**. No customer is emailed and no
  vendor is contacted.

---

## Project layout

```
hw5/
├── AI_prompts.md            the prompts typed while building this
├── requirements.txt
├── .env.example
├── .gitignore
├── .mcp.json                MCP server registration
├── README.md
├── data/
│   ├── campus_customs.db        original, untouched
│   └── campus_customs_new.db    working copy
├── mcp_server/
│   ├── server.py            all shop tools
│   └── README.md            what each tool does and which table it uses
├── frontend/                React + Vite + TypeScript dashboard
├── backend/
│   ├── main.py              FastAPI routes
│   ├── models.py            shared data types
│   ├── agents.py            the five agents and their delegation wiring
│   ├── audit.py             append-only audit trail
│   └── prompts/
│       ├── boss.md
│       ├── inventory.md
│       ├── accounting.md
│       ├── facilities.md
│       └── customer_service.md
└── output/
    ├── harness.md               tables, tools, agents, routes, safety
    ├── mcp_smoke.json           evidence the MCP tools work
    ├── desk_tickets.html        expected vs actual, cash, reflection
    ├── design.md                dashboard design decisions
    ├── resolved_tickets.json    the full run, ticket by ticket
    ├── resolved_board.html      screenshots of the resolved board
    ├── audit_trail.json         every agent step, appended across runs
    └── github_url.txt
```

## Backend routes

| route | what it does |
|---|---|
| `GET /tickets` | Every ticket with its status |
| `POST /tickets/{id}/run` | Put the agent team on that ticket |
| `GET /events` | Recent agent events, filterable by ticket or run |
| `GET /approvals` | Payments the agents have prepared |
| `POST /approvals/decide` | A human approves or rejects — the only route that moves cash |
| `POST /approvals/{id}/cancel` | Withdraw a request the shop cannot pay |
| `GET /cash` | The checking balance and every payment made |
| `GET /drafts` | Customer drafts, none of them sent |
| `POST /reset` | Restore the original database |
