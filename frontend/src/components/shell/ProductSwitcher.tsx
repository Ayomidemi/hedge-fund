"use client";

import Link from "next/link";
import { theme } from "@/components/ui/theme";

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
  const on = theme.navActive;
  const off = theme.navIdle;

  return (
    <div className="inline-flex items-center gap-1 rounded-lg border border-rule bg-paper p-1">
      <Link href="/" className={`${base} ${active === "capital" ? on : off}`}>
        Capital
      </Link>
      <Link href="/invest" className={`${base} ${active === "invest" ? on : off}`}>
        Invest
      </Link>
    </div>
  );
}
