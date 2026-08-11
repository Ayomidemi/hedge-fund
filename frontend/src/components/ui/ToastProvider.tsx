"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type ToastType = "success" | "error";

export type ToastPosition =
  | "top-right"
  | "top-left"
  | "bottom-right"
  | "bottom-left";

export type ToastOptions = {
  position?: ToastPosition;
};

type ToastItem = {
  id: string;
  type: ToastType;
  message: string;
  position: ToastPosition;
};

type ToastContextValue = {
  push: (type: ToastType, message: string, options?: ToastOptions) => void;
  defaultPosition: ToastPosition;
};

const ToastContext = createContext<ToastContextValue | null>(null);

let pushToast:
  | ((type: ToastType, message: string, options?: ToastOptions) => void)
  | null = null;

export const toast = {
  success(message: string, options?: ToastOptions) {
    pushToast?.("success", message, options);
  },
  error(message: string, options?: ToastOptions) {
    pushToast?.("error", message, options);
  },
};

const positionStyles: Record<
  ToastPosition,
  { container: string; alignment: string }
> = {
  "top-right": {
    container: "top-6 right-6",
    alignment: "items-end",
  },
  "top-left": {
    container: "top-6 left-6",
    alignment: "items-start",
  },
  "bottom-right": {
    container: "bottom-6 right-6",
    alignment: "items-end",
  },
  "bottom-left": {
    container: "bottom-6 left-6",
    alignment: "items-start",
  },
};

function ToastCard({ type, message }: ToastItem) {
  const isSuccess = type === "success";

  return (
    <div
      role="status"
      className={`toast-enter pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-2xl border px-4 py-3.5 shadow-[0_12px_40px_-12px_rgba(24,24,27,0.25)] backdrop-blur-sm ${
        isSuccess
          ? "border-emerald-200/70 bg-[#fbfbf8]/95 text-zinc-800 dark:border-emerald-900/50 dark:bg-zinc-950/95 dark:text-zinc-100"
          : "border-amber-200/80 bg-[#fbfbf8]/95 text-zinc-800 dark:border-amber-900/50 dark:bg-zinc-950/95 dark:text-zinc-100"
      }`}
    >
      <span
        className={`mt-2 h-2 w-2 shrink-0 rounded-full ${
          isSuccess ? "bg-emerald-500" : "bg-amber-500"
        }`}
        aria-hidden
      />
      <p className="text-sm leading-6">{message}</p>
    </div>
  );
}

type ToastProviderProps = {
  children: ReactNode;
  position?: ToastPosition;
};

export function ToastProvider({
  children,
  position = "top-right",
}: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const push = useCallback(
    (type: ToastType, message: string, options?: ToastOptions) => {
      const trimmed = message.trim();
      if (!trimmed) {
        return;
      }

      const id = crypto.randomUUID();
      setToasts((current) => [
        ...current,
        {
          id,
          type,
          message: trimmed,
          position: options?.position ?? position,
        },
      ]);

      window.setTimeout(() => {
        setToasts((current) => current.filter((item) => item.id !== id));
      }, 4500);
    },
    [position],
  );

  useEffect(() => {
    pushToast = push;
    return () => {
      pushToast = null;
    };
  }, [push]);

  const value = useMemo(
    () => ({ push, defaultPosition: position }),
    [push, position],
  );

  const groupedToasts = useMemo(() => {
    const groups: Record<ToastPosition, ToastItem[]> = {
      "top-right": [],
      "top-left": [],
      "bottom-right": [],
      "bottom-left": [],
    };

    for (const item of toasts) {
      groups[item.position].push(item);
    }

    return groups;
  }, [toasts]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {(Object.keys(groupedToasts) as ToastPosition[]).map((corner) => {
        const items = groupedToasts[corner];
        if (items.length === 0) {
          return null;
        }

        const styles = positionStyles[corner];

        return (
          <div
            key={corner}
            aria-live="polite"
            className={`pointer-events-none fixed z-[100] flex w-full max-w-sm flex-col gap-2.5 px-4 sm:px-0 ${styles.container} ${styles.alignment}`}
          >
            {items.map((item) => (
              <ToastCard key={item.id} {...item} />
            ))}
          </div>
        );
      })}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider.");
  }
  return context;
}
