from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict
import contextlib

import websockets
from websockets.exceptions import ConnectionClosed

from config import WS_URL

_logger = logging.getLogger(__name__)


class _WebSocketClient:
    def __init__(self) -> None:
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connect_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._receiver_task: asyncio.Task | None = None
        self._closed = False

    async def _ensure_connection(self) -> websockets.WebSocketClientProtocol:
        if self._closed:
            raise RuntimeError("WebSocket client is closed")
        ws = self._ws
        if ws and not getattr(ws, "closed", True):
            return ws
        async with self._connect_lock:
            ws = self._ws
            if ws and not getattr(ws, "closed", True):
                return ws
            try:
                _logger.info("Connecting to trader WebSocket at %s", WS_URL)
                ws = await websockets.connect(WS_URL)
                self._ws = ws
                self._receiver_task = asyncio.create_task(self._receiver(ws))
                return ws
            except Exception as exc:  # pragma: no cover - network error
                _logger.exception("Failed to connect to trader WebSocket: %s", exc)
                raise

    async def _receiver(self, ws: websockets.WebSocketClientProtocol) -> None:
        try:
            async for message in ws:
                _logger.debug("Message from trader: %s", message)
        except ConnectionClosed:
            _logger.info("Trader WebSocket connection closed")
        except Exception as exc:  # pragma: no cover - defensive
            _logger.exception("Trader WebSocket receiver error: %s", exc)
        finally:
            if self._ws is ws:
                self._ws = None

    async def send_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self._closed:
            raise RuntimeError("WebSocket client is closed")
        data = json.dumps({"type": event_type, "payload": payload}, ensure_ascii=False)
        attempt = 0
        while attempt < 2:
            attempt += 1
            ws = await self._ensure_connection()
            try:
                async with self._send_lock:
                    await ws.send(data)
                _logger.debug("Sent event %s", event_type)
                return
            except ConnectionClosed:
                _logger.warning("Trader WebSocket connection lost, retrying...")
                await self._close_ws()
        raise RuntimeError("Unable to send event: trader WebSocket unavailable")

    async def _close_ws(self) -> None:
        ws = self._ws
        self._ws = None
        if ws:
            try:
                await ws.close()
            except Exception:
                pass
        if self._receiver_task:
            self._receiver_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receiver_task
            self._receiver_task = None

    async def close(self) -> None:
        self._closed = True
        await self._close_ws()


_client = _WebSocketClient()


async def send_event(event_type: str, payload: Dict[str, Any]) -> None:
    await _client.send_event(event_type, payload)


def send_event_nowait(event_type: str, payload: Dict[str, Any]) -> None:
    asyncio.create_task(_client.send_event(event_type, payload))


async def close_ws_client() -> None:
    await _client.close()
