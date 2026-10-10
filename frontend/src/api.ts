/** Calls to the Campus Customs backend. */

export const api_base = "http://localhost:8000";

export type ticket = {
  id: number;
  type: string;
  requester: string;
  subject: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  status: string;
  is_open: boolean;
  notes: string | null;
  created_at: string;
};

export type tickets_response = {
  date_today: string;
  count: number;
  open_count: number;
  tickets: ticket[];
};

export type agent_event = {
  run_id: string;
  ticket_id: number | null;
  step: number;
  timestamp: string;
  agent: string;
  caller: string;
  depth: number;
  event: string;
  model: string;
  detail: Record<string, any>;
};

export type resolution = {
  ticket_id: number;
  decision: string;
  reasoning: string;
  agents_consulted: string[];
  actions_taken: string[];
  pending_approvals: number[];
  status: string;
};

export type run_result = {
  run_id: string;
  ticket_id: number;
  resolution: resolution;
  delegations_used: number;
  total_tokens: number;
};

export type approval = {
  id: number;
  ticket_id: number | null;
  kind: string;
  ref_id: number | null;
  amount: number;
  account: string;
  reason: string;
  requested_by: string;
  requested_at: string;
  status: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
};

export type payment = {
  id: number;
  kind: string;
  ref_id: number | null;
  amount: number;
  account: string;
  paid_at: string;
  approved_by: string;
};

export type cash_response = {
  account: string;
  balance: number;
  as_of: string;
  total_paid: number;
  payments: payment[];
};

export type draft = {
  id: number;
  ticket_id: number;
  audience: string;
  subject: string;
  body: string;
  written_by: string;
  written_at: string;
  status: string;
};

async function get_json<T>(path: string): Promise<T> {
  const response = await fetch(`${api_base}${path}`);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}

async function post_json<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${api_base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}

export const fetch_tickets = () => get_json<tickets_response>("/tickets");

export const fetch_events = (
  limit = 120,
  run_id?: string,
  ticket_id?: number
) =>
  get_json<{ count: number; events: agent_event[] }>(
    `/events?limit=${limit}${run_id ? `&run_id=${run_id}` : ""}${
      ticket_id ? `&ticket_id=${ticket_id}` : ""
    }`
  );

export const fetch_cash = () => get_json<cash_response>("/cash");

export const fetch_approvals = (status = "all") =>
  get_json<{ count: number; approvals: approval[] }>(
    `/approvals?status=${status}`
  );

export const fetch_drafts = () =>
  get_json<{ count: number; drafts: draft[] }>("/drafts");

export const run_ticket = (ticket_id: number) =>
  post_json<run_result>(`/tickets/${ticket_id}/run`);

export const decide_approval = (
  approval_id: number,
  decision: "approved" | "rejected",
  decided_by: string,
  note = ""
) =>
  post_json<{ message: string; payment: any }>("/approvals/decide", {
    approval_id,
    decision,
    decided_by,
    note,
  });

export const reset_shop = () => post_json<{ message: string }>("/reset");
