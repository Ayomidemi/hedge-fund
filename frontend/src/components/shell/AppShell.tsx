"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navigationItems = [
  { label: "Fund Dashboard", href: "/" },
  { label: "Cash Ledger", href: "/cash-ledger" },
  { label: "Ticker Analyst" },
  { label: "Research Lab" },
  { label: "Strategy Pods" },
  { label: "Risk Centre" },
  { label: "Opportunity Queue" },
  { label: "Trade Journal" },
  { label: "Attribution" },
  { label: "Reports" },
  { label: "Administration" },
];

type AppShellProps = {
  apiStatus: "connected" | "offline";
  children: React.ReactNode;
};

export function AppShell({ apiStatus, children }: AppShellProps) {
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
                {activeLabel === "Cash Ledger" ? "Cash Ledger History" : "Portfolio Control Room"}
              </h1>
            </div>
            <div className="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-900">
              <div
                className={`h-2.5 w-2.5 rounded-full ${
                  apiStatus === "connected" ? "bg-emerald-500" : "bg-red-500"
                }`}
              />
              <span className="font-medium">Backend</span>
              <span className="text-zinc-500">{apiStatus}</span>
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 py-5 sm:px-6 xl:px-8">{children}</main>
      </div>
    </div>
  );
}
