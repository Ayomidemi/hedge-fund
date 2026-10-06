"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LiveStatusIndicator } from "@/components/shell/LiveStatusIndicator";
import { ProductSwitcher } from "@/components/shell/ProductSwitcher";
import { CapitalIcon, type CapitalIconName } from "@/components/ui/CapitalIcon";

const navigationGroups: { label: string; items: { label: string; href: string; icon: CapitalIconName }[] }[] = [
  { label: "Workspace", items: [
    { label: "Overview", href: "/", icon: "overview" },
    { label: "Cash ledger", href: "/cash-ledger", icon: "cash" },
    { label: "Reports", href: "/reports", icon: "reports" },
  ] },
  { label: "Discover", items: [
    { label: "Market radar", href: "/market-radar", icon: "radar" },
    { label: "Ticker analyst", href: "/ticker-analyst", icon: "research" },
    { label: "Watchlist", href: "/watchlist", icon: "watch" },
    { label: "News", href: "/news", icon: "news" },
    { label: "Research lab", href: "/research-lab", icon: "research" },
  ] },
  { label: "Manage", items: [
    { label: "Opportunity queue", href: "/opportunity-queue", icon: "orders" },
    { label: "Trade journal", href: "/trade-journal", icon: "journal" },
    { label: "Strategy pods", href: "/strategy-pods", icon: "strategy" },
    { label: "Risk centre", href: "/risk-centre", icon: "risk" },
    { label: "Administration", href: "/administration", icon: "settings" },
  ] },
];

export function AppShell({ children, userOrgName, canSwitchProducts = false }: {
  userOrgName: string | null;
  canSwitchProducts?: boolean;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isActive = (href: string) => href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
  const active = navigationGroups.flatMap(group => group.items).find(item => isActive(item.href));
  const ticker = pathname.match(/^\/ticker\/([^/]+)/i);
  const title = ticker ? decodeURIComponent(ticker[1]).toUpperCase() : pathname === "/settings" ? "Settings" : active?.label ?? "Capital";
  const navigation = navigationGroups.map(group => <div key={group.label} className="mb-6 last:mb-0">
    <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">{group.label}</p>
    <div className="space-y-0.5">{group.items.map(item => <Link key={item.href} href={item.href} aria-current={isActive(item.href) ? "page" : undefined}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition ${isActive(item.href) ? "bg-emerald-50 font-semibold text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-100"}`}>
      <CapitalIcon name={item.icon} className="h-[17px] w-[17px] shrink-0" />{item.label}
    </Link>)}</div>
  </div>);

  return <div className="flex min-h-screen bg-[#f7f8fa] text-zinc-900 dark:bg-[#0c0e11] dark:text-zinc-100">
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-zinc-200/70 bg-white lg:flex dark:border-zinc-800/70 dark:bg-[#111316]">
      <Link href="/" className="flex items-center gap-3 px-6 py-7">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-900 text-white"><CapitalIcon name="strategy" className="h-5 w-5" /></div>
        <span className="text-lg font-semibold tracking-tight">pease<span className="ml-1 font-normal text-zinc-500 dark:text-zinc-400">capital</span></span>
      </Link>
      {canSwitchProducts ? <div className="px-5 pb-5"><ProductSwitcher active="capital" /></div> : null}
      <nav aria-label="Capital navigation" className="flex-1 overflow-y-auto px-3 py-2">{navigation}</nav>
      <Link href="/settings" className="m-3 flex items-center gap-3 rounded-xl border border-zinc-200/70 px-3 py-3 text-sm hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-xs font-semibold dark:bg-zinc-800">{(userOrgName ?? "PC").slice(0, 2).toUpperCase()}</span>
        <span className="min-w-0 flex-1"><span className="block truncate text-xs font-medium">{userOrgName ?? "Your organization"}</span><span className="text-[11px] text-zinc-500">Workspace settings</span></span>
        <CapitalIcon name="settings" className="h-4 w-4 text-zinc-500 dark:text-zinc-400" />
      </Link>
    </aside>
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-zinc-200/70 bg-white px-5 py-4 dark:border-zinc-800/70 dark:bg-[#111316] sm:px-8">
        <div className="flex items-center gap-3 text-sm"><span className="text-zinc-500 dark:text-zinc-400">Capital</span><span className="text-zinc-300 dark:text-zinc-600">/</span><h1 className="font-medium">{title}</h1></div>
        <LiveStatusIndicator />
      </header>
      <details className="border-b border-zinc-200 bg-white px-5 py-3 lg:hidden dark:border-zinc-800 dark:bg-[#111316]">
        <summary className="cursor-pointer text-xs font-medium">Menu</summary>
        <nav aria-label="Capital mobile navigation" className="mt-5 grid grid-cols-2 gap-3">{navigation}</nav>
        <div className="mb-3 flex flex-wrap items-center gap-3"><ProductSwitcher active="capital" visible={canSwitchProducts} /><Link href="/settings" className="text-sm text-zinc-500">Workspace settings →</Link></div>
      </details>
      <main className="flex-1 px-4 py-6 sm:px-8 sm:py-8 xl:px-10">{children}</main>
    </div>
  </div>;
}
