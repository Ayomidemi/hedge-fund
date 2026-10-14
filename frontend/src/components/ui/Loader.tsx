import { theme } from "@/components/ui/theme";

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
      className={`inline-flex items-center gap-2 text-sm ${theme.muted} ${className}`}
      role="status"
      aria-live="polite"
    >
      <span
        className={`${spinnerBySize[size]} ${theme.spinner}`}
        aria-hidden="true"
      />
      <span>{label}</span>
    </div>
  );
}

export function LoaderCover({ label = "Loading" }: { label?: string }) {
  return (
    <div className={theme.cover}>
      <Loader label={label} />
    </div>
  );
}
