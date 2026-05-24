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
     format="{asctime} - {levelname} - {message}",
     style="{",
     datefmt="%Y-%m-%d %H:%M",
 )

RUNNING_NODES   = {}
NODE_LOGS       = {}
NODE_LOG_QUEUES = {}

RUNNING_LAUNCHES   = {}
LAUNCH_LOGS        = {}
LAUNCH_LOG_QUEUES  = {}

SETUP_PATH = None


def _collect_logs(key, master_fd, loop, log_store, queue_store):
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
            log_store[key].append(text)
            for q in list(queue_store.get(key, [])):
                loop.call_soon_threadsafe(q.put_nowait, text)


def source_ws(setup_path):
    global SETUP_PATH
    try:
        minimal_env = {k: os.environ[k] for k in ("HOME", "USER", "PATH") if k in os.environ}
        result = subprocess.run(
            ["bash", "--norc", "--noprofile", "-c",
             f"source {shlex.quote(setup_path)} && env"],
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


def _is_under_install(prefix, install_dir):
    """Check prefix is under install_dir, guarding against partial-name matches."""
    return (os.path.normpath(prefix) + os.sep).startswith(install_dir)


def get_packages_list(setup_path):
    install_dir = os.path.normpath(os.path.dirname(os.path.abspath(setup_path))) + os.sep
    packages_node_dict = {}
    for package, prefix in get_packages_with_prefixes().items():
        if not _is_under_install(prefix, install_dir):
            continue
        executables = [os.path.basename(e) for e in get_executable_paths(package_name=package)]
        if executables:
            packages_node_dict[package] = executables
    return packages_node_dict


def get_launch_files(setup_path):
    """Return {package: [launch_file, ...]} for all packages under the workspace."""
    install_dir = os.path.normpath(os.path.dirname(os.path.abspath(setup_path))) + os.sep
    result = {}
    for package, prefix in get_packages_with_prefixes().items():
        if not _is_under_install(prefix, install_dir):
            continue
        launch_dir = os.path.join(prefix, "share", package, "launch")
        if not os.path.isdir(launch_dir):
            continue
        files = sorted(
            f for f in os.listdir(launch_dir)
            if f.endswith((".launch.py", ".launch.xml", ".launch.yaml"))
        )
        if files:
            result[package] = files
    return result


def _start_process(cmd, key, log_store, queue_store, running_store):
    """Shared PTY process launcher used by both start_node and start_launch."""
    master_fd, slave_fd = pty.openpty()
    try:
        process = subprocess.Popen(
            cmd,
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            preexec_fn=os.setsid,
            close_fds=True
        )
    except Exception as e:
        os.close(slave_fd)
        os.close(master_fd)
        logging.error("Failed to start process %s: %s", key, e)
        return "error"
    os.close(slave_fd)
    log_store[key] = deque(maxlen=500)
    loop = asyncio.get_running_loop()
    threading.Thread(
        target=_collect_logs,
        args=(key, master_fd, loop, log_store, queue_store),
        daemon=True
    ).start()
    running_store[key] = (process, master_fd)
    logging.info("Started: %s", key)
    return "ok"


def start_node(package_name: str, node_name: str):
    node_key = f"{package_name}/{node_name}"
    if SETUP_PATH is None:
        return "not_sourced"
    if node_key in RUNNING_NODES:
        return "already_running"
    cmd = ["bash", "--norc", "--noprofile", "-c",
           f"source {shlex.quote(SETUP_PATH)} && "
           f"ros2 run {shlex.quote(package_name)} {shlex.quote(node_name)}"]
    return _start_process(cmd, node_key, NODE_LOGS, NODE_LOG_QUEUES, RUNNING_NODES)


def stop_node(package_name: str, node_name: str):
    _stop_process(f"{package_name}/{node_name}", RUNNING_NODES)


def start_launch(package_name: str, launch_file: str):
    launch_key = f"{package_name}/{launch_file}"
    if SETUP_PATH is None:
        return "not_sourced"
    if launch_key in RUNNING_LAUNCHES:
        return "already_running"
    cmd = ["bash", "--norc", "--noprofile", "-c",
           f"source {shlex.quote(SETUP_PATH)} && "
           f"ros2 launch {shlex.quote(package_name)} {shlex.quote(launch_file)}"]
    return _start_process(cmd, launch_key, LAUNCH_LOGS, LAUNCH_LOG_QUEUES, RUNNING_LAUNCHES)


def stop_launch(package_name: str, launch_file: str):
    _stop_process(f"{package_name}/{launch_file}", RUNNING_LAUNCHES)


def _stop_process(key, running_store):
    entry = running_store.pop(key, None)
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
    logging.info("Stopped: %s", key)


def get_node_params(node_name: str):
    """Fetch all parameters for a running node. Returns dict or None on failure."""
    if SETUP_PATH is None:
        return None
    try:
        import yaml
        result = subprocess.run(
            ["ros2", "param", "dump", f"/{node_name}"],
            capture_output=True, text=True, env=os.environ, timeout=8
        )
        if result.returncode != 0:
            return None
        data = yaml.safe_load(result.stdout)
        if not isinstance(data, dict):
            return {}
        # ros2 param dump output: {'/node_name': {'ros__parameters': {...}}}
        for val in data.values():
            if isinstance(val, dict) and "ros__parameters" in val:
                return val["ros__parameters"]
        return {}
    except Exception as e:
        logging.error("get_node_params failed for %s: %s", node_name, e)
        return None


def set_node_param(node_name: str, param: str, value: str):
    """Set a single parameter on a running node. Returns True on success."""
    if SETUP_PATH is None:
        return False
    try:
        result = subprocess.run(
            ["ros2", "param", "set", f"/{node_name}", param, value],
            capture_output=True, text=True, env=os.environ, timeout=8
        )
        return result.returncode == 0
    except Exception as e:
        logging.error("set_node_param failed for %s %s=%s: %s", node_name, param, value, e)
        return False
