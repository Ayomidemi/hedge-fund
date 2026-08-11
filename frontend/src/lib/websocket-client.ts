import { API_BASE_URL } from "@/lib/api";
import { parsePlatformEvent, type PlatformEvent } from "@/lib/live-events";

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;
const KEEPALIVE_INTERVAL_MS = 30_000;

export type PlatformSocketOptions = {
  getToken: () => Promise<string | undefined>;
  onEvent: (event: PlatformEvent) => void;
  onStatusChange?: (connected: boolean) => void;
};

function websocketUrl(token: string): string {
  const base = API_BASE_URL.replace(/^http/, "ws");
  return `${base}/api/ws?token=${encodeURIComponent(token)}`;
}

/**
 * Single WebSocket connection to the platform event stream with automatic
 * reconnection (exponential backoff) and keepalive pings.
 */
export class PlatformSocket {
  private socket: WebSocket | null = null;
  private backoffMs = INITIAL_BACKOFF_MS;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private keepaliveTimer: ReturnType<typeof setInterval> | null = null;
  private stopped = false;

  constructor(private readonly options: PlatformSocketOptions) {}

  start(): void {
    this.stopped = false;
    void this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.keepaliveTimer) clearInterval(this.keepaliveTimer);
    this.socket?.close();
    this.socket = null;
  }

  private async connect(): Promise<void> {
    if (this.stopped) return;

    const token = await this.options.getToken();
    if (!token) {
      this.scheduleReconnect();
      return;
    }

    const socket = new WebSocket(websocketUrl(token));
    this.socket = socket;

    socket.onopen = () => {
      this.backoffMs = INITIAL_BACKOFF_MS;
      this.options.onStatusChange?.(true);
      this.keepaliveTimer = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send("ping");
        }
      }, KEEPALIVE_INTERVAL_MS);
    };

    socket.onmessage = (message) => {
      const event = parsePlatformEvent(String(message.data));
      if (event) {
        this.options.onEvent(event);
      }
    };

    socket.onclose = () => {
      this.options.onStatusChange?.(false);
      if (this.keepaliveTimer) clearInterval(this.keepaliveTimer);
      this.scheduleReconnect();
    };

    socket.onerror = () => {
      socket.close();
    };
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    this.reconnectTimer = setTimeout(() => {
      void this.connect();
    }, this.backoffMs);
    this.backoffMs = Math.min(this.backoffMs * 2, MAX_BACKOFF_MS);
  }
}
