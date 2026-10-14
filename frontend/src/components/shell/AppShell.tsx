"use client";

import { WorkspaceShell, type WorkspaceNavGroup } from "@/components/shell/WorkspaceShell";

const navigationGroups: WorkspaceNavGroup[] = [
  {
    label: "Workspace",
    items: [
      { label: "Overview", href: "/", icon: "overview" },
      { label: "Cash ledger", href: "/cash-ledger", icon: "cash" },
      { label: "Reports", href: "/reports", icon: "reports" },
    ],
  },
  {
    label: "Discover",
    items: [
      { label: "Market radar", href: "/market-radar", icon: "radar" },
      { label: "Ticker analyst", href: "/ticker-analyst", icon: "research" },
      { label: "Watchlist", href: "/watchlist", icon: "watch" },
      { label: "News", href: "/news", icon: "news" },
      { label: "Research lab", href: "/research-lab", icon: "research" },
    ],
  },
  {
    label: "Manage",
    items: [
      { label: "Opportunity queue", href: "/opportunity-queue", icon: "orders" },
      { label: "Trade journal", href: "/trade-journal", icon: "journal" },
      { label: "Strategy pods", href: "/strategy-pods", icon: "strategy" },
      { label: "Risk centre", href: "/risk-centre", icon: "risk" },
      { label: "Administration", href: "/administration", icon: "settings" },
    ],
  },
];

function isItemActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function titleForPath(pathname: string, activeLabel: string | undefined) {
  const ticker = pathname.match(/^\/ticker\/([^/]+)/i);
  if (ticker) return decodeURIComponent(ticker[1]).toUpperCase();
  if (pathname === "/settings") return "Settings";
  return activeLabel ?? "Capital";
}

export function AppShell({
  children,
  userOrgName,
  canSwitchProducts = false,
}: {
  userOrgName: string | null;
  canSwitchProducts?: boolean;
  children: React.ReactNode;
}) {
  return (
    <WorkspaceShell
      product="capital"
      homeHref="/"
      navigationGroups={navigationGroups}
      accountHref="/settings"
      accountHint="Workspace settings"
      userOrgName={userOrgName}
      canSwitchProducts={canSwitchProducts}
      isItemActive={isItemActive}
      titleForPath={titleForPath}
    >
      {children}
    </WorkspaceShell>
  );
}
