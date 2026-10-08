"use client";

import { useEffect, useState } from "react";
import { getCapitalRiskSettings, saveCapitalRiskSettings, type CapitalRiskSettings as Settings, type CapitalRiskProfile } from "@/lib/api";
import { toast } from "@/components/ui/ToastProvider";

const descriptions = {
  low: "Smaller positions, more cash, tighter loss limits.",
  medium: "Moderate exposure with the current drawdown limit.",
  high: "More positions and larger loss budgets within account limits.",
};
const rows = [
  ["max_position_pct", "Stock position", "%"], ["max_etf_position_pct", "ETF position", "%"],
  ["max_positions", "Open positions", ""], ["cash_reserve_pct", "Minimum cash", "%"],
  ["risk_per_trade_pct", "Planned loss per trade", "%"], ["max_aggregate_risk_pct", "Combined planned loss", "%"],
  ["max_daily_loss_pct", "Daily entry pause", "%"], ["max_drawdown_pct", "Drawdown halt", "%"],
  ["max_sector_pct", "Sector exposure", "%"], ["max_correlated_exposure_pct", "Correlated exposure", "%"],
];

export function CapitalRiskSettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [selected, setSelected] = useState<CapitalRiskProfile>("medium");
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    getCapitalRiskSettings().then((data) => {
      if (active) { setSettings(data); setSelected(data.profile); setError(null); }
    }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Risk settings could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);
  async function save() {
    if (!settings || pending || loading) return;
    setPending(true); setError(null);
    try {
      const data = await saveCapitalRiskSettings(selected, settings.profile);
      setSettings(data); setSelected(data.profile);
      toast.success(`Capital risk set to ${data.profile}.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Changes could not be saved."); }
    finally { setPending(false); }
  }
  return <section aria-labelledby="capital-risk-title">
    <h2 id="capital-risk-title" className="text-lg font-semibold">Capital risk</h2>
    <p className="mt-2 text-sm text-zinc-500">Choose the limits for Capital’s paper trading. Invest has its own account.</p>
    {error && <div role="alert" className="mt-4 text-sm text-red-700 dark:text-red-300">{error} <button type="button" disabled={pending || loading} onClick={() => { setLoading(true); setReload((n) => n + 1); }} className="underline">{loading ? "Reloading…" : "Reload settings"}</button></div>}
    {!settings ? <p className="mt-5 text-sm text-zinc-500">{error ? "Settings unavailable." : "Loading risk limits…"}</p> : <>
      <fieldset disabled={pending || loading} className="mt-6 grid gap-3 sm:grid-cols-3">
        <legend className="sr-only">Risk profile</legend>
        {(["low", "medium", "high"] as const).map((profile) => <label key={profile} className={`cursor-pointer rounded-sm border p-4 ${selected === profile ? "border-emerald-700 bg-emerald-50/50 dark:bg-emerald-950/20" : "border-zinc-200 dark:border-zinc-800"}`}>
          <span className="flex items-center gap-2"><input type="radio" name="capital-risk" value={profile} checked={selected === profile} onChange={() => setSelected(profile)} className="accent-emerald-700" /><span className="text-sm font-medium capitalize">{profile}</span></span>
          <span className="mt-2 block text-xs leading-5 text-zinc-500">{descriptions[profile]}</span>
        </label>)}
      </fieldset>
      <div className="mt-6 flex justify-between text-sm"><span className="font-medium capitalize">{selected} limits</span><span className="text-zinc-500">Saved: <span className="capitalize">{settings.profile}</span></span></div>
      <p className="mt-1 text-xs text-zinc-500">Percentages are of account value, except drawdown, which is measured from its peak.</p>
      <dl className="mt-3 divide-y divide-zinc-200 text-sm dark:divide-zinc-800">{rows.map(([key, label, unit]) => <div key={key} className="flex justify-between gap-4 py-2.5"><dt className="text-zinc-500">{label}</dt><dd className="tabular-nums">{settings.options[selected][key]}{unit}</dd></div>)}</dl>
      <p className="mt-4 text-xs leading-5 text-zinc-500">{settings.notice} Daily loss pauses new entries; exits remain active. Drawdown can exceed its trigger during gaps or unavailable execution.</p>
      <button type="button" disabled={pending || loading || selected === settings.profile} onClick={() => void save()} className="mt-5 rounded-sm bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-950">{pending ? "Saving…" : "Save risk profile"}</button>
    </>}
  </section>;
}
