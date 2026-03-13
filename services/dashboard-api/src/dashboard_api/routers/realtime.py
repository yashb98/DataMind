"""
Dashboard Realtime Router — WebSocket endpoint with Kafka consumer for live dashboard updates.
Day 15: Phase 3 — Real-time dashboard streaming via aiokafka + WebSocket.

Protocols: None
SOLID: SRP (realtime only), OCP (heartbeat/consumer logic extensible)
Benchmark: SLO < 1s refresh latency from Kafka event to client
"""

from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from aiokafka import AIOKafkaConsumer

from dashboard_api.config import settings
from dashboard_api.models import WebSocketMessage

router = APIRouter(tags=["Realtime"])
log = structlog.get_logger(__name__)


@router.websocket("/ws/dashboards/{dashboard_id}")
async def dashboard_websocket(
    websocket: WebSocket,
    dashboard_id: str,
    tenant_id: str,
) -> None:
    """WebSocket endpoint for real-time dashboard data streaming.

    On connect:
      1. Accepts the WebSocket connection.
      2. Sends initial snapshot message.
      3. Starts Kafka consumer on agent.events topic.
      4. Forwards events matching (dashboard_id, tenant_id) to the client.
      5. Sends heartbeat every 30s.
      6. Cleans up Kafka consumer on disconnect.

    Args:
        websocket: FastAPI WebSocket connection.
        dashboard_id: Dashboard UUID to stream events for.
        tenant_id: Tenant identifier used for event filtering.
    """
    await websocket.accept()
    log.info(
        "ws.dashboard.connected",
        dashboard_id=dashboard_id,
        tenant_id=tenant_id,
    )

    # Send initial snapshot
    snapshot = WebSocketMessage(
        type="snapshot",
        dashboard_id=dashboard_id,
        data={"message": "Connected to real-time dashboard stream"},
    )
    await websocket.send_text(snapshot.model_dump_json())

    # Unique group_id per connection to get all events independently
    group_id = f"{settings.kafka_group_id}-{dashboard_id[:8]}"
    consumer = AIOKafkaConsumer(
        settings.kafka_topic_agent_events,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8", errors="replace")),
        auto_offset_reset="latest",
    )

    heartbeat_task: asyncio.Task[None] | None = None
    try:
        await consumer.start()
        heartbeat_task = asyncio.create_task(
            _heartbeat(websocket, dashboard_id), name=f"hb-{dashboard_id[:8]}"
        )

        async for msg in consumer:
            payload: dict = msg.value if isinstance(msg.value, dict) else {}
            # Filter: only forward events for this dashboard + tenant
            if (
                payload.get("tenant_id") == tenant_id
                and payload.get("dashboard_id", dashboard_id) == dashboard_id
            ):
                event = WebSocketMessage(
                    type="event",
                    dashboard_id=dashboard_id,
                    data=payload,
                )
                try:
                    await websocket.send_text(event.model_dump_json())
                except WebSocketDisconnect:
                    log.info(
                        "ws.dashboard.disconnected_mid_send",
                        dashboard_id=dashboard_id,
                    )
                    break
    except WebSocketDisconnect:
        log.info("ws.dashboard.disconnected", dashboard_id=dashboard_id)
    except Exception as exc:
        log.error("ws.dashboard.error", dashboard_id=dashboard_id, error=str(exc))
        try:
            error_msg = WebSocketMessage(
                type="error",
                dashboard_id=dashboard_id,
                data={"error": str(exc), "code": "WS_ERROR"},
            )
            await websocket.send_text(error_msg.model_dump_json())
        except Exception:
            pass  # Client already disconnected
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        try:
            await consumer.stop()
        except Exception as stop_exc:
            log.warning("ws.dashboard.consumer_stop_error", error=str(stop_exc))
        log.info("ws.dashboard.cleaned_up", dashboard_id=dashboard_id)


async def _heartbeat(websocket: WebSocket, dashboard_id: str) -> None:
    """Send a heartbeat message every 30 seconds to keep the connection alive.

    Args:
        websocket: Active WebSocket connection.
        dashboard_id: Dashboard UUID for the heartbeat message.
    """
    while True:
        await asyncio.sleep(30)
        try:
            hb = WebSocketMessage(type="heartbeat", dashboard_id=dashboard_id)
            await websocket.send_text(hb.model_dump_json())
        except Exception:
            # Connection closed — stop heartbeats
            break
