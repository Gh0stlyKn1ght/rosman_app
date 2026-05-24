from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ros_manager import (
    RUNNING_NODES,
    NODE_LOGS,
    NODE_LOG_QUEUES,
    source_ws,
    get_packages_list,
    start_node,
    stop_node,
)

import asyncio
import os
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

_SAFE_ORIGINS = {"http://localhost", "http://127.0.0.1"}
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _MUTATING_METHODS:
            origin = request.headers.get("origin", "")
            # strip port before checking host
            host_only = origin.rsplit(":", 1)[0] if ":" in origin[7:] else origin
            if origin and host_only not in _SAFE_ORIGINS:
                return Response("Cross-origin requests not allowed", status_code=403)
        return await call_next(request)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for node_key in list(RUNNING_NODES.keys()):
        pkg, node = node_key.split("/", 1)
        stop_node(pkg, node)

app = FastAPI(lifespan=lifespan)
app.add_middleware(CSRFMiddleware)

@app.get("/browse")
async def browse_file():
    try:
        result = subprocess.run(
            ["zenity", "--file-selection", "--title=Select ROS Setup File"],
            capture_output=True, text=True
        )
        return {"path": result.stdout.strip()}
    except FileNotFoundError:
        return {"path": "", "error": "unavailable"}

@app.post("/source")
async def source_and_get_packages(setup_path:str):
    try:
        ok = source_ws(setup_path)
        if not ok:
            return {"error": True, "packages": {}}
        return {"error": False, "packages": get_packages_list(setup_path)}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to source workspace")

@app.post("/start")
async def start(package_name: str, node_name: str):
    result = start_node(package_name, node_name)
    if result == "not_sourced":
        raise HTTPException(status_code=400, detail="Workspace not sourced")

@app.post("/stop")
async def stop(package_name:str, node_name:str):
    stop_node(package_name, node_name)

@app.get("/logs/stream")
async def stream_logs(package_name: str, node_name: str):
    node_key = f"{package_name}/{node_name}"
    q = asyncio.Queue()
    NODE_LOG_QUEUES.setdefault(node_key, []).append(q)

    async def event_gen():
        try:
            for line in list(NODE_LOGS.get(node_key, [])):
                yield f"data: {line}\n\n"
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {line}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            NODE_LOG_QUEUES.get(node_key, []).remove(q)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/status")
async def status():
    return {"running": list(RUNNING_NODES.keys())}

@app.get("/")
async def root():
    return FileResponse(os.path.join(PROJECT_ROOT, "templates", "index.html"))