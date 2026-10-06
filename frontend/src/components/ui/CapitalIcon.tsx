import type { CSSProperties } from "react";

const paths = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  cash: "M3 6h18v14H3z M3 6l14-3v3 M16 11h5v5h-5z",
  radar: "M12 3a9 9 0 1 0 9 9 M12 7a5 5 0 1 0 5 5 M12 12l8-8 M12 11v2",
  research: "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14 M15 15l6 6",
  news: "M4 3h16v18H4z M8 7h8 M8 11h8 M8 15h3 M14 15h2 M8 18h8",
  watch: "M5 4h14v17l-7-4-7 4z",
  strategy: "M4 20V10 M10 20V4 M16 20v-8 M22 20H2",
  risk: "M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6",
  orders: "M4 6h15 M15 2l4 4-4 4 M20 18H5 M9 14l-4 4 4 4",
  journal: "M5 3h14v18H5z M8 7h8 M8 12h8 M8 17h5",
  reports: "M5 3h10l4 4v14H5z M14 3v5h5 M8 17v-4 M12 17V9 M16 17v-6",
  settings: "M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  refresh: "M20 7v5h-5 M4 17v-5h5 M6 7a7 7 0 0 1 12-1l2 3 M4 15l2 3a7 7 0 0 0 12-1",
  activity: "M2 12h5l3-8 4 16 3-8h5",
} satisfies Record<string, string>;

export type CapitalIconName = keyof typeof paths;

export function CapitalIcon({ name, className = "h-4 w-4", style }: { name: CapitalIconName; className?: string; style?: CSSProperties }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className} style={style}><path d={paths[name]} /></svg>;
}
