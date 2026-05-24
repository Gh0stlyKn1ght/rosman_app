from ros2pkg.api import get_executable_paths
from ament_index_python.packages import get_packages_with_prefixes

import asyncio
import logging
import os
import pty
import shlex
import signal
import subprocess
import threading
from collections import deque

logging.basicConfig(
     encoding="utf-8",
     filemode="a",
     format="{asctime} - {levelname} - {message}",
     style="{",
     datefmt="%Y-%m-%d %H:%M",
 )

RUNNING_NODES = {}
NODE_LOGS = {}
NODE_LOG_QUEUES = {}
SETUP_PATH = None


def _collect_logs(node_key, master_fd, loop):
    buf = b""
    while True:
        try:
            data = os.read(master_fd, 4096)
            if not data:
                break
        except OSError:
            break
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace").rstrip("\r")
            NODE_LOGS[node_key].append(text)
            for q in list(NODE_LOG_QUEUES.get(node_key, [])):
                loop.call_soon_threadsafe(q.put_nowait, text)

def source_ws(setup_path):
    global SETUP_PATH
    try:
        minimal_env = {k: os.environ[k] for k in ("HOME", "USER", "PATH") if k in os.environ}
        result = subprocess.run(
            ["bash", "--norc", "--noprofile", "-c", f"source {shlex.quote(setup_path)} && env"],
            capture_output=True, text=True,
            env=minimal_env
        )
        if result.returncode != 0:
            return False
        for line in result.stdout.splitlines():
            key, _, value = line.partition("=")
            if key:
                os.environ[key] = value
        SETUP_PATH = setup_path
        return True
    except Exception as e:
        logging.error("Cannot source the bash file: %s", e)
        return False
    
def get_packages_list(setup_path):
    install_dir = os.path.normpath(os.path.dirname(os.path.abspath(setup_path)))
    packages_node_dict = {}
    for package, prefix in get_packages_with_prefixes().items():
        if not os.path.normpath(prefix).startswith(install_dir):
            continue
        executables = [os.path.basename(e) for e in get_executable_paths(package_name=package)]
        if executables:
            packages_node_dict[package] = executables
    return packages_node_dict
    
def start_node(package_name: str, node_name: str):
    node_key = f"{package_name}/{node_name}"
    if SETUP_PATH is None:
        return "not_sourced"
    if node_key in RUNNING_NODES:
        return "already_running"
    cmd = ["bash", "--norc", "--noprofile", "-c",
           f"source {shlex.quote(SETUP_PATH)} && ros2 run {shlex.quote(package_name)} {shlex.quote(node_name)}"]
    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(
        cmd,
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        preexec_fn=os.setsid,
        close_fds=True
    )
    os.close(slave_fd)
    NODE_LOGS[node_key] = deque(maxlen=200)
    loop = asyncio.get_running_loop()
    threading.Thread(target=_collect_logs, args=(node_key, master_fd, loop), daemon=True).start()
    RUNNING_NODES[node_key] = (process, master_fd)
    logging.info("Started node: %s", node_key)

def stop_node(package_name: str, node_name: str):
    node_key = f"{package_name}/{node_name}"
    entry = RUNNING_NODES.pop(node_key, None)
    if entry is None:
        return
    process, master_fd = entry
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        os.close(master_fd)
    except OSError:
        pass
    logging.info("Stopped node: %s", node_key)