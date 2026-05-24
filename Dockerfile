FROM ros:jazzy-ros-base

RUN apt-get update && apt-get install -y \
    python3-pip \
    ros-jazzy-demo-nodes-py \
    ros-jazzy-demo-nodes-cpp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --break-system-packages fastapi "uvicorn[standard]"

COPY . .

SHELL ["/bin/bash", "-c"]
CMD source /opt/ros/jazzy/setup.bash && uvicorn main:app --host 0.0.0.0 --port 8000
