export function score(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(0) : "—";
}

export function money(value: unknown) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "Unknown";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: n >= 1_000_000_000 ? 1 : 0,
    notation: n >= 1_000_000_000 ? "compact" : "standard",
  }).format(n);
}

export function titleCase(value: unknown) {
  if (!value) return "Unknown";
  return String(value).replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}
