"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ProductSwitcher } from "@/components/shell/ProductSwitcher";

const navigationItems = [
  { label: "Overview", href: "/invest" },
  { label: "Portfolio", href: "/invest/portfolio" },
  { label: "Markets", href: "/invest/markets" },
  { label: "Discover", href: "/invest/discover" },
  { label: "Watchlist", href: "/invest/watchlist" },
  { label: "News", href: "/invest/news" },
  { label: "Cash", href: "/invest/cash" },
  { label: "Activity", href: "/invest/activity" },
];

export function InvestShell({ children, canSwitchProducts = false }: {
  children: React.ReactNode;
  canSwitchProducts?: boolean;
}) {
  const pathname = usePathname();
  const activeHref = pathname.startsWith("/invest/orders") ? "/invest/portfolio"
    : pathname.startsWith("/invest/instruments/") || pathname.startsWith("/invest/fixed-income/") || pathname === "/invest/search" ? "/invest/markets"
    : navigationItems.find(item => item.href === "/invest" ? pathname === item.href : pathname.startsWith(item.href))?.href;

  return <div className="pease-workspace min-h-screen">
    <header className="border-b border-[var(--pease-rule)] bg-[var(--pease-paper)]">
      <div className="mx-auto max-w-[1440px] px-5 sm:px-10">
        <div className="flex flex-wrap items-center justify-between gap-4 py-6 sm:py-7">
          <Link href="/invest" className="pease-editorial text-2xl sm:text-3xl">Pease <span className="text-stone-500 dark:text-stone-400">Invest</span></Link>
          <div className="flex items-center gap-5">
            <ProductSwitcher active="invest" visible={canSwitchProducts} />
            <Link href="/invest/profile" aria-current={pathname === "/invest/profile" ? "page" : undefined} className="text-sm underline-offset-4 hover:underline">Your account ↗</Link>
          </div>
        </div>
        <nav aria-label="Invest navigation" className="-mb-px flex gap-6 overflow-x-auto sm:gap-8">
          {navigationItems.map(item => <Link key={item.href} href={item.href} aria-current={item.href === activeHref ? "page" : undefined}
            className={`shrink-0 border-b-2 pb-3.5 pt-1 text-sm transition ${item.href === activeHref ? "border-[#526044] font-semibold text-[#39462f] dark:border-stone-300 dark:text-stone-100" : "border-transparent text-stone-500 hover:border-stone-300 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"}`}>{item.label}</Link>)}
        </nav>
      </div>
    </header>
    <main className="mx-auto max-w-[1440px] px-5 py-8 sm:px-10 sm:py-10">{children}</main>
    <footer className="mx-auto mt-10 flex max-w-[1440px] flex-wrap justify-between gap-3 border-t border-[var(--pease-rule)] px-5 py-6 text-xs text-stone-500 sm:px-10">
      <span>Pease Invest</span><span>Paper account · Simulated execution</span>
    </footer>
  </div>;
}
