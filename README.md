# ROS Manager (rosman)

I was working on a project on automated driving whose system was built on ROS2. Those who have worked with ROS2 know that in such complex system, there are many different nodes that need to be started at the same time, so that they exchange topics. Sure I could write a launch file a start all nodes from that single file. But I needed something more.


I wanted a browser-based UI for managing your ROS2 nodes - start, stop and stream logs without touching the terminal. And that led to me building `ROSMAN`.

ROSMAN (ROS2 Manager) is an interface that allows you to control your nodes via a UI that runs on your localhost. It uses FastAPI on the backend and a simple web frontend, with Python in the backend.

<img src="rosman_demo.gif" width="100%"/>

---

## How It Works

ROSMAN runs a local web server on your machine. You open it in your browser, you enter the absolute path of the setup file of the ROS2 workspace you are working in. That will give you a list of nodes in that workspace and lets you manage your nodes through the UI.

---

## Requirements

- ROS2 installed (any distro — Humble, Iron, Jazzy, etc.)
- Python 3.8+
- `zenity` (for the workspace file picker — usually pre-installed on Ubuntu with a desktop environment)

---

## Quick Start (Docker — no ROS2 install needed)

The Docker image ships with ROS2 Jazzy and the official demo nodes so you can try ROSMAN immediately without a robot or a local ROS2 installation.

```bash
git clone https://github.com/cmodi306/rosman_app.git
cd rosman_app
docker compose up --build
```

Open `http://localhost:8000`, enter `/opt/ros/jazzy/setup.bash` as the workspace path, and click **Source**. You'll see packages like `demo_nodes_py` and `demo_nodes_cpp` — pick a node such as `talker` and hit **Start** to see live logs streaming in the UI.

---

## Installation (local ROS2)

```bash
git clone https://github.com/cmodi306/rosman_app.git
cd rosman_app
pip install -r requirements.txt
```

---

## Usage

1. Start the server:

   ```bash
   uvicorn main:app --port 8000
   ```

2. Open your browser and go to `http://localhost:8000`

3. Enter the absolute path to your ROS2 workspace setup file (e.g. `install/setup.bash`) and click **Source**. You can also use **Browse** to pick the file via a dialog.

4. Pick a package and node, then hit **▶ Start**. Logs will stream live via the **≡ Logs** button.

5. Click **■ Stop** to kill a running node. All nodes are automatically stopped when the server shuts down.

6. Switch to the **Launch Files** tab to start/stop full `.launch.py` / `.launch.xml` files — same start, stop, and live log streaming as individual nodes.

7. Click **⚙ Params** on any running node to open the parameter editor — lists all parameters with their current values and lets you set them live without restarting the node.

---

## Future ToDOs

- [x] Launch file support
- [x] Parameter editing via UI

---

## Support

If rosman saves you some terminal headaches, consider showing some love:

- ☕ [Buy me a coffee](https://buymeacoffee.com/cmodi306)
- ✍️ [Follow me on Medium](https://medium.com/@cmodi306) for more content on tech
- [Substack](https://substack.com/@cmodi306)
- [Bluesky](https://bsky.app/profile/cmodi306.bsky.social)
- [Mastodon](https://mastodon.social/@cmodi3006)
