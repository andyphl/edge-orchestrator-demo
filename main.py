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

from aiwin_resource.creator import ResourceCreator
from aiwin_resource.instance_manager import ResourceInstanceManager
from aiwin_resource.plugins.image.v1.main import ImageResource
from aiwin_resource.plugins.number.v1.main import NumberResource
from aiwin_resource.plugins.numbers.v1.main import NumbersResource
from aiwin_resource.plugins.string.v1.main import StringResource
from aiwin_resource.plugins.unknown.v1.main import UnknownResource
from aiwin_resource.plugins.vision.input.usb_device.v1.main import UsbDeviceResource
from aiwin_resource.plugins.vision.input.usb_devices.v1.main import UsbDevicesResource
from event_emitter import EventEmitter
from node.base import BaseNode, BaseNodeContext
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


@app.delete("/file/{file_name}")
async def delete_file(file_name: str):
    file_path = f"files/{file_name}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(file_path)
    return {"message": "File deleted"}


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
        "webcam": "random_id_1",
        "binarization": "random_id_2",
        "cast_resource": "random_id_4",
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

    resource_manager = ResourceInstanceManager()

    resource_creator = ResourceCreator()
    resource_creator.register("image.v1", ImageResource)
    resource_creator.register("string.v1", StringResource)
    resource_creator.register("number.v1", NumberResource)
    resource_creator.register("numbers.v1", NumbersResource)
    resource_creator.register("unknown.v1", UnknownResource)
    resource_creator.register("vision.input.usb_device.v1", UsbDeviceResource)
    resource_creator.register(
        "vision.input.usb_devices.v1", UsbDevicesResource)

    file_store = FileStore(cfg={"url": "http://localhost:8000"})
    event_emitter = EventEmitter()
    node_context = BaseNodeContext(
        resource_manager=resource_manager,
        resource_creator=resource_creator,
        file_store=file_store,
        event=event_emitter
    )

    def run_pipeline_thread(pipeline: List[Dict[str, Any]]):
        # 初始化所有 node 並調用 prepare，同時為每個 node 配置下一個 node 的索引
        node_instances: List[BaseNode] = []
        for i, node_config in enumerate(pipeline):
            # 在 node_config 中添加下一個 node 的索引資訊
            node_config_with_next = node_config.copy()
            if i + 1 < len(pipeline):
                node_config_with_next['_next_node_index'] = i + 1
            else:
                node_config_with_next['_next_node_index'] = None

            node_class = node_manager.get(node_config["name"])
            node_instance = node_class(node_context, node_config_with_next)
            node_instance.prepare()
            node_instances.append(node_instance)

        json.dump(resource_manager.serialize(),
                  open("resource_after_prepare.json", "w"), indent=4)

        # 為每個 node 註冊事件監聽器
        def create_node_executor(node_index: int):
            def execute_node(data: Any = None):
                node_instance = node_instances[node_index]
                node_instance.execute()
                json.dump(resource_manager.serialize(),
                          open(f"resource_after_execute_node_{node_index}.json", "w"), indent=4)
                node_instance.next()

            return execute_node

        # 為每個 node 註冊事件監聽器
        for i in range(len(node_instances)):
            event_emitter.on(f"node_start_{i}", create_node_executor(i))

        # 發送第一個 node 的開始信號
        event_emitter.emit("node_start_0")

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
