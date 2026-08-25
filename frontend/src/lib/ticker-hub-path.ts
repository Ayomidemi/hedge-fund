export function tickerHubPath(ticker: string) {
  return `/ticker/${encodeURIComponent(ticker.trim().toUpperCase())}`;
}

export function tickerMarketFromSymbol(ticker: string): "US" | "NG" {
  return ticker.trim().toUpperCase().endsWith(".NG") ? "NG" : "US";
}
