type WatchlistButtonProps = {
  ticker: string;
  watched: boolean;
  busy: boolean;
  onClick: () => void;
};

export function WatchlistButton({
  ticker,
  watched,
  busy,
  onClick,
}: WatchlistButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      title={watched ? `Remove ${ticker} from watchlist` : `Add ${ticker} to watchlist`}
      aria-label={watched ? `Remove ${ticker} from watchlist` : `Add ${ticker} to watchlist`}
      aria-pressed={watched}
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition ${
        watched
          ? "text-emerald-700 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-950"
          : "text-zinc-400 hover:bg-zinc-100 hover:text-zinc-800 dark:hover:bg-zinc-900 dark:hover:text-zinc-100"
      } disabled:opacity-50`}
    >
      <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
        {watched ? (
          <path
            fill="currentColor"
            d="M5 2.5A1.5 1.5 0 0 0 3.5 4v13.1a.75.75 0 0 0 1.2.6L10 14.2l5.3 3.5a.75.75 0 0 0 1.2-.6V4A1.5 1.5 0 0 0 15 2.5H5Z"
          />
        ) : (
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            d="M5.2 3.2h9.6A1.3 1.3 0 0 1 16.1 4.5v11.8a.6.6 0 0 1-.96.48L10 13.4l-5.14 3.38a.6.6 0 0 1-.96-.48V4.5A1.3 1.3 0 0 1 5.2 3.2Z"
          />
        )}
      </svg>
    </button>
  );
}
