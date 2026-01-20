import argparse
import importlib
import json
import os
from threading import Thread
from typing import Any, Dict, List

import uvicorn
from fastapi import (FastAPI, File, Form, HTTPException, UploadFile, WebSocket,
                     WebSocketDisconnect)
from starlette.responses import FileResponse

from aiwin_resource.manager import ResourceManager
from node.base import BaseNodeContext
from node.manager import NodeManager
from store.file import FileStore

app = FastAPI()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


@app.get("/")
def root():
    return {"message": "Hello from orchestrator!"}


@app.post("/file")
async def upload_file(file: UploadFile = File(...), filename: str = Form(...)):
    file_path = f"files/{filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())
    return {"filename": filename}


@app.get("/file/{file_name}")
async def get_file(file_name: str):
    file_path = f"files/{file_name}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # 回傳給自己
            await manager.send_personal_message(
                f"你送出了: {data}", websocket
            )

            # 廣播給所有人
            await manager.broadcast(
                f"[Broadcast] 有人說: {data}"
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast("⚠️ 有人離線了")


@app.post("/pipeline")
async def run_pipeline(pipeline: List[Dict[str, Any]]):
    # sample_pipeline = [
    #     {
    #         "id": "user_defined_node_#1",
    #         "name": "webcam",
    #         "version": "v1.0.0",
    #         "config": {
    #             "device_id": 0,
    #         }
    #     }
    # ]

    plugin_map = {
        "webcam": "random_id_1"
    }

    node_manager = NodeManager()

    for plugin_name, register_id in plugin_map.items():
        # try to find plugins in ./node/plugins
        base_plugin_path = f"./node/plugins/{register_id}"
        if not os.path.exists(base_plugin_path):
            raise FileNotFoundError(f"Plugin {register_id} not found")
        manifest = json.load(open(f"{base_plugin_path}/manifest.json"))
        backend_entrypoint = manifest["backend_entrypoint"]
        backend_module, backend_class = backend_entrypoint.split("#")
        # Convert file path to module path: remove .py extension and convert slashes to dots
        backend_module = backend_module.replace(".py", "")
        module_path = f"node.plugins.{register_id}.{backend_module}"
        backend_module = importlib.import_module(module_path)
        backend_class = getattr(backend_module, backend_class)
        node_manager.register(plugin_name, backend_class)

    resource_manager = ResourceManager()
    file_store = FileStore(cfg={"url": "http://localhost:8000"})
    node_context = BaseNodeContext(
        resource=resource_manager, file_store=file_store)

    def run_pipeline_thread(pipeline: List[Dict[str, Any]]):
        for node_config in pipeline:
            node_class = node_manager.get(node_config["name"])
            node_instance = node_class(node_context, node_config)
            node_instance.prepare()
            json.dump(resource_manager.serialize(),
                      open("resource_after_prepare.json", "w"), indent=4)
            node_instance.execute()
            json.dump(resource_manager.serialize(),
                      open("resource_after_execute.json", "w"), indent=4)

    Thread(target=run_pipeline_thread, args=(pipeline,)).start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", type=bool, default=True)
    args = parser.parse_args()

    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
