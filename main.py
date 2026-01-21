import argparse
import importlib
import json
import os
from enum import Enum
from threading import Event, Thread
from typing import Any, Dict, List, Optional

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


class PipelineStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"


class PipelineManager:
    def __init__(self):
        self.pipeline_config: Optional[List[Dict[str, Any]]] = None
        self.status: PipelineStatus = PipelineStatus.IDLE
        self._stop_event = Event()
        self._execution_thread: Optional[Thread] = None
        self._node_manager: Optional[NodeManager] = None
        self._resource_manager: Optional[ResourceInstanceManager] = None
        self._resource_creator: Optional[ResourceCreator] = None
        self._file_store: Optional[FileStore] = None
        self._event_emitter: Optional[EventEmitter] = None
        self._node_context: Optional[BaseNodeContext] = None
        self._node_instances: List[BaseNode] = []

    def _initialize_components(self):
        """初始化所有必要的組件"""
        plugin_map = {
            "webcam": "random_id_1",
            "binarization": "random_id_2",
            "cast_resource": "random_id_4",
        }

        self._node_manager = NodeManager()

        for plugin_name, register_id in plugin_map.items():
            base_plugin_path = f"./node/plugins/{register_id}"
            if not os.path.exists(base_plugin_path):
                raise FileNotFoundError(f"Plugin {register_id} not found")
            manifest = json.load(open(f"{base_plugin_path}/manifest.json"))
            backend_entrypoint = manifest["backend_entrypoint"]
            backend_module, backend_class = backend_entrypoint.split("#")
            backend_module = backend_module.replace(".py", "")
            module_path = f"node.plugins.{register_id}.{backend_module}"
            backend_module = importlib.import_module(module_path)
            backend_class = getattr(backend_module, backend_class)
            self._node_manager.register(plugin_name, backend_class)

        self._resource_manager = ResourceInstanceManager()

        self._resource_creator = ResourceCreator()
        self._resource_creator.register("image.v1", ImageResource)
        self._resource_creator.register("string.v1", StringResource)
        self._resource_creator.register("number.v1", NumberResource)
        self._resource_creator.register("numbers.v1", NumbersResource)
        self._resource_creator.register("unknown.v1", UnknownResource)
        self._resource_creator.register(
            "vision.input.usb_device.v1", UsbDeviceResource)
        self._resource_creator.register(
            "vision.input.usb_devices.v1", UsbDevicesResource)

        self._file_store = FileStore(cfg={"url": "http://localhost:8000"})
        self._event_emitter = EventEmitter()
        self._node_context = BaseNodeContext(
            resource_manager=self._resource_manager,
            resource_creator=self._resource_creator,
            file_store=self._file_store,
            event=self._event_emitter
        )

    def set_config(self, pipeline: List[Dict[str, Any]]):
        """設置 pipeline 配置"""
        if self.status == PipelineStatus.RUNNING:
            raise HTTPException(
                status_code=400,
                detail="Cannot set config while pipeline is running. Please stop it first."
            )
        self.pipeline_config = pipeline
        self.status = PipelineStatus.IDLE
        return {"message": "Pipeline config set successfully", "status": self.status}

    def start(self):
        """開始執行 pipeline"""
        if self.pipeline_config is None:
            raise HTTPException(
                status_code=400,
                detail="Pipeline config not set. Please call /config first."
            )

        if self.status == PipelineStatus.RUNNING:
            raise HTTPException(
                status_code=400,
                detail="Pipeline is already running. Please stop it first."
            )

        # 重置停止事件
        self._stop_event.clear()
        self.status = PipelineStatus.RUNNING

        # 每次啟動時重新初始化組件，確保狀態乾淨
        self._initialize_components()

        # 在新線程中執行 pipeline
        self._execution_thread = Thread(
            target=self._run_pipeline_thread, daemon=True)
        self._execution_thread.start()

        return {"message": "Pipeline started", "status": self.status}

    def stop(self):
        """停止 pipeline"""
        if self.status != PipelineStatus.RUNNING:
            return {"message": "Pipeline is not running", "status": self.status}

        # 設置停止標誌
        self._stop_event.set()
        self.status = PipelineStatus.STOPPED

        # 等待執行線程結束（最多等待 5 秒）
        if self._execution_thread and self._execution_thread.is_alive():
            self._execution_thread.join(timeout=5.0)

        # 清理資源
        self._cleanup_nodes()

        return {"message": "Pipeline stopped", "status": self.status}

    def _cleanup_nodes(self):
        """清理所有 node 實例"""
        for node_instance in self._node_instances:
            try:
                node_instance.dispose()
            except Exception as e:
                print(f"Error disposing node: {e}")
        self._node_instances.clear()

    def _run_pipeline_thread(self):
        """在背景線程中執行 pipeline"""
        try:
            if (self.pipeline_config is None or
                self._node_manager is None or
                self._resource_manager is None or
                self._event_emitter is None or
                    self._node_context is None):
                return

            # 清理之前的 node 實例
            self._cleanup_nodes()

            # 初始化所有 node 並調用 prepare
            for i, node_config in enumerate(self.pipeline_config):
                if self._stop_event.is_set():
                    return

                node_config_with_next = node_config.copy()
                if i + 1 < len(self.pipeline_config):
                    node_config_with_next['_next_node_index'] = i + 1
                else:
                    node_config_with_next['_next_node_index'] = None

                node_class = self._node_manager.get(node_config["name"])
                node_instance = node_class(
                    self._node_context, node_config_with_next)
                node_instance.prepare()
                self._node_instances.append(node_instance)

            if self._stop_event.is_set():
                return

            # 保存 prepare 後的資源快照
            json.dump(
                self._resource_manager.serialize(),
                open("resource_after_prepare.json", "w"), indent=4
            )

            # 為每個 node 註冊事件監聽器
            def create_node_executor(node_index: int):
                def execute_node(data: Any = None):
                    if self._stop_event.is_set():
                        return

                    if node_index >= len(self._node_instances):
                        return

                    node_instance = self._node_instances[node_index]
                    node_instance.execute()

                    if self._stop_event.is_set():
                        return

                    if self._resource_manager is not None:
                        json.dump(
                            self._resource_manager.serialize(),
                            open(
                                f"resource_after_execute_node_{node_index}.json", "w"),
                            indent=4
                        )

                    if not self._stop_event.is_set():
                        node_instance.next()

                return execute_node

            # 註冊事件監聽器
            for i in range(len(self._node_instances)):
                self._event_emitter.on(
                    f"node_start_{i}", create_node_executor(i))

            # 發送第一個 node 的開始信號
            if not self._stop_event.is_set():
                self._event_emitter.emit("node_start_0")

        except Exception as e:
            print(f"Error in pipeline execution: {e}")
            self.status = PipelineStatus.STOPPED
        finally:
            # 如果沒有被手動停止，執行完成後設置為 IDLE
            if not self._stop_event.is_set():
                self.status = PipelineStatus.IDLE

    def get_status(self):
        """獲取 pipeline 狀態"""
        return {
            "status": self.status,
            "has_config": self.pipeline_config is not None,
            "config_length": len(self.pipeline_config) if self.pipeline_config else 0
        }


# 全局 pipeline 管理器
pipeline_manager = PipelineManager()


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


@app.post("/config")
async def set_pipeline_config(pipeline: List[Dict[str, Any]]):
    """
    設置 pipeline 配置

    接收 pipeline 配置（list of nodes），保存配置以供後續啟動使用。
    如果 pipeline 正在運行，需要先調用 /stop 停止。
    """
    return pipeline_manager.set_config(pipeline)


@app.post("/start")
async def start_pipeline():
    """
    開始執行 pipeline

    根據之前通過 /config 設置的配置開始執行 pipeline。
    pipeline 會在背景線程中執行，可以多次調用 /start 來重複執行。
    如果 pipeline 已在運行，會返回錯誤。
    """
    return pipeline_manager.start()


@app.post("/stop")
async def stop_pipeline():
    """
    停止 pipeline

    停止當前正在執行的 pipeline。
    如果 pipeline 未在運行，會返回當前狀態。
    """
    return pipeline_manager.stop()


@app.get("/status")
async def get_pipeline_status():
    """
    獲取 pipeline 狀態

    返回當前 pipeline 的狀態信息，包括：
    - status: 當前狀態 (idle/running/stopped)
    - has_config: 是否已設置配置
    - config_length: 配置中的 node 數量
    """
    return pipeline_manager.get_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", type=bool, default=True)
    args = parser.parse_args()

    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
