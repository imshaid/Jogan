// Bangladesh groups digits in lakhs and crores (1,23,456), as en-IN does.
const taka = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export const tk = (x: number) => `৳${taka.format(Math.round(x))}`;
export const pct = (p: number) => `${Math.round(p * 100)}%`;

export function when(iso: string) {
  return new Date(iso).toLocaleString("en-GB", {
    timeZone: "Asia/Dhaka",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Display bands for P(stock-out) (ASSUMPTION, a UI choice, not a decision rule). Risk is never
// shown by colour alone: every level has a word and a symbol too.
export function riskLevel(p: number): { label: string; icon: string; tone: "high" | "medium" | "low" } {
  if (p >= 0.5) return { label: "High", icon: "▲", tone: "high" };
  if (p >= 0.2) return { label: "Medium", icon: "◆", tone: "medium" };
  return { label: "Low", icon: "●", tone: "low" };
}
