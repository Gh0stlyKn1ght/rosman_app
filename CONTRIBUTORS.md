# Contributors

## Original Author

**[cmodi306](https://github.com/cmodi306)**
- Created ROSMAN — core architecture, FastAPI backend, PTY-based node management, frontend UI

---

## Contributors

**[gh0stlykn1ght](https://github.com/gh0stlykn1ght)**

- Docker support — `Dockerfile` and `docker-compose.yml` for zero-install quick start with ROS 2 Jazzy and bundled demo nodes
- Browse button — auto-hides in Docker environments where `zenity` is unavailable
- Security fixes — CSRF origin parsing rewrite, path traversal guard in `get_packages_list`, `OSError` handling in browse endpoint
- Bug fixes — missing return values on `/start` and `/stop` endpoints, race condition in log queue cleanup, file descriptor leak on `Popen` failure, invalid `logging.basicConfig` config, removed `--reload` from production container
- EventSource reliability — `onerror` handler with visible terminal message, `beforeunload` cleanup
- Already-running UX — 409 response handled silently in frontend instead of crashing
- Launch file support — `get_launch_files`, `start_launch`, `stop_launch` in backend; Launch Files tab in UI with full start/stop/log streaming
- Parameter editor — `get_node_params`, `set_node_param` via `ros2 param dump/set`; in-UI parameter modal with live editing on running nodes
- Code refactor — `_collect_logs` and `_start_process` extracted as shared helpers eliminating duplication between node and launch management; `_make_log_stream` factory in `main.py`
