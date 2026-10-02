// Display bands for P(stock-out) (ASSUMPTION, a UI choice, not a decision rule). Risk is never
// shown by colour alone: every level has a word and a shape too, on the map as in the tables.
export type RiskLevel = "high" | "medium" | "low";

export const RISK_BANDS = { high: 0.5, medium: 0.2 } as const;

export const RISK_SHAPE: Record<RiskLevel, string> = { high: "▲", medium: "◆", low: "●" };

export function riskLevel(p: number): RiskLevel {
  if (p >= RISK_BANDS.high) return "high";
  if (p >= RISK_BANDS.medium) return "medium";
  return "low";
}

export const higher = (a: { p_stockout_cash: number; p_stockout_efloat: number }) =>
  Math.max(a.p_stockout_cash, a.p_stockout_efloat);
