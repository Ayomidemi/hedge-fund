import type { MarketRadarName } from "./api";

export type RadarView = "all" | "signals" | "watched" | "gaps";
export type RadarSort = "priority" | "gainers" | "losers" | "volume";
export function hasDataGap(name: MarketRadarName) {
  return Boolean(name.stale_reason || name.carried_forward || name.evidence.history_gap)
    || Number(name.evidence.return_sample_count ?? 0) < 20;
}
export function isSignal(name: MarketRadarName) {
  return !name.stale_reason && !name.carried_forward && ["P0", "P1"].includes(name.radar_priority ?? "");
}
export function filterRadarNames(names: MarketRadarName[], options: {
  market: string; industry: string; query: string; view: RadarView; sort: RadarSort;
}) {
  const query = options.query.trim().toLowerCase();
  const numeric = (value: unknown) => value != null && value !== "" && Number.isFinite(Number(value)) ? Number(value) : null;
  const rank = (name: MarketRadarName) => ["P0", "P1", "P2", "P3"].indexOf(name.radar_priority ?? "");
  return names.filter(name => (options.market === "all" || name.jurisdiction === options.market)
    && (!options.industry || `${name.jurisdiction}:${name.industry || name.sector || "Unclassified"}` === options.industry)
    && (!query || `${name.ticker} ${name.name} ${name.industry ?? ""} ${name.sector ?? ""}`.toLowerCase().includes(query))
    && (options.view === "all" || (options.view === "signals" && isSignal(name))
      || (options.view === "gaps" && hasDataGap(name))
      || (options.view === "watched" && (name.on_watchlist || name.in_portfolio))))
    .sort((a, b) => {
      if (options.sort !== "priority") {
        const av = numeric(options.sort === "volume" ? a.volume_ratio : a.change_pct);
        const bv = numeric(options.sort === "volume" ? b.volume_ratio : b.change_pct);
        if (av === null || bv === null) return av === bv ? a.ticker.localeCompare(b.ticker) : av === null ? 1 : -1;
        return (options.sort === "losers" ? av - bv : bv - av) || a.ticker.localeCompare(b.ticker);
      }
      const ar = a.stale_reason || a.carried_forward || rank(a) < 0 ? 9 : rank(a);
      const br = b.stale_reason || b.carried_forward || rank(b) < 0 ? 9 : rank(b);
      return ar - br || (numeric(b.priority_score) ?? 0) - (numeric(a.priority_score) ?? 0) || a.ticker.localeCompare(b.ticker);
    });
}
