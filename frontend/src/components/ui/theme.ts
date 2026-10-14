/**
 * Pease design system.
 *
 * Surfaces are black and white. Actions — buttons, selected controls, the
 * active nav item — use a very light sky blue. Emerald, red, rose, amber,
 * and sky are reserved for meaning and should not be used as decoration.
 *
 * Color values live in `src/app/globals.css` (`--pease-*`). Class recipes
 * live here. New UI should import these instead of hardcoding a palette.
 */

export const theme = {
  page: "min-h-screen bg-paper text-ink",
  surface: "bg-paper text-ink",
  muted: "text-muted",
  card: "rounded-lg border border-rule bg-paper text-ink",
  navActive: "bg-action font-semibold text-action-ink",
  navIdle: "text-muted hover:bg-hover hover:text-ink",
  action: "bg-action text-action-ink transition hover:bg-action-hover",
  actionQuiet:
    "border border-rule bg-paper text-ink transition hover:border-sky-200 hover:bg-action dark:hover:border-sky-900",
  focusRing:
    "focus:border-sky-300 focus:ring-4 focus:ring-sky-100 dark:focus:border-sky-800 dark:focus:ring-sky-950/40",
  profit: "text-profit",
  profitMark: "bg-emerald-500",
  loss: "text-loss",
  lossMark: "bg-red-500",
  /** Plot bars only. Alerts and danger text use red. */
  plotLoss: "bg-rose-500",
  caution: "text-caution",
  cautionMark: "bg-amber-500",
  info: "text-info",
  skeleton: "animate-pulse rounded-lg bg-zinc-200/80 dark:bg-zinc-800",
  spinner: "animate-spin rounded-full border-zinc-300 border-t-ink dark:border-zinc-700",
  cover: "absolute inset-0 z-10 flex items-center justify-center bg-paper/80",
  toast:
    "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-2xl border bg-paper px-4 py-3.5 text-ink shadow-[0_12px_40px_-12px_rgba(0,0,0,0.25)]",
  toastSuccess: "border-emerald-200 dark:border-emerald-900",
  toastError: "border-red-200 dark:border-red-900",
  lossSurface:
    "border border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200",
} as const;

export const buttonPrimaryClassName =
  `inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${theme.action}`;

export const buttonSecondaryClassName =
  `inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${theme.actionQuiet}`;

export const inputControlClassName =
  `w-full rounded-lg border border-rule bg-paper px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-muted ${theme.focusRing}`;

export const inputClassName = `mt-1.5 ${inputControlClassName}`;
