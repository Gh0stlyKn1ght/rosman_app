from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ros_manager import (
    RUNNING_NODES, NODE_LOGS, NODE_LOG_QUEUES,
    RUNNING_LAUNCHES, LAUNCH_LOGS, LAUNCH_LOG_QUEUES,
    source_ws, get_packages_list, get_launch_files,
    start_node, stop_node,
    start_launch, stop_launch,
    get_node_params, set_node_param,
)

import asyncio
import os
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

_SAFE_ORIGINS   = {"http://localhost", "http://127.0.0.1"}
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _MUTATING_METHODS:
            origin = request.headers.get("origin", "")
            if origin:
                try:
                    scheme_end = origin.index("://") + 3
                    host_part  = origin[scheme_end:]
                    host_only  = origin[:scheme_end] + host_part.split(":")[0]
                except ValueError:
                    return Response("Cross-origin requests not allowed", status_code=403)
                if host_only not in _SAFE_ORIGINS:
                    return Response("Cross-origin requests not allowed", status_code=403)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for node_key in list(RUNNING_NODES.keys()):
        pkg, node = node_key.split("/", 1)
        stop_node(pkg, node)
    for launch_key in list(RUNNING_LAUNCHES.keys()):
        pkg, lfile = launch_key.split("/", 1)
        stop_launch(pkg, lfile)


app = FastAPI(lifespan=lifespan)
app.add_middleware(CSRFMiddleware)


# ── File browser ──────────────────────────────────────────────────────────────

@app.get("/browse")
async def browse_file():
    try:
        result = subprocess.run(
            ["zenity", "--file-selection", "--title=Select ROS Setup File"],
            capture_output=True, text=True
        )
        return {"path": result.stdout.strip()}
    except (FileNotFoundError, OSError):
        return {"path": "", "error": "unavailable"}


# ── Workspace sourcing ────────────────────────────────────────────────────────

@app.post("/source")
async def source_and_get_packages(setup_path: str):
    try:
        ok = source_ws(setup_path)
        if not ok:
            return {"error": True, "packages": {}, "launch_files": {}}
        return {
            "error": False,
            "packages":     get_packages_list(setup_path),
            "launch_files": get_launch_files(setup_path),
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to source workspace")


# ── Node management ───────────────────────────────────────────────────────────

@app.post("/start")
async def start(package_name: str, node_name: str):
    result = start_node(package_name, node_name)
    if result == "not_sourced":
        raise HTTPException(status_code=400, detail="Workspace not sourced")
    if result == "already_running":
        return JSONResponse(status_code=409, content={"detail": "Node already running"})
    if result == "error":
        raise HTTPException(status_code=500, detail="Failed to start node")
    return {"status": "started"}


@app.post("/stop")
async def stop(package_name: str, node_name: str):
    stop_node(package_name, node_name)
    return {"status": "stopped"}


@app.get("/status")
async def status():
    return {"running": list(RUNNING_NODES.keys())}


@app.get("/logs/stream")
async def stream_logs(package_name: str, node_name: str):
    return _make_log_stream(
        f"{package_name}/{node_name}", NODE_LOGS, NODE_LOG_QUEUES
    )


# ── Launch file management ────────────────────────────────────────────────────

@app.post("/launch/start")
async def launch_start(package_name: str, launch_file: str):
    result = start_launch(package_name, launch_file)
    if result == "not_sourced":
        raise HTTPException(status_code=400, detail="Workspace not sourced")
    if result == "already_running":
        return JSONResponse(status_code=409, content={"detail": "Launch already running"})
    if result == "error":
        raise HTTPException(status_code=500, detail="Failed to start launch file")
    return {"status": "started"}


@app.post("/launch/stop")
async def launch_stop(package_name: str, launch_file: str):
    stop_launch(package_name, launch_file)
    return {"status": "stopped"}


@app.get("/launch/status")
async def launch_status():
    return {"running": list(RUNNING_LAUNCHES.keys())}


@app.get("/launch/logs/stream")
async def stream_launch_logs(package_name: str, launch_file: str):
    return _make_log_stream(
        f"{package_name}/{launch_file}", LAUNCH_LOGS, LAUNCH_LOG_QUEUES
    )


# ── Parameters ────────────────────────────────────────────────────────────────

@app.get("/params")
async def get_params(node_name: str):
    params = get_node_params(node_name)
    if params is None:
        raise HTTPException(status_code=503, detail="Could not fetch parameters — is the node running?")
    return {"params": params}


@app.post("/params/set")
async def set_param(node_name: str, param: str, value: str):
    ok = set_node_param(node_name, param, value)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to set parameter")
    return {"status": "ok"}


# ── Static ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(os.path.join(PROJECT_ROOT, "templates", "index.html"))


# ── Shared log stream factory ─────────────────────────────────────────────────

def _make_log_stream(key: str, log_store: dict, queue_store: dict):
    q = asyncio.Queue()
    queue_store.setdefault(key, []).append(q)

    async def event_gen():
        try:
            for line in list(log_store.get(key, [])):
                yield f"data: {line}\n\n"
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {line}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            try:
                queue_store.get(key, []).remove(q)
            except ValueError:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
