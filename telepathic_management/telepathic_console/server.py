"""Serve the Web Teleops Console interface and proxy its browser WebSocket to local rosbridge."""
from __future__ import annotations

import asyncio
import hmac
import json
import re
import os
import socket
import time
import uuid
from pathlib import Path

import uvicorn
import websockets
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from cryptic_signal_core.telepathic_encoding import encode_text


def _interface_dir() -> Path:
    """Resolve the source checkout or the installed ROS package interface."""
    configured = os.getenv("AGI_WEB_TELEOPS_CONSOLE_INTERFACE_DIR")
    if configured:
        return Path(configured)
    try:
        from ament_index_python.packages import get_package_share_directory
        installed = Path(get_package_share_directory("telepathic_management")) / "telepathic_console"
        if (installed / "frontend" / "index.html").is_file():
            return installed
    except (ImportError, LookupError):
        pass
    return Path(__file__).resolve().parent


INTERFACE_DIR = _interface_dir()
FRONTEND_DIR = INTERFACE_DIR / "frontend"
app = FastAPI(title="AGi Web Teleops Console", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=INTERFACE_DIR / "backend" / "static"), name="static")
_aiva_last_seen: float | None = None


@app.get("/api/settings")
async def get_settings() -> dict:
    return {"settings": [], "runtime": [
                {"name": "ROS bridge", "value": os.getenv("AGI_ROSBRIDGE_URL", "ws://127.0.0.1:9090"), "source": "Environment"},
                {"name": "Signal scheme", "value": os.getenv("AGI_TELEPATHIC_SCHEME", "ternary_utf8_v1"), "source": "Environment"},
            ], "path": "",
            "apply_note": "Grace runtime configuration belongs to Shell.",
            "read_only_note": "This console does not edit AuRoRA or Grace runtime settings."}


@app.put("/api/settings")
async def put_settings(request: Request) -> dict:
    raise HTTPException(status_code=409, detail="Configure Grace through Shell, not the console")


@app.post("/api/presence/aiva", status_code=204)
async def aiva_presence() -> None:
    """Refresh AIVA's heartbeat; tailnet ACLs restrict callers to trusted devices."""
    global _aiva_last_seen
    _aiva_last_seen = time.monotonic()


@app.get("/api/presence")
async def presence() -> dict[str, bool | int | None]:
    """Report AIVA presence, using local deployment identity or a remote heartbeat."""
    timeout_s = max(5, int(os.getenv("AGI_AIVA_PRESENCE_TIMEOUT", "12")))
    age = None if _aiva_last_seen is None else time.monotonic() - _aiva_last_seen
    local_aiva = os.getenv("AGI_WEB_TELEOPS_CONSOLE_AIVA_LOCAL")
    if local_aiva is None:
        local_aiva = "false"
    aiva_host = local_aiva.strip().lower() in {"1", "true", "yes", "on"}
    aiva_online = aiva_host or (age is not None and age <= timeout_s)
    # External consoles can run on any host; do not infer robot presence.
    aurora_online = os.getenv("AGI_WEB_TELEOPS_CONSOLE_AURORA_LOCAL", "false").lower() in {"1", "true", "yes", "on"}
    return {
        "aiva_online": aiva_online,
        "aurora_online": aurora_online,
        "aiva_last_seen_seconds_ago": None if age is None else int(age),
        "timeout_seconds": timeout_s,
    }


def _encode_stimulus(text: str, identifier: str) -> dict:
    """Build the common wire contract for chat and Canvas request producers."""
    scheme = os.getenv("AGI_TELEPATHIC_SCHEME", "ternary_utf8_v1")
    if scheme != "ternary_utf8_v1":
        raise ValueError(f"Unsupported signal scheme: {scheme}")
    signal, pulse = encode_text(text)
    return {"source": os.getenv("AGI_SOURCE_ID", socket.gethostname()),
            "signal": list(signal), "pulse": pulse,
            "channel": os.getenv("AGI_TELEPATHIC_CHANNEL", "grace"),
            "scheme": scheme, "identifier": identifier}


@app.post("/api/telepathic/send")
async def send_telepathic_input(request: Request) -> dict[str, str]:
    """Encode text and publish a typed TelepathicSignal through rosbridge."""
    raw_text = await request.body()
    if len(raw_text) > 2_500_000:
        raise HTTPException(status_code=413, detail="Encoded request input exceeds 2500000 bytes")
    try:
        text = raw_text.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=400, detail="Input must be UTF-8 text") from error
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text input is empty")

    if request.query_params.get("web_search", "false").lower() in {"1", "true", "yes"}:
        text = f"/web {text}"
    identifier = uuid.uuid4().hex
    try:
        msg = await asyncio.to_thread(_encode_stimulus, text, identifier)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    target = os.getenv("AGI_ROSBRIDGE_URL", "ws://127.0.0.1:9090")
    envelope = {"op": "publish", "topic": "/telepathic/stimulus", "msg": msg}
    try:
        async with websockets.connect(target, open_timeout=3) as rosbridge:
            await rosbridge.send(json.dumps({"op": "advertise", "topic": envelope["topic"], "type": "cryptic_signal_core/msg/TelepathicSignal"}))
            await rosbridge.send(json.dumps(envelope))
    except (websockets.WebSocketException, OSError, TimeoutError) as error:
        raise HTTPException(status_code=502, detail="Could not publish to ROS rosbridge") from error
    return {"identifier": identifier, "topic": envelope["topic"]}


@app.get("/canvas")
async def canvas_page():
    return FileResponse(FRONTEND_DIR / "canvas.html")


@app.get("/api/canvas/config.js")
async def canvas_config_script() -> Response:
    settings = {
        "assistantName": os.getenv("AGI_CANVAS_ASSISTANT_NAME", "Grace"),
        "backUrl": "/",
        "apiKeyRequired": bool(os.getenv("AGI_CANVAS_API_KEY")),
        "features": {
            "reference": os.getenv("AGI_CANVAS_REFERENCE_MODE", "1") == "1",
            "image": os.getenv("AGI_CANVAS_IMAGE_MODE", "1") == "1",
            "feedback": os.getenv("AGI_CANVAS_FEEDBACK", "1") == "1",
        },
    }
    return Response("window.CANVAS_STUDIO_CONFIG=" + json.dumps(settings, separators=(",", ":")) + ";",
                    media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.websocket("/api/canvas/ws")
async def canvas_api(browser: WebSocket) -> None:
    """WebSocket drawing API; relay requests/events through ROS for monitoring."""
    await browser.accept()
    identifier = ""
    api_key = os.getenv("AGI_CANVAS_API_KEY", "")
    input_topic = os.getenv("AGI_CANVAS_INPUT_TOPIC", "/telepathic/stimulus")
    response_topic = os.getenv("AGI_CANVAS_RESPONSE_TOPIC", "/telepathic/response")
    snapshot_topic = os.getenv("AGI_CANVAS_SNAPSHOT_TOPIC", "/aiva/canvas_snapshot")

    async def send_error(message: str) -> None:
        try:
            await browser.send_json({"type": "canvas_error", "identifier": identifier, "content": message})
        except (RuntimeError, WebSocketDisconnect):
            pass

    try:
        if api_key:
            try:
                auth = await browser.receive_json()
            except (WebSocketDisconnect, ValueError):
                return
            if not isinstance(auth, dict) or auth.get("type") != "auth" or not isinstance(auth.get("token"), str) \
                    or not hmac.compare_digest(auth["token"], api_key):
                await send_error("Canvas API key is missing or invalid.")
                await browser.close(code=4401, reason="API key required")
                return
        try:
            packet = await browser.receive_json()
        except (WebSocketDisconnect, ValueError):
            return
        if not isinstance(packet, dict) or packet.get("type") != "request" or not isinstance(packet.get("payload"), dict):
            await send_error("Expected a canvas request payload.")
            await browser.close(code=4400, reason="Invalid request")
            return
        payload = packet["payload"]
        identifier = payload.get("identifier", "")
        if not isinstance(identifier, str) or not identifier or len(identifier) > 64:
            await send_error("Canvas request needs an identifier of at most 64 characters.")
            await browser.close(code=4400, reason="Invalid identifier")
            return
        if len(json.dumps(payload, separators=(",", ":"))) > 12_000_000:
            await send_error("Canvas request exceeds the 12 MB limit.")
            await browser.close(code=4400, reason="Request too large")
            return

        target = os.getenv("AGI_ROSBRIDGE_URL", "ws://127.0.0.1:9090")
        async with websockets.connect(target, open_timeout=5, max_size=None) as ros:
            await ros.send(json.dumps({"op": "subscribe", "topic": response_topic,
                                       "type": "std_msgs/String", "queue_length": 100}))
            await ros.send(json.dumps({"op": "advertise", "topic": input_topic, "type": "cryptic_signal_core/msg/TelepathicSignal"}))
            if snapshot_topic != input_topic:
                await ros.send(json.dumps({"op": "advertise", "topic": snapshot_topic, "type": "std_msgs/String"}))

            async def publish(topic: str, body: dict) -> None:
                text = json.dumps(body, separators=(",", ":"))
                if topic == input_topic:
                    msg = await asyncio.to_thread(_encode_stimulus, text, identifier)
                else:
                    msg = {"data": text}
                await ros.send(json.dumps({"op": "publish", "topic": topic, "msg": msg}))

            await publish(input_topic, payload)

            async def browser_to_ros() -> None:
                while True:
                    message = await browser.receive_json()
                    if not isinstance(message, dict) or message.get("identifier") != identifier:
                        continue
                    kind = message.get("type")
                    if kind == "snapshot" and isinstance(message.get("image"), str):
                        await publish(snapshot_topic, {"identifier": identifier, "image": message["image"]})
                    elif kind == "feedback" and message.get("rating") in ("keep", "improve"):
                        await publish(input_topic, {"canvas_feedback": {
                            "identifier": identifier, "rating": message["rating"],
                            "notes": str(message.get("notes", ""))[:1000],
                        }})

            async def ros_to_browser() -> None:
                async for raw in ros:
                    try:
                        envelope = json.loads(raw)
                        if envelope.get("op") != "publish" or envelope.get("topic") != response_topic:
                            continue
                        event = json.loads(envelope.get("msg", {}).get("data", "{}"))
                    except (json.JSONDecodeError, AttributeError, TypeError):
                        continue
                    if not isinstance(event, dict) or event.get("identifier") != identifier:
                        continue
                    await browser.send_json(event)

            tasks = [asyncio.create_task(browser_to_ros()), asyncio.create_task(ros_to_browser())]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except (websockets.WebSocketException, OSError, TimeoutError, RuntimeError, ValueError, WebSocketDisconnect) as error:
        await send_error(f"Canvas API could not reach its drawing service: {error}")
    finally:
        try:
            await browser.close()
        except RuntimeError:
            pass


def _tail_lines(path: Path, limit: int) -> list[bytes]:
    chunks = []
    newlines = 0
    with path.open("rb") as log:
        remaining = log.seek(0, os.SEEK_END)
        while remaining and newlines <= limit:
            size = min(8192, remaining)
            remaining -= size
            log.seek(remaining)
            chunk = log.read(size)
            chunks.append(chunk)
            newlines += chunk.count(b"\n")
    return b"".join(reversed(chunks)).splitlines()[-limit:]


@app.get("/api/logs")
def get_logs(limit: int = 200, level: str = "ALL") -> dict:
    """Return recent persistent ROS logs for the local WebUI log viewer."""
    log_dir = Path(os.getenv("AGI_LOG_DIR", str(Path(os.getenv("AGI_HOME", "~/.agi")).expanduser() / "log"))).expanduser()
    if not re.fullmatch(r"ALL|DEBUG|INFO|WARN|ERROR|FATAL", level):
        raise HTTPException(status_code=400, detail="Invalid log level")
    limit = max(1, min(limit, 1000))
    entries = []
    for path in (log_dir / "application.jsonl", log_dir / "errors.jsonl"):
        try:
            lines = _tail_lines(path, limit)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise HTTPException(status_code=500, detail=f"Cannot read logs: {error}") from error
        for line in lines:
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(event, dict):
                continue
            if level == "ALL" or event.get("level") == level:
                entries.append(event)
    entries.sort(key=lambda event: event.get("timestamp", ""))
    return {"entries": entries[-limit:], "path": str(log_dir)}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/settings")
async def settings_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "settings.html")


@app.get("/logs")
async def logs_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "logs.html")


@app.websocket("/rosbridge")
async def rosbridge_proxy(browser: WebSocket) -> None:
    """Keep rosbridge on loopback; the browser connects through this origin."""
    await browser.accept()
    target = os.getenv("AGI_ROSBRIDGE_URL", "ws://127.0.0.1:9090")
    try:
        async with websockets.connect(target, max_size=None) as ros:
            async def browser_to_ros() -> None:
                while True:
                    message = await browser.receive_text()
                    await ros.send(message)

            async def ros_to_browser() -> None:
                async for message in ros:
                    if isinstance(message, bytes):
                        await browser.send_bytes(message)
                    else:
                        await browser.send_text(message)

            tasks = [asyncio.create_task(browser_to_ros()), asyncio.create_task(ros_to_browser())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    except (WebSocketDisconnect, websockets.WebSocketException, OSError, RuntimeError):
        pass
    finally:
        try:
            await browser.close()
        except RuntimeError:
            pass


def main() -> None:
    """Run loopback-only Web Teleops Console; use Tailscale Serve for tailnet access."""
    uvicorn.run(
        app,
        host=os.getenv("TELEPATHIC_CONSOLE_HOST", "127.0.0.1"),
        port=int(os.getenv("TELEPATHIC_CONSOLE_PORTAL", "8853")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
