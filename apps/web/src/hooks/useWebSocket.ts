/**
 * useWebSocket — Real-time WebSocket hook with auto-reconnect and heartbeat.
 * Day 15: Dashboard real-time streaming.
 *
 * Protocols: None (native WebSocket)
 * SOLID: SRP — manages WS lifecycle only; OCP — consumers handle message semantics
 * Benchmark: tests/benchmarks/bench_websocket.ts
 */
"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import type { WSMessage } from "@/lib/types";

export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

interface UseWebSocketOptions {
  /** Called on every parsed message */
  onMessage?: (msg: WSMessage) => void;
  /** Whether to connect at all */
  enabled?: boolean;
  /** Heartbeat timeout in ms — reconnect if no message for this long */
  heartbeatTimeoutMs?: number;
}

interface UseWebSocketReturn {
  lastMessage: WSMessage | null;
  connectionStatus: ConnectionStatus;
  sendMessage: (msg: Record<string, unknown>) => void;
  disconnect: () => void;
}

const WS_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_WS_URL) ||
  "ws://localhost:8110";

/** Exponential backoff delays: 1s, 2s, 4s, 8s … max 30s */
function backoffDelay(attempt: number): number {
  return Math.min(1000 * Math.pow(2, attempt), 30_000);
}

export function useWebSocket(
  dashboardId: string,
  tenantId: string,
  options: UseWebSocketOptions = {},
): UseWebSocketReturn {
  const {
    onMessage,
    enabled = true,
    heartbeatTimeoutMs = 45_000,
  } = options;

  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current);
  }, []);

  const resetHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current);
    heartbeatTimerRef.current = setTimeout(() => {
      // No message received within heartbeat window — force reconnect
      wsRef.current?.close(4001, "heartbeat timeout");
    }, heartbeatTimeoutMs);
  }, [heartbeatTimeoutMs]);

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return;
    if (!dashboardId || !tenantId) return;

    const url = `${WS_BASE}/ws/dashboards/${encodeURIComponent(dashboardId)}?tenant_id=${encodeURIComponent(tenantId)}`;

    setConnectionStatus("connecting");

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      attemptRef.current = 0;
      setConnectionStatus("connected");
      resetHeartbeat();
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      if (!mountedRef.current) return;
      resetHeartbeat();
      try {
        const msg = JSON.parse(event.data) as WSMessage;
        setLastMessage(msg);
        onMessage?.(msg);
      } catch {
        // ignore unparseable frames
      }
    };

    ws.onclose = (event) => {
      if (!mountedRef.current) return;
      clearTimers();
      setConnectionStatus(
        event.wasClean && event.code !== 4001 ? "disconnected" : "error",
      );

      // Schedule reconnect unless cleanly closed by the component
      if (enabled && event.code !== 1000) {
        const delay = backoffDelay(attemptRef.current);
        attemptRef.current += 1;
        reconnectTimerRef.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      if (!mountedRef.current) return;
      setConnectionStatus("error");
    };
  }, [dashboardId, tenantId, enabled, onMessage, clearTimers, resetHeartbeat]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled && dashboardId && tenantId) connect();

    return () => {
      mountedRef.current = false;
      clearTimers();
      const ws = wsRef.current;
      if (ws) {
        ws.onclose = null; // prevent reconnect loop on unmount
        ws.close(1000, "component unmounted");
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardId, tenantId, enabled]);

  const sendMessage = useCallback((msg: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    }
  }, []);

  const disconnect = useCallback(() => {
    clearTimers();
    const ws = wsRef.current;
    if (ws) {
      ws.onclose = null;
      ws.close(1000, "user disconnect");
    }
    setConnectionStatus("disconnected");
  }, [clearTimers]);

  return { lastMessage, connectionStatus, sendMessage, disconnect };
}
