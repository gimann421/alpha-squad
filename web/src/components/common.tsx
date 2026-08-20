import { type ReactNode } from "react";

// Explicit BLOCKED/LIMITED-style badges everywhere a status appears (PRODUCT_SPEC.md:
// "surface freshness/provenance and BLOCKED/LIMITED source badges everywhere") -- never a
// generic green checkmark hiding a real limitation.
const BADGE_COLORS: Record<string, string> = {
  AVAILABLE: "#1a7f37",
  COMPLETE: "#1a7f37",
  BUY: "#1a7f37",
  BLOCKED_BY_POLICY: "#9a6700",
  NO_CREDENTIALS: "#9a6700",
  NOT_FOUND: "#9a6700",
  WATCH: "#57606a",
  HOLD: "#57606a",
  ERROR: "#cf222e",
  FAILED: "#cf222e",
  REJECTED: "#cf222e",
  SELL: "#cf222e",
  STRONG: "#1a7f37",
  MEDIUM: "#9a6700",
  WEAK: "#57606a",
};

export function Badge({ value }: { value: string }) {
  const color = BADGE_COLORS[value] ?? "#57606a";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 12,
        fontSize: 12,
        fontWeight: 600,
        color: "white",
        background: color,
      }}
    >
      {value}
    </span>
  );
}

export function AsyncSection<T>({
  loading,
  error,
  data,
  render,
}: {
  loading: boolean;
  error: string | null;
  data: T | null;
  render: (data: T) => ReactNode;
}) {
  // Deliberately no fallback/demo data on error: a fetch failure here means the API (and
  // the real engine behind it) is unreachable, and that must surface as a real error, not
  // silently render stale or fabricated content.
  if (loading) return <p className="muted">Loading…</p>;
  if (error) return <p className="error">Couldn't reach the Alpha Squad API: {error}</p>;
  if (data === null) return <p className="muted">No data.</p>;
  return <>{render(data)}</>;
}
