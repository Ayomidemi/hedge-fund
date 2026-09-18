"use client";

import Link from "next/link";

type ProductSwitcherProps = {
  active: "capital" | "invest";
  visible?: boolean;
};

export function ProductSwitcher({ active, visible = true }: ProductSwitcherProps) {
  if (!visible) {
    return null;
  }

  const base =
    "rounded-md px-2.5 py-1 text-xs font-semibold tracking-wide transition";
  const on = "bg-zinc-950 text-white dark:bg-zinc-100 dark:text-zinc-950";
  const off =
    "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-100";

  return (
    <div className="inline-flex items-center gap-1 rounded-lg border border-zinc-200 bg-white p-1 dark:border-zinc-800 dark:bg-zinc-950">
      <Link href="/" className={`${base} ${active === "capital" ? on : off}`}>
        Capital
      </Link>
      <Link href="/invest" className={`${base} ${active === "invest" ? on : off}`}>
        Invest
      </Link>
    </div>
  );
}
