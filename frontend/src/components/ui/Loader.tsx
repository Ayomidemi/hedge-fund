type LoaderSize = "sm" | "md";

type LoaderProps = {
  label?: string;
  size?: LoaderSize;
  className?: string;
};

const spinnerBySize: Record<LoaderSize, string> = {
  sm: "h-4 w-4 border-2",
  md: "h-5 w-5 border-2",
};

export function Loader({ label = "Loading", size = "md", className = "" }: LoaderProps) {
  return (
    <div
      className={`inline-flex items-center gap-2 text-sm text-zinc-500 ${className}`}
      role="status"
      aria-live="polite"
    >
      <span
        className={`${spinnerBySize[size]} animate-spin rounded-full border-zinc-300 border-t-zinc-700 dark:border-zinc-700 dark:border-t-zinc-200`}
        aria-hidden="true"
      />
      <span>{label}</span>
    </div>
  );
}

export function LoaderCover({ label = "Loading" }: { label?: string }) {
  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/80 dark:bg-zinc-950/80">
      <Loader label={label} />
    </div>
  );
}
