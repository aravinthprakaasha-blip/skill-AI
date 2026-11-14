"use client";
import { useEffect, useRef, useState } from "react";
import { getToken, wsUrl } from "./api";

export type LiveEvent = {
  type: string;
  run_id?: string;
  seq?: number;
  agent?: string;
  task?: string;
  event?: string;
  status?: string;
  duration_ms?: number;
  output?: any;
  event_chain?: string[];
  error?: string | null;
  at: number;
};

/** Subscribes to the learner's realtime agent event stream (reconnects with backoff). */
export function useLiveEvents(enabled = true, max = 80) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const retry = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let ping: ReturnType<typeof setInterval> | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const token = getToken();
      if (!token || closed) return;
      try {
        ws = new WebSocket(wsUrl(token));
      } catch {
        return;
      }
      ws.onopen = () => {
        retry.current = 0;
        setConnected(true);
        ping = setInterval(() => ws?.readyState === 1 && ws.send("ping"), 25_000);
      };
      ws.onmessage = (m) => {
        try {
          const data = JSON.parse(m.data);
          if (data.type === "pong" || data.type === "hello") return;
          setEvents((prev) => [{ ...data, at: Date.now() }, ...prev].slice(0, max));
        } catch {
          /* ignore malformed */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (ping) clearInterval(ping);
        if (!closed) timer = setTimeout(connect, Math.min(15_000, 1000 * 2 ** retry.current++));
      };
    };
    connect();
    return () => {
      closed = true;
      if (ping) clearInterval(ping);
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, [enabled, max]);

  return { events, connected };
}
