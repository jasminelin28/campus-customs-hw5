/** How each agent reads on the board: colour, label, and glyph. */

export type agent_style = {
  label: string;
  tint: string;
  edge: string;
  ink: string;
  glyph: string;
  role: string;
};

export const agent_styles: Record<string, agent_style> = {
  boss: {
    label: "Boss",
    tint: "var(--boss_tint)",
    edge: "var(--boss_edge)",
    ink: "var(--boss_ink)",
    glyph: "B",
    role: "routes the ticket, makes the final call",
  },
  inventory: {
    label: "Inventory",
    tint: "var(--inventory_tint)",
    edge: "var(--inventory_edge)",
    ink: "var(--inventory_ink)",
    glyph: "I",
    role: "stock, shortfalls, vendors, lead times",
  },
  accounting: {
    label: "Accounting",
    tint: "var(--accounting_tint)",
    edge: "var(--accounting_edge)",
    ink: "var(--accounting_ink)",
    glyph: "A",
    role: "cash, invoices, margins, approvals",
  },
  facilities: {
    label: "Facilities",
    tint: "var(--facilities_tint)",
    edge: "var(--facilities_edge)",
    ink: "var(--facilities_ink)",
    glyph: "F",
    role: "leases, rent, the shop space",
  },
  customer_service: {
    label: "Customer Service",
    tint: "var(--service_tint)",
    edge: "var(--service_edge)",
    ink: "var(--service_ink)",
    glyph: "C",
    role: "drafts the messages customers read",
  },
  human: {
    label: "You",
    tint: "var(--human_tint)",
    edge: "var(--human_edge)",
    ink: "var(--human_ink)",
    glyph: "Y",
    role: "the person at the desk",
  },
};

export const style_for = (agent: string): agent_style =>
  agent_styles[agent] ?? agent_styles.human;

/** Turn a snake_case tool name into something readable. */
export const pretty_tool = (tool: string): string =>
  tool.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
