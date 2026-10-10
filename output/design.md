# Dashboard design notes

The brief was a desk someone would actually want to sit at. The thing I kept coming back
to is that this is a page where a person spends money. It has to feel calm enough to read
carefully and clear enough that nobody approves $2,400.00 by accident.

## The idea: a desk, not a log viewer

Most agent demos render a scrolling transcript. That is the wrong shape here, because the
question a shopkeeper has is not "what happened next" but "**who said what, and do I
believe them**". So the layout is organised by *person*, not by time: each agent gets its
own column, in its own colour, holding what it concluded and which tools it used to get
there. You read across the agents the way you would read around a table of colleagues.

## Layout

Four bands, top to bottom, in the order a person actually needs them:

1. **The header** — who you are and what you have. The cash balance lives here, never
   scrolls out of mind, and is the largest number on the page.
2. **The board** — the three tickets as cards in a left-to-right carousel.
3. **The run** — the selected ticket, its agent lanes, and the Boss's verdict.
4. **Waiting on you** — approvals, then the drafts and the ledger at the foot.

Money sits at the top and bottom: the balance in the header, the payments ledger at the
end. Everything the agents do happens in between those two facts.

### Carousels, left to right

The board, the agent lanes, the approvals and the drafts are all horizontally scrolling
rows with scroll-snap. This was a deliberate choice over stacking: **a vertical list would
push the cash balance off the screen** as the team worked. Sideways scrolling keeps the
page one screen tall, so the balance, the ticket you are working, and the approve button
are visible together. The board has arrow buttons; the rest are drag or trackpad, because
adding four sets of arrows would have cluttered a page that is meant to feel quiet.

## How the agents read differently

Each agent has a fixed identity that never changes across the page:

| agent | colour | glyph |
|---|---|---|
| Boss | pastel purple | B |
| Inventory | pastel blue | I |
| Accounting | pastel green | A |
| Facilities | pastel yellow | F |
| Customer Service | pastel red | C |

The colour is on the lane background, the border, the avatar, the agent's name **and the
borders of its tool chips**, so a tool chip is identifiable as "something Accounting did"
without reading a word. Green for Accounting is doing real work — money is the thing you
scan for — and red for Customer Service marks the one agent whose output a customer would
eventually read.

Inside a lane the information is ordered by how much a human needs it:

1. **What the agent concluded**, in its own words — the first thing you read.
2. **A blocked note**, if anything stopped it, on a white strip with a red left border, so
   a blocker interrupts the colour field instead of blending into it.
3. **The facts it relied on**, as a short list with the actual numbers, capped at four so
   a lane stays skimmable.
4. **The tools it called**, as small monospace chips with a count.

That last part matters more than it looks. The chips are what make the agents *auditable
at a glance*: you can see that Inventory called `Get vendor status` and therefore that its
claim about shipping is grounded in a lookup rather than invented. Hovering a chip shows
the arguments it was called with. It is the audit trail, made glanceable.

## Resolved tickets and cash

**Resolved tickets** are marked three ways, because one signal is easy to miss: the status
pill turns green, the card gets a soft green wash fading from the top, and the Boss's
verdict block carries the same pill. The wash is the part I like — a resolved card reads as
*settled* from across the room, before you read a single word.

Status colours carry meaning consistently: yellow for open (something wants attention),
blue for awaiting approval (the ball is in your court), green for resolved, red for
blocked.

**Cash** is the emotional centre of the page, so it gets the most deliberate treatment.
The balance sits in a green card in the header in a serif face at 28px — the only number
on the page that large. When an approved payment goes through, the card **flashes amber and
scales up briefly**, then settles back to green. It is a small animation and it is the
thing I would keep if I had to throw everything else away: money leaving the shop should be
felt, not silently rerendered.

Each approval card does the arithmetic for you before you click: `$3,400.00 → $2,560.00`,
in monospace, so the consequence of approving is stated rather than implied. The approve
button is solid green and the reject button is a quiet outline — not to nudge you toward
approving, but because reject is reversible and approve is not, so approve is the one that
should be deliberate and clearly labelled.

Below, the ledger lists every payment with **the name of the person who approved it**. That
column exists to make the central rule of this homework visible: agents prepare, humans
pay.

## Type and colour

- **Fraunces** (serif) for headings, numbers and agent names — it gives the page the
  feeling of a shop's ledger rather than a SaaS dashboard, and it makes the cash figure
  look like money.
- **Inter** for body text, because it stays readable at 13px in a dense lane.
- **JetBrains Mono** for SKUs, tool names, dates and balances — anything that is an
  identifier or a figure you might need to copy exactly.

The palette is Google's blue / red / yellow / green pushed to pastel: `#e3edfb`, `#fae4e2`,
`#fbf1d9`, `#e2f0e6`, on a warm off-white (`#fcfbf9`) rather than pure white. Pure white
plus five colours reads like a toy; the warm paper tone makes the pastels sit down. Borders
are a mid-tone of each tint so cards have definition without hard outlines.

## Small things that make it feel like a desk

- **"Five agents work the board. You hold the cheque book."** — the tagline states the
  deal in one line.
- **The working strip** — three coloured dots bobbing in sequence while the team runs, in
  the Boss, Inventory and Accounting colours, with "agents are talking to each other…".
  It makes a 60-second wait feel like watching people work rather than a frozen page.
- **The empty approvals state** reads "Agents can prepare a payment, but only you can
  release it" — the guardrail stated where you would notice it.
- **Drafts are labelled "unsent draft"** on every card, and the section says "Nothing has
  been sent." Said twice on purpose.
- **"approving as" is an editable field**, not a hardcoded name, because that name is
  written into the permanent `payments` record.
- **Reset is a ghost button** in the corner — reachable, never inviting.

## Restraint

The brief asked for few clickable things. The whole page has four kinds of interaction:
pick a ticket, start the team, approve or reject, reset. Everything else is reading. There
are no tabs, no modals, no settings, no expand-collapse. The agent lanes show their
reasoning permanently rather than hiding it behind a disclosure, because hiding an agent's
reasoning behind a click is exactly how people stop checking it.
