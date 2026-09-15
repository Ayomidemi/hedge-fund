"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ProductSwitcher } from "@/components/shell/ProductSwitcher";

const navigationItems = [
  { label: "Home", href: "/invest" },
  { label: "Discover", href: "/invest/discover" },
  { label: "Markets", href: "/invest/markets" },
  { label: "Search", href: "/invest/search" },
  { label: "Watchlist", href: "/invest/watchlist" },
  { label: "Portfolio", href: "/invest/portfolio" },
  { label: "Orders", href: "/invest/orders" },
  { label: "Cash", href: "/invest/cash" },
  { label: "Profile", href: "/invest/profile" },
];

const pageTitles: Record<string, string> = {
  Home: "Your investing",
  Discover: "What's happening",
  Markets: "Markets",
  Search: "Search",
  Watchlist: "Watchlist",
  Portfolio: "Portfolio",
  Orders: "Orders",
  Cash: "Cash",
  Profile: "Profile",
};

type InvestShellProps = {
  children: React.ReactNode;
};

export function InvestShell({ children }: InvestShellProps) {
  const pathname = usePathname();
  const instrumentMatch = pathname.match(/^\/invest\/instruments\/([^/]+)/i);
  const activeLabel =
    navigationItems.find((item) =>
      item.href === "/invest"
        ? pathname === "/invest"
        : pathname === item.href || pathname.startsWith(`${item.href}/`),
    )?.label ?? "Home";
  const headerTitle = instrumentMatch
    ? decodeURIComponent(instrumentMatch[1]).toUpperCase()
    : (pageTitles[activeLabel] ?? "Pease Invest");
  const headerEyebrow = instrumentMatch ? "Invest" : activeLabel;

  return (
    <div className="flex min-h-screen bg-[#f7f8f5] text-zinc-950 dark:bg-zinc-950 dark:text-zinc-50">
      <aside className="hidden w-64 shrink-0 border-r border-zinc-200 bg-white lg:block dark:border-zinc-800 dark:bg-zinc-950">
        <div className="border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-emerald-800 text-sm font-semibold text-white">
              PI
            </div>
            <div>
              <p className="text-sm font-semibold">Pease Invest</p>
              <p className="text-xs text-zinc-500">You decide the trades</p>
            </div>
          </div>
          <div className="mt-4">
            <ProductSwitcher active="invest" />
          </div>
        </div>
        <nav className="space-y-1 px-3 py-4">
          {navigationItems.map((item) => {
            const isActive = item.label === activeLabel;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block rounded-md px-3 py-2 text-sm ${
                  isActive
                    ? "bg-emerald-800 font-medium text-white"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-zinc-200 bg-white px-4 py-4 dark:border-zinc-800 dark:bg-zinc-950 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                {headerEyebrow}
              </p>
              <h1 className="mt-1 text-2xl font-semibold tracking-normal">{headerTitle}</h1>
            </div>
            <div className="lg:hidden">
              <ProductSwitcher active="invest" />
            </div>
          </div>
          <nav className="mt-4 flex gap-2 overflow-x-auto pb-1 lg:hidden">
            {navigationItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium ${
                  item.label === activeLabel
                    ? "bg-emerald-800 text-white"
                    : "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="flex-1 px-4 py-5 sm:px-6 xl:px-8">{children}</main>
      </div>
    </div>
  );
}
