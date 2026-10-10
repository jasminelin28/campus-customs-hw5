import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  agent_event,
  approval,
  cash_response,
  decide_approval,
  draft,
  fetch_approvals,
  fetch_cash,
  fetch_drafts,
  fetch_events,
  fetch_tickets,
  reset_shop,
  run_result,
  run_ticket,
  ticket,
} from "./api";
import { pretty_tool, style_for } from "./agent_style";

const money = (value: number) =>
  value.toLocaleString("en-US", { style: "currency", currency: "USD" });

const ticket_kind: Record<string, string> = {
  customer_order: "Customer order",
  rent_notice: "Rent notice",
  price_override: "Discount request",
};

export default function App() {
  const [tickets, set_tickets] = useState<ticket[]>([]);
  const [date_today, set_date_today] = useState("");
  const [selected_id, set_selected_id] = useState<number | null>(null);
  const [events, set_events] = useState<agent_event[]>([]);
  const [cash, set_cash] = useState<cash_response | null>(null);
  const [approvals, set_approvals] = useState<approval[]>([]);
  const [drafts, set_drafts] = useState<draft[]>([]);
  const [running, set_running] = useState(false);
  const [result, set_result] = useState<run_result | null>(null);
  const [error, set_error] = useState<string | null>(null);
  const [approver, set_approver] = useState("Jasmine Lin");
  const [flash_cash, set_flash_cash] = useState(false);

  const board_ref = useRef<HTMLDivElement>(null);

  const load_board = useCallback(async () => {
    try {
      const [ticket_data, cash_data, approval_data, draft_data] =
        await Promise.all([
          fetch_tickets(),
          fetch_cash(),
          fetch_approvals("all"),
          fetch_drafts(),
        ]);
      set_tickets(ticket_data.tickets);
      set_date_today(ticket_data.date_today);
      set_cash(cash_data);
      set_approvals(approval_data.approvals);
      set_drafts(draft_data.drafts);
      set_error(null);
    } catch (problem) {
      set_error(
        "Cannot reach the backend on http://localhost:8000. Start it with: uvicorn main:app --reload --port 8000"
      );
    }
  }, []);

  useEffect(() => {
    load_board();
  }, [load_board]);

  // Picking a ticket loads what the team already did on it, so a finished run
  // can be read back later instead of only while it is happening.
  useEffect(() => {
    if (selected_id === null) return;
    fetch_events(200, undefined, selected_id)
      .then((data) => set_events(data.events))
      .catch(() => {
        /* the board still works without the history */
      });
  }, [selected_id]);

  // While a ticket is running, poll the event feed so the desk stays live.
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      try {
        const data = await fetch_events(200, undefined, selected_id ?? undefined);
        set_events(data.events);
      } catch {
        /* a dropped poll is not worth interrupting the run */
      }
    }, 1200);
    return () => clearInterval(timer);
  }, [running, selected_id]);

  const selected = tickets.find((t) => t.id === selected_id) ?? null;

  const run_selected = async () => {
    if (selected_id === null) return;
    set_running(true);
    set_result(null);
    set_error(null);
    try {
      const run = await run_ticket(selected_id);
      set_result(run);
      const data = await fetch_events(200, run.run_id);
      set_events(data.events);
      await load_board();
    } catch (problem) {
      set_error(String(problem));
    } finally {
      set_running(false);
    }
  };

  const decide = async (approval_id: number, decision: "approved" | "rejected") => {
    try {
      const outcome = await decide_approval(approval_id, decision, approver);
      await load_board();
      if (outcome.payment) {
        set_flash_cash(true);
        setTimeout(() => set_flash_cash(false), 1600);
      }
    } catch (problem) {
      set_error(String(problem));
    }
  };

  const reset_everything = async () => {
    await reset_shop();
    set_events([]);
    set_result(null);
    set_selected_id(null);
    await load_board();
  };

  // Events belonging to the ticket on screen, oldest first.
  const run_events = useMemo(() => {
    if (selected_id === null) return [];
    return events.filter((e) => e.ticket_id === selected_id);
  }, [events, selected_id]);

  // One lane per agent, so you can read who did what at a glance.
  const lanes = useMemo(() => {
    const grouped = new Map<string, agent_event[]>();
    for (const event of run_events) {
      if (event.agent === "human") continue;
      const list = grouped.get(event.agent) ?? [];
      list.push(event);
      grouped.set(event.agent, list);
    }
    return [...grouped.entries()];
  }, [run_events]);

  const pending = approvals.filter((a) => a.status === "pending");

  const scroll_board = (direction: -1 | 1) => {
    board_ref.current?.scrollBy({ left: direction * 360, behavior: "smooth" });
  };

  return (
    <div className="desk">
      <header className="desk_header">
        <div>
          <div className="wordmark">Campus Customs</div>
          <h1>Operations Desk</h1>
          <p className="tagline">
            Five agents work the board. You hold the cheque book.
          </p>
        </div>

        <div className="header_right">
          <div className={`cash_card ${flash_cash ? "cash_flash" : ""}`}>
            <span className="cash_label">checking</span>
            <span className="cash_value">
              {cash ? money(cash.balance) : "—"}
            </span>
            <span className="cash_note">
              {cash && cash.total_paid > 0
                ? `${money(cash.total_paid)} paid out`
                : "nothing paid yet"}
            </span>
          </div>
          <div className="desk_date">shop date · {date_today || "—"}</div>
          <button className="ghost_button" onClick={reset_everything}>
            Reset shop
          </button>
        </div>
      </header>

      {error && <div className="error_strip">{error}</div>}

      {/* ---------------------------- THE BOARD ---------------------------- */}
      <section className="board_section">
        <div className="section_head">
          <h2>The board</h2>
          <div className="carousel_controls">
            <button onClick={() => scroll_board(-1)} aria-label="scroll left">
              ‹
            </button>
            <button onClick={() => scroll_board(1)} aria-label="scroll right">
              ›
            </button>
          </div>
        </div>

        <div className="carousel" ref={board_ref}>
          {tickets.map((t) => {
            const is_selected = t.id === selected_id;
            return (
              <article
                key={t.id}
                className={`ticket_card ${is_selected ? "selected" : ""} ${
                  t.is_open ? "" : "done"
                }`}
                onClick={() => {
                  set_selected_id(t.id);
                  set_result(null);
                }}
              >
                <div className="ticket_top">
                  <span className="ticket_id">#{t.id}</span>
                  <span className={`status_pill status_${t.status}`}>
                    {t.status.replace(/_/g, " ")}
                  </span>
                </div>
                <h3>{t.subject}</h3>
                <div className="ticket_kind">
                  {ticket_kind[t.type] ?? t.type}
                </div>
                <div className="ticket_from">from {t.requester}</div>

                <div className="ticket_tags">
                  {t.sku && (
                    <span className="tag">
                      {t.sku}
                      {t.size ? ` · ${t.size}` : ""}
                    </span>
                  )}
                  {t.qty !== null && <span className="tag">qty {t.qty}</span>}
                  {t.lease_id !== null && (
                    <span className="tag">lease {t.lease_id}</span>
                  )}
                  {t.invoice_id !== null && (
                    <span className="tag tag_warn">
                      invoice {t.invoice_id}
                    </span>
                  )}
                </div>

                <p className="ticket_notes">{t.notes}</p>
              </article>
            );
          })}
        </div>
      </section>

      {/* -------------------------- SELECTED TICKET ------------------------ */}
      {selected && (
        <section className="run_section">
          <div className="run_head">
            <div>
              <h2>
                Ticket #{selected.id} · {selected.subject}
              </h2>
              <p className="run_sub">
                {running
                  ? "The team is working. Watch the lanes fill in."
                  : run_events.length > 0
                  ? "Run complete. Here is what each agent did."
                  : "Nobody has worked this ticket yet."}
              </p>
            </div>
            <button
              className="run_button"
              onClick={run_selected}
              disabled={running}
            >
              {running ? "Agents working…" : "Start the team"}
            </button>
          </div>

          {running && (
            <div className="working_strip">
              <span className="pulse" />
              <span className="pulse" />
              <span className="pulse" />
              <span>agents are talking to each other…</span>
            </div>
          )}

          {/* Agent lanes — a horizontal carousel, one column per agent */}
          {lanes.length > 0 && (
            <div className="carousel lanes">
              {lanes.map(([agent, agent_events]) => {
                const style = style_for(agent);
                const tools = agent_events.filter(
                  (e) => e.event === "tool_call" && e.detail.tool !== "final_result"
                );
                const answer = [...agent_events]
                  .reverse()
                  .find(
                    (e) =>
                      e.event === "delegation_answered" || e.event === "run_finished"
                  );

                return (
                  <article
                    key={agent}
                    className="lane"
                    style={{
                      background: style.tint,
                      borderColor: style.edge,
                    }}
                  >
                    <div className="lane_head">
                      <span
                        className="avatar"
                        style={{ background: style.edge, color: "#ffffff" }}
                      >
                        {style.glyph}
                      </span>
                      <div>
                        <div className="lane_name" style={{ color: style.ink }}>
                          {style.label}
                        </div>
                        <div className="lane_role">{style.role}</div>
                      </div>
                    </div>

                    {answer && (
                      <p className="lane_said">
                        {answer.detail.summary ?? answer.detail.decision ?? ""}
                      </p>
                    )}

                    {answer?.detail.blocked_by && (
                      <div className="blocked_note">
                        blocked · {answer.detail.blocked_by}
                      </div>
                    )}

                    {Array.isArray(answer?.detail.facts_used) &&
                      answer!.detail.facts_used.length > 0 && (
                        <ul className="fact_list">
                          {answer!.detail.facts_used
                            .slice(0, 4)
                            .map((fact: string, index: number) => (
                              <li key={index}>{fact}</li>
                            ))}
                        </ul>
                      )}

                    <div className="lane_tools_label">
                      tools used ({tools.length})
                    </div>
                    <div className="tool_chips">
                      {tools.slice(0, 8).map((event, index) => (
                        <span
                          key={index}
                          className="tool_chip"
                          style={{ borderColor: style.edge, color: style.ink }}
                          title={JSON.stringify(event.detail.arguments ?? {})}
                        >
                          {pretty_tool(event.detail.tool)}
                        </span>
                      ))}
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {/* The Boss's final call */}
          {result && (
            <div className="verdict">
              <div className="verdict_head">
                <span className={`status_pill status_${result.resolution.status}`}>
                  {result.resolution.status.replace(/_/g, " ")}
                </span>
                <span className="verdict_meta">
                  {result.resolution.agents_consulted.length} specialists ·{" "}
                  {result.delegations_used} delegations ·{" "}
                  {result.total_tokens.toLocaleString()} tokens
                </span>
              </div>
              <h3>{result.resolution.decision}</h3>
              <p className="verdict_why">{result.resolution.reasoning}</p>
              {result.resolution.actions_taken.length > 0 && (
                <ul className="action_list">
                  {result.resolution.actions_taken.map((action, index) => (
                    <li key={index}>{action}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      )}

      {/* ---------------------------- APPROVALS ---------------------------- */}
      <section className="approvals_section">
        <div className="section_head">
          <h2>Waiting on you</h2>
          <div className="approver_field">
            <label htmlFor="approver">approving as</label>
            <input
              id="approver"
              value={approver}
              onChange={(event) => set_approver(event.target.value)}
            />
          </div>
        </div>

        {pending.length === 0 ? (
          <div className="empty_note">
            No payments are waiting. Agents can prepare a payment, but only you
            can release it.
          </div>
        ) : (
          <div className="carousel">
            {pending.map((request) => (
              <article key={request.id} className="approval_card">
                <div className="approval_top">
                  <span className="approval_kind">
                    {request.kind.replace(/_/g, " ")}
                  </span>
                  <span className="approval_amount">{money(request.amount)}</span>
                </div>
                <p className="approval_reason">{request.reason}</p>
                <div className="approval_meta">
                  prepared by {request.requested_by}
                  {request.ticket_id ? ` · ticket #${request.ticket_id}` : ""}
                </div>
                {cash && (
                  <div className="approval_math">
                    {money(cash.balance)} → {money(cash.balance - request.amount)}
                  </div>
                )}
                <div className="approval_buttons">
                  <button
                    className="approve_button"
                    onClick={() => decide(request.id, "approved")}
                  >
                    Approve &amp; pay
                  </button>
                  <button
                    className="reject_button"
                    onClick={() => decide(request.id, "rejected")}
                  >
                    Reject
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* ------------------------- DRAFTS AND LEDGER ----------------------- */}
      {(drafts.length > 0 || (cash?.payments.length ?? 0) > 0) && (
        <section className="bottom_section">
          {drafts.length > 0 && (
            <div className="bottom_block">
              <h2>Drafts on the board</h2>
              <p className="block_sub">Written by the team. Nothing has been sent.</p>
              <div className="carousel">
                {drafts.map((item) => (
                  <article key={item.id} className="draft_card">
                    <div className="draft_to">to {item.audience}</div>
                    <h4>{item.subject}</h4>
                    <p>{item.body}</p>
                    <div className="draft_foot">
                      ticket #{item.ticket_id} · unsent draft
                    </div>
                  </article>
                ))}
              </div>
            </div>
          )}

          {cash && cash.payments.length > 0 && (
            <div className="bottom_block">
              <h2>Money out</h2>
              <p className="block_sub">
                Every payment carries the name of the person who approved it.
              </p>
              <table className="ledger">
                <thead>
                  <tr>
                    <th>what</th>
                    <th>amount</th>
                    <th>date</th>
                    <th>approved by</th>
                  </tr>
                </thead>
                <tbody>
                  {cash.payments.map((item) => (
                    <tr key={item.id}>
                      <td>{item.kind.replace(/_/g, " ")}</td>
                      <td className="amount_cell">{money(item.amount)}</td>
                      <td>{item.paid_at}</td>
                      <td>{item.approved_by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <footer className="desk_footer">
        Campus Customs multi-agent operations · every agent runs gpt-6-luna through
        Portkey · agents prepare payments, people approve them
      </footer>
    </div>
  );
}
