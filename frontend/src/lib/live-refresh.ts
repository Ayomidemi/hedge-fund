/** Coalesce server refreshes without competing with account polling or hidden tabs. */
export function shouldRefreshRoute(pathname: string, eventType: string): boolean {
  if (eventType === "system_log.entry") return pathname.startsWith("/administration");
  if (eventType !== "price_refresh.completed" && eventType !== "portfolio.marked") return false;
  return pathname !== "/" && pathname !== "/opportunity-queue";
}

export function createLiveRefreshScheduler({ refresh, visible, busy, schedule, cancel, delay = 30_000 }: {
  refresh: () => void;
  visible: () => boolean;
  busy: () => boolean;
  schedule: (callback: () => void, delay: number) => ReturnType<typeof setTimeout>;
  cancel: (timer: ReturnType<typeof setTimeout>) => void;
  delay?: number;
}) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let dirty = false;
  let disposed = false;
  function arm(wait: number) {
    if (disposed || timer !== null || !dirty || !visible()) return;
    timer = schedule(() => {
      timer = null;
      if (disposed || !dirty || !visible()) return;
      if (busy()) { arm(5_000); return; }
      dirty = false;
      refresh();
    }, wait);
  }
  return {
    notify() { dirty = true; arm(delay); },
    resume() { arm(delay); },
    dispose() { disposed = true; dirty = false; if (timer !== null) cancel(timer); timer = null; },
  };
}
