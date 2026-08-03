import { getApiInfo, getHealth } from "@/lib/api";

export default async function Home() {
  let apiStatus: "connected" | "offline" = "offline";
  let apiMessage = "Backend unavailable";

  try {
    const [health, info] = await Promise.all([getHealth(), getApiInfo()]);
    if (health.status === "ok") {
      apiStatus = "connected";
      apiMessage = info.message;
    }
  } catch {
    apiStatus = "offline";
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-wider text-zinc-500">
              Hedge Fund Platform
            </p>
            <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
              Operations Console
            </h1>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span
              className={`h-2 w-2 rounded-full ${
                apiStatus === "connected" ? "bg-emerald-500" : "bg-red-500"
              }`}
            />
            <span className="text-zinc-600 dark:text-zinc-400">
              API {apiStatus === "connected" ? "connected" : "offline"}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-12">
        <section className="rounded-2xl border border-zinc-200 bg-white p-8 dark:border-zinc-800 dark:bg-zinc-950">
          <h2 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
            Platform scaffold ready
          </h2>
          <p className="mt-3 max-w-2xl text-zinc-600 dark:text-zinc-400">
            Backend and frontend are wired up. Feature modules — portfolio,
            strategies, risk, execution — can be added incrementally as scope is
            defined.
          </p>
          {apiStatus === "connected" && (
            <p className="mt-4 text-sm text-emerald-700 dark:text-emerald-400">
              Backend response: {apiMessage}
            </p>
          )}
        </section>

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            "Market Data",
            "Portfolio",
            "Strategies",
            "Risk & Execution",
          ].map((module) => (
            <div
              key={module}
              className="rounded-xl border border-dashed border-zinc-300 p-6 dark:border-zinc-700"
            >
              <h3 className="font-medium text-zinc-900 dark:text-zinc-50">
                {module}
              </h3>
              <p className="mt-2 text-sm text-zinc-500">Coming soon</p>
            </div>
          ))}
        </section>
      </main>
    </div>
  );
}
