#!/usr/bin/env python3
"""Local browser-to-HC-05 bridge for ROBO CTRL.

Run: python3 bridge.py --port /dev/rfcomm0
Open: http://127.0.0.1:8080
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web, WSMsgType
import serial
from serial import SerialException

BASE_DIR = Path(__file__).resolve().parent
LOG = logging.getLogger("robo_ctrl")

class RobotBridge:
    def __init__(self, port: str, baud: int):
        self.port = port
        self.baud = baud
        self.ser = None
        self.clients = set()
        self.serial_lock = asyncio.Lock()
        self.reader_task = None

    async def broadcast(self, payload):
        dead = []
        message = json.dumps(payload)
        for ws in list(self.clients):
            try:
                await ws.send_str(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def connect_serial(self):
        if self.ser and self.ser.is_open:
            return True
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.15, write_timeout=1)
            # Opening a serial port may toggle DTR on some adapters. Clear stale startup output.
            await asyncio.sleep(1.5)
            self.ser.reset_input_buffer()
            LOG.info("Serial connected: %s at %s baud", self.port, self.baud)
            await self.broadcast({"type": "status", "connected": True,
                                  "message": f"Bluetooth serial connected: {self.port}"})
            return True
        except (SerialException, OSError) as exc:
            self.ser = None
            LOG.warning("Serial connection failed: %s", exc)
            await self.broadcast({"type": "status", "connected": False,
                                  "message": f"Serial unavailable ({self.port}): {exc}"})
            return False

    async def serial_reader(self, app):
        while True:
            try:
                if not self.ser or not self.ser.is_open:
                    await self.connect_serial()
                    await asyncio.sleep(1.5)
                    continue
                line = await asyncio.to_thread(self.ser.readline)
                if line:
                    text = line.decode("utf-8", errors="replace").strip()
                    if text:
                        await self.broadcast({"type": "serial", "line": text})
            except asyncio.CancelledError:
                raise
            except (SerialException, OSError) as exc:
                LOG.warning("Serial read failed: %s", exc)
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:
                    pass
                self.ser = None
                await self.broadcast({"type": "status", "connected": False,
                                      "message": f"Bluetooth serial lost: {exc}"})
                await asyncio.sleep(1)

    async def send_command(self, command: str):
        if command not in {"U", "D", "L", "R", "S", "X"}:
            raise ValueError("Unsupported command")
        async with self.serial_lock:
            if not self.ser or not self.ser.is_open:
                if not await self.connect_serial():
                    raise ConnectionError(f"Cannot open {self.port}. Check Bluetooth pairing and RFCOMM.")
            try:
                self.ser.write(command.encode("ascii"))
                self.ser.flush()
            except (SerialException, OSError) as exc:
                raise ConnectionError(f"Bluetooth write failed: {exc}") from exc

    async def websocket(self, request):
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=1024)
        await ws.prepare(request)
        self.clients.add(ws)
        await ws.send_json({"type": "status", "connected": bool(self.ser and self.ser.is_open),
                            "message": "Bluetooth serial ready" if self.ser and self.ser.is_open else "Bridge open; waiting for Bluetooth serial"})
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        payload = json.loads(msg.data)
                        if payload.get("type") != "command":
                            continue
                        command = str(payload.get("command", "")).upper()
                        await self.send_command(command)
                    except (ValueError, ConnectionError, json.JSONDecodeError) as exc:
                        await ws.send_json({"type": "error", "message": str(exc)})
                    except Exception as exc:
                        LOG.exception("WebSocket command failed")
                        await ws.send_json({"type": "error", "message": f"Unexpected bridge error: {exc}"})
                elif msg.type == WSMsgType.ERROR:
                    LOG.warning("WebSocket error: %s", ws.exception())
        finally:
            self.clients.discard(ws)
            # Fail-safe: ask the robot to stop when a browser client disconnects.
            try:
                await self.send_command("S")
            except Exception:
                pass
        return ws

async def index(request):
    return web.FileResponse(BASE_DIR / "index.html")

async def on_startup(app):
    bridge: RobotBridge = app["bridge"]
    app["reader_task"] = asyncio.create_task(bridge.serial_reader(app))

async def on_cleanup(app):
    task = app.get("reader_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    bridge: RobotBridge = app["bridge"]
    try:
        if bridge.ser and bridge.ser.is_open:
            bridge.ser.write(b"S")
            bridge.ser.close()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="ROBO CTRL local Bluetooth bridge")
    parser.add_argument("--port", default="/dev/rfcomm0", help="Serial port (default: /dev/rfcomm0)")
    parser.add_argument("--baud", type=int, default=9600, help="HC-05 baud rate (default: 9600)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host; keep localhost for safety")
    parser.add_argument("--http-port", type=int, default=8080, help="Web UI port (default: 8080)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bridge = RobotBridge(args.port, args.baud)
    app = web.Application()
    app["bridge"] = bridge
    app.router.add_get("/", index)
    app.router.add_get("/ws", bridge.websocket)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    print(f"\nROBO CTRL is starting. Open http://127.0.0.1:{args.http_port}")
    print(f"Serial port: {args.port} @ {args.baud} baud")
    print("Keep this terminal open while controlling the robot. Press Ctrl+C to stop.\n")
    web.run_app(app, host=args.host, port=args.http_port)

if __name__ == "__main__":
    main()
