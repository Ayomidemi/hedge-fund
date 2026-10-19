"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "@/components/ui/ToastProvider";
import { setInvestTradingMode, type InvestHome } from "@/lib/api";

export function InvestAutomation({ home }: { home: InvestHome }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const mode = home.trading_mode ?? "manual";

  async function choose(next: "manual" | "automatic") {
    if (pending || next === mode) return;
    setPending(true);
    try {
      await setInvestTradingMode(next);
      toast.success(next === "automatic" ? "Automatic mode enabled." : "Manual mode enabled.");
      router.refresh();
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "Could not change trading mode.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div role="group" aria-label="Trading mode" className="inline-flex rounded-lg bg-hover p-1">
      {(["manual", "automatic"] as const).map((value) => (
        <button
          key={value}
          type="button"
          aria-pressed={mode === value}
          disabled={pending || mode === value}
          onClick={() => void choose(value)}
          className={`rounded-md px-3.5 py-2 text-xs font-medium capitalize transition focus-visible:outline-2 focus-visible:outline-sky-300 ${pending ? "opacity-50" : ""} ${mode === value ? "bg-action text-action-ink" : "text-muted hover:text-ink"}`}
        >
          {value === "automatic" ? <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" /> : null}
          {value}
        </button>
      ))}
    </div>
  );
}
