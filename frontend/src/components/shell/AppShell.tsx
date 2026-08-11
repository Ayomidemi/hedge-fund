"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navigationItems = [
  { label: "Fund Dashboard", href: "/" },
  { label: "Cash Ledger", href: "/cash-ledger" },
  { label: "Ticker Analyst", href: "/ticker-analyst" },
  { label: "Research Lab", href: "/research-lab" },
  { label: "Strategy Pods", href: "/strategy-pods" },
  { label: "Risk Centre", href: "/risk-centre" },
  { label: "Opportunity Queue" },
  { label: "Trade Journal" },
  { label: "Attribution" },
  { label: "Reports", href: "/reports" },
  { label: "Settings", href: "/settings" },
];

type AppShellProps = {
  userOrgName: string | null;
  children: React.ReactNode;
};

const pageTitles: Record<string, string> = {
  "Cash Ledger": "Cash Ledger History",
  "Ticker Analyst": "Ticker Research Desk",
  "Research Lab": "Research Lab",
  "Strategy Pods": "Investment Pod Control",
  "Risk Centre": "Central Risk Office",
  Reports: "Monthly Reports",
  Settings: "Account Settings",
};

export function AppShell({ children, userOrgName }: AppShellProps) {
  const pathname = usePathname();
  const activeLabel =
    navigationItems.find((item) => item.href === pathname)?.label ??
    "Fund Dashboard";

  return (
    <div className="flex min-h-screen bg-[#f6f7f4] text-zinc-950 dark:bg-zinc-950 dark:text-zinc-50">
      <aside className="hidden w-72 shrink-0 border-r border-zinc-200 bg-[#fbfbf8] lg:block dark:border-zinc-800 dark:bg-zinc-950">
        <div className="border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-zinc-950 text-sm font-semibold text-white dark:bg-zinc-100 dark:text-zinc-950">
              PC
            </div>
            <div>
              <p className="text-sm font-semibold">Pease Capital</p>
              <p className="text-xs text-zinc-500">Operating system</p>
            </div>
          </div>
        </div>

        <nav className="space-y-1 px-3 py-4">
          {navigationItems.map((item) => {
            const isActive = item.label === activeLabel;
            const className = `block rounded-md px-3 py-2 text-sm ${
              isActive
                ? "bg-zinc-950 font-medium text-white dark:bg-zinc-100 dark:text-zinc-950"
                : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
            }`;

            if (!item.href) {
              return (
                <div
                  key={item.label}
                  className="block rounded-md px-3 py-2 text-sm text-zinc-400 dark:text-zinc-600"
                >
                  {item.label}
                </div>
              );
            }

            return (
              <Link key={item.label} href={item.href} className={className}>
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-zinc-200 bg-[#fbfbf8] px-4 py-4 dark:border-zinc-800 dark:bg-zinc-950 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                {activeLabel}
              </p>
              <h1 className="mt-1 text-2xl font-semibold tracking-normal">
                {pageTitles[activeLabel] ?? "Portfolio Control Room"}
              </h1>
            </div>

            <Link
              href="/settings"
              className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-800 transition hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
            >
              {userOrgName ?? "Your organization"}
            </Link>
          </div>
        </header>

        <main className="flex-1 px-4 py-5 sm:px-6 xl:px-8">{children}</main>
      </div>
    </div>
  );
}
