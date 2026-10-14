import { theme } from "@/components/ui/theme";

export function PageLoading() {
  return (
    <div className="space-y-4">
      <div className={`h-32 ${theme.skeleton}`} />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className={`h-56 ${theme.skeleton}`} />
        <div className={`h-56 ${theme.skeleton}`} />
      </div>
    </div>
  );
}
