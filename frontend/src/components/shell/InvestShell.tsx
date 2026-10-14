"use client";

import { WorkspaceShell, type WorkspaceNavGroup } from "@/components/shell/WorkspaceShell";

const navigationGroups: WorkspaceNavGroup[] = [
  {
    label: "Workspace",
    items: [
      { label: "Overview", href: "/invest", icon: "overview" },
      { label: "Portfolio", href: "/invest/portfolio", icon: "strategy" },
      { label: "Cash", href: "/invest/cash", icon: "cash" },
      { label: "Activity", href: "/invest/activity", icon: "activity" },
    ],
  },
  {
    label: "Discover",
    items: [
      { label: "Markets", href: "/invest/markets", icon: "radar" },
      { label: "Discover", href: "/invest/discover", icon: "research" },
      { label: "Watchlist", href: "/invest/watchlist", icon: "watch" },
      { label: "News", href: "/invest/news", icon: "news" },
    ],
  },
];

function isItemActive(pathname: string, href: string) {
  if (pathname === "/invest/profile") return false;
  if (pathname.startsWith("/invest/orders")) return href === "/invest/portfolio";
  if (
    pathname.startsWith("/invest/instruments/") ||
    pathname.startsWith("/invest/fixed-income/") ||
    pathname === "/invest/search"
  ) {
    return href === "/invest/markets";
  }
  if (href === "/invest") return pathname === "/invest";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function titleForPath(pathname: string, activeLabel: string | undefined) {
  if (pathname === "/invest/profile") return "Account";
  if (pathname === "/invest/search") return "Search";
  const instrument = pathname.match(/^\/invest\/instruments\/([^/]+)/i);
  if (instrument) return decodeURIComponent(instrument[1]).toUpperCase();
  if (pathname.startsWith("/invest/fixed-income/")) return "Fixed income";
  if (pathname.startsWith("/invest/orders/")) return "Order";
  return activeLabel ?? "Invest";
}

export function InvestShell({
  children,
  userOrgName = null,
  canSwitchProducts = false,
}: {
  children: React.ReactNode;
  userOrgName?: string | null;
  canSwitchProducts?: boolean;
}) {
  return (
    <WorkspaceShell
      product="invest"
      homeHref="/invest"
      navigationGroups={navigationGroups}
      accountHref="/invest/profile"
      accountHint="Your account"
      userOrgName={userOrgName}
      canSwitchProducts={canSwitchProducts}
      isItemActive={isItemActive}
      titleForPath={titleForPath}
    >
      {children}
    </WorkspaceShell>
  );
}
