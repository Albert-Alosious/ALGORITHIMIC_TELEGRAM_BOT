"""FastAPI-based WebSocket server for the trader engine."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from input_calls import (
    OrderPayload,
    close_app,
    create_or_update_order,
    fetch_logs,
    open_app,
    show_status,
    start_app,
    stop_app,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
_logger = logging.getLogger(__name__)

app = FastAPI(title="Trader Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


async def dispatch_event(event_type: str, payload: Dict[str, Any]) -> None:
    if event_type == "app.open":
        workdir = Path(payload.get("workdir", "."))
        open_app(workdir)
    elif event_type == "app.start.command":
        workdir = Path(payload.get("workdir", "."))
        raw_cmd = payload.get("cmd") or []
        if isinstance(raw_cmd, str):
            cmd = [raw_cmd]
        elif isinstance(raw_cmd, (list, tuple)):
            cmd = [str(part) for part in raw_cmd]
        else:
            cmd = [str(raw_cmd)]
        start_app(workdir, cmd)
    elif event_type == "app.stop.command":
        stop_app()
    elif event_type == "app.close.command":
        close_app(bool(payload.get("force", True)))
    elif event_type == "app.status.command":
        show_status(bool(payload.get("running", False)), payload.get("pid"))
    elif event_type == "app.logs.command":
        fetch_logs(int(payload.get("lines", 100) or 100))
    elif event_type == "app.monitor.command":
        show_status(bool(payload.get("running", False)), payload.get("pid"))
    elif event_type == "order.saved":
        order = OrderPayload(
            symbol=str(payload.get("symbol", "")),
            company=str(payload.get("company", "")),
            quantity=int(payload.get("quantity", 0) or 0),
            min_profit_inr=float(payload.get("min_profit_inr", 0.0) or 0.0),
            max_profit_inr=float(payload.get("max_profit_inr", 0.0) or 0.0),
            exchange=str(payload.get("exchange", "NSE")),
            serial=payload.get("serial"),
            timestamp=_parse_timestamp(payload.get("timestamp")),
        )
        create_or_update_order(order)
    else:
        _logger.info("Unhandled event type: %s", event_type)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.utcnow()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _logger.info("WebSocket client connected: %s", websocket.client)
    try:
        while True:
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "invalid_json"})
                continue
            event_type = data.get("type")
            if not event_type:
                await websocket.send_json({"error": "missing_type"})
                continue
            payload = data.get("payload") or {}
            await dispatch_event(str(event_type), payload)
            await websocket.send_json({"ack": event_type})
    except WebSocketDisconnect:
        _logger.info("WebSocket client disconnected: %s", websocket.client)
    except Exception as exc:  # pragma: no cover - defensive
        _logger.exception("WebSocket error: %s", exc)
        await websocket.close()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
