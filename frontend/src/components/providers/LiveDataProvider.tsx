"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  FxRateUpdatedPayload,
  LiveQuote,
  NewsPollCompletedPayload,
  PlatformEvent,
  PriceRefreshCompletedPayload,
} from "@/lib/live-events";
import { PlatformSocket } from "@/lib/websocket-client";

/** Server components re-render at most this often after live events. */
const ROUTER_REFRESH_DEBOUNCE_MS = 2_000;

type LiveDataContextValue = {
  connected: boolean;
  quotes: Record<string, LiveQuote>;
  pricesAsOf: string | null;
  lastPortfolioMarkedAt: string | null;
  lastRefresh: PriceRefreshCompletedPayload | null;
  fxRate: FxRateUpdatedPayload | null;
  lastNewsPoll: NewsPollCompletedPayload | null;
};

const LiveDataContext = createContext<LiveDataContextValue>({
  connected: false,
  quotes: {},
  pricesAsOf: null,
  lastPortfolioMarkedAt: null,
  lastRefresh: null,
  fxRate: null,
  lastNewsPoll: null,
});

export function useLiveData(): LiveDataContextValue {
  return useContext(LiveDataContext);
}

export function useLiveQuote(ticker: string | null | undefined): LiveQuote | null {
  const { quotes } = useLiveData();
  if (!ticker) return null;
  return quotes[ticker.toUpperCase()] ?? null;
}

export function LiveDataProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [connected, setConnected] = useState(false);
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [pricesAsOf, setPricesAsOf] = useState<string | null>(null);
  const [lastPortfolioMarkedAt, setLastPortfolioMarkedAt] = useState<
    string | null
  >(null);
  const [lastRefresh, setLastRefresh] =
    useState<PriceRefreshCompletedPayload | null>(null);
  const [fxRate, setFxRate] = useState<FxRateUpdatedPayload | null>(null);
  const [lastNewsPoll, setLastNewsPoll] =
    useState<NewsPollCompletedPayload | null>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleRouterRefresh = useCallback(() => {
    if (refreshTimer.current) return;
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = null;
      router.refresh();
    }, ROUTER_REFRESH_DEBOUNCE_MS);
  }, [router]);

  const handleEvent = useCallback(
    (event: PlatformEvent) => {
      if (event.type === "quote.batch_updated") {
        setQuotes((current) => {
          const next = { ...current };
          for (const quote of event.payload.quotes) {
            next[quote.ticker.toUpperCase()] = quote;
          }
          return next;
        });
        setPricesAsOf(event.payload.as_of);
        return;
      }

      if (event.type === "fx.rate_updated") {
        setFxRate(event.payload);
        return;
      }

      if (event.type === "price_refresh.completed") {
        setLastRefresh(event.payload);
        scheduleRouterRefresh();
        return;
      }

      if (event.type === "portfolio.marked") {
        setLastPortfolioMarkedAt(event.emitted_at);
        scheduleRouterRefresh();
        return;
      }

      if (event.type === "system_log.entry") {
        scheduleRouterRefresh();
        return;
      }

      if (event.type === "news.poll_completed") {
        setLastNewsPoll(event.payload);
        scheduleRouterRefresh();
      }
    },
    [scheduleRouterRefresh],
  );

  useEffect(() => {
    const socket = new PlatformSocket({
      getToken: async () => {
        const { createClient, isSupabaseConfigured } = await import(
          "@/lib/supabase/client"
        );
        if (!isSupabaseConfigured()) return undefined;
        const supabase = createClient();
        const { data } = await supabase.auth.getSession();
        return data.session?.access_token;
      },
      onEvent: handleEvent,
      onStatusChange: setConnected,
    });
    socket.start();
    return () => {
      socket.stop();
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, [handleEvent]);

  const value = useMemo(
    () => ({
      connected,
      quotes,
      pricesAsOf,
      lastPortfolioMarkedAt,
      lastRefresh,
      fxRate,
      lastNewsPoll,
    }),
    [
      connected,
      quotes,
      pricesAsOf,
      lastPortfolioMarkedAt,
      lastRefresh,
      fxRate,
      lastNewsPoll,
    ],
  );

  return (
    <LiveDataContext.Provider value={value}>
      {children}
    </LiveDataContext.Provider>
  );
}
