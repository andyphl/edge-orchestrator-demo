import argparse
import asyncio
import importlib
import json
import os
from enum import Enum
from queue import PriorityQueue, Queue
from threading import Event, Thread
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import (FastAPI, File, Form, HTTPException, UploadFile, WebSocket,
                     WebSocketDisconnect)
from starlette.responses import FileResponse, HTMLResponse

from aiwin_resource.creator import ResourceCreator
from aiwin_resource.instance_manager import ResourceInstanceManager
from aiwin_resource.plugins.image.v1.main import ImageResource
from aiwin_resource.plugins.number.v1.main import NumberResource
from aiwin_resource.plugins.numbers.v1.main import NumbersResource
from aiwin_resource.plugins.string.v1.main import StringResource
from aiwin_resource.plugins.unknown.v1.main import UnknownResource
from aiwin_resource.plugins.vision.input.usb_device.v1.main import \
    UsbDeviceResource
from aiwin_resource.plugins.vision.input.usb_devices.v1.main import \
    UsbDevicesResource
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
        # 每次初始化時重新創建 queue，確保狀態乾淨
        # Queue 中只存儲 FrameRef（輕量級引用），不存儲實際圖像數據
        from node.base import FrameRef
        self._priority_queue: PriorityQueue[tuple[float, FrameRef]] = PriorityQueue(
        )
        # 限制 WebSocket 消息队列大小，避免内存泄漏
        # 如果队列满了，丢弃最旧的消息（FIFO）
        self._ws_message_queue: Queue[Dict[str, Any]] = Queue(maxsize=10)
        self._ws_thread: Optional[Thread] = None
        self._node_context = BaseNodeContext(
            resource_manager=self._resource_manager,
            resource_creator=self._resource_creator,
            file_store=self._file_store,
            event=self._event_emitter,
            priority_queue=self._priority_queue,
            ws_message_queue=self._ws_message_queue
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

        # 啟動 WebSocket 消息處理線程
        self._ws_thread = Thread(
            target=self._ws_message_handler_thread, daemon=True)
        self._ws_thread.start()

        # 在新線程中執行 pipeline
        self._execution_thread = Thread(
            target=self._run_pipeline_thread, daemon=True)
        self._execution_thread.start()

        return {"message": "Pipeline started", "status": self.status}

    def stop(self):
        """停止 pipeline"""
        print(
            f"[PipelineManager] stop() called, current status: {self.status}")
        if self.status != PipelineStatus.RUNNING:
            return {"message": "Pipeline is not running", "status": self.status}

        # 設置停止標誌
        print(f"[PipelineManager] Setting stop event...")
        self._stop_event.set()

        # 先清理資源（包括關閉相機），這樣可以立即釋放資源
        print(f"[PipelineManager] Cleaning up nodes...")
        self._cleanup_nodes()

        # 等待執行線程結束（最多等待 2 秒）
        if self._execution_thread and self._execution_thread.is_alive():
            print(f"[PipelineManager] Waiting for execution thread to finish...")
            self._execution_thread.join(timeout=2.0)
            if self._execution_thread.is_alive():
                print("Warning: Execution thread did not stop within timeout")
            else:
                print(f"[PipelineManager] Execution thread stopped")

        # 等待 WebSocket 消息處理線程結束
        if self._ws_thread and self._ws_thread.is_alive():
            print(f"[PipelineManager] Waiting for WS thread to finish...")
            self._ws_thread.join(timeout=1.0)
            if self._ws_thread.is_alive():
                print("Warning: WebSocket thread did not stop within timeout")
            else:
                print(f"[PipelineManager] WebSocket thread stopped")

        self.status = PipelineStatus.STOPPED
        print(f"[PipelineManager] Pipeline stopped, status: {self.status}")

        return {"message": "Pipeline stopped", "status": self.status}

    def _cleanup_nodes(self):
        """清理所有 node 實例"""
        print(
            f"[PipelineManager] _cleanup_nodes() called, disposing {len(self._node_instances)} nodes")
        for i, node_instance in enumerate(self._node_instances):
            try:
                print(f"[PipelineManager] Disposing node {i}...")
                node_instance.dispose()
                print(f"[PipelineManager] Node {i} disposed successfully")
            except Exception as e:
                print(f"[PipelineManager] Error disposing node {i}: {e}")
                import traceback
                traceback.print_exc()
        self._node_instances.clear()
        print(f"[PipelineManager] All nodes cleaned up")

    def _ws_message_handler_thread(self):
        """處理 WebSocket 消息的後台線程"""
        import asyncio
        import queue as std_queue
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def process_messages():
            processed_count = 0
            while not self._stop_event.is_set():
                try:
                    # 使用 timeout 來定期檢查停止事件
                    message = self._ws_message_queue.get(timeout=0.1)
                    if message:
                        # 發送到所有連接的 WebSocket
                        message_str = json.dumps(message)
                        seq = message.get('seq', 'N/A')
                        try:
                            await asyncio.wait_for(
                                manager.broadcast(message_str),
                                timeout=2.0  # 2秒超时
                            )
                            processed_count += 1
                            print(
                                f"[WS] Broadcasted {message.get('type', 'unknown')} seq={seq} to {len(manager.active_connections)} connections (total processed: {processed_count})")
                        except asyncio.TimeoutError:
                            print(
                                f"[WS] Timeout broadcasting seq={seq}, skipping")
                        except Exception as e:
                            print(f"[WS] Error broadcasting seq={seq}: {e}")
                            import traceback
                            traceback.print_exc()
                except std_queue.Empty:
                    # 超時，繼續循環
                    await asyncio.sleep(0.01)
                except Exception as e:
                    # 其他錯誤，記錄但繼續運行
                    print(f"[WS] Error in process_messages: {e}")
                    import traceback
                    traceback.print_exc()
                    await asyncio.sleep(0.01)

        try:
            loop.run_until_complete(process_messages())
        except Exception as e:
            print(f"Error in WebSocket message handler: {e}")
        finally:
            loop.close()

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
                    node_instance: BaseNode | None = None
                    try:
                        print(
                            f"[PipelineManager] execute_node({node_index}) called, data={data}, stop_event={self._stop_event.is_set()}")
                        if self._stop_event.is_set():
                            print(
                                f"[PipelineManager] execute_node({node_index}) stopped: stop_event is set")
                            return

                        print(
                            f"[PipelineManager] execute_node({node_index}) checking node_index: {node_index} >= {len(self._node_instances)}?")
                        if node_index >= len(self._node_instances):
                            print(
                                f"[PipelineManager] execute_node({node_index}) stopped: node_index >= len({len(self._node_instances)})")
                            return

                        node_instance = self._node_instances[node_index]
                        print(
                            f"[PipelineManager] execute_node({node_index}) got node_instance: {type(node_instance).__name__}")

                        # 在執行前再次檢查停止標誌
                        if self._stop_event.is_set():
                            print(
                                f"[PipelineManager] execute_node({node_index}) stopped: stop_event is set (second check)")
                            return

                        print(
                            f"[PipelineManager] Executing node {node_index} (calling execute())")
                        node_instance.execute()
                        print(
                            f"[PipelineManager] Node {node_index} execute() completed")
                    except Exception as e:
                        print(
                            f"[PipelineManager] Error in execute_node({node_index}): {e}")
                        import traceback
                        traceback.print_exc()
                        # 即使出錯也要繼續，避免阻塞整個 pipeline
                        # 但需要確保循環能繼續
                        # 不要直接 return，而是繼續執行 next() 邏輯，確保循環不會中斷
                        node_instance = None  # 標記為 None，讓後續邏輯知道出錯了

                    if self._stop_event.is_set():
                        print(
                            f"[PipelineManager] Stop event set, returning from execute_node for node {node_index}")
                        return

                    # 只在第一次执行时保存资源快照，避免循环执行时频繁序列化导致递归错误
                    # 如果需要调试，可以取消注释下面的代码
                    # if self._resource_manager is not None:
                    #     try:
                    #         json.dump(
                    #             self._resource_manager.serialize(),
                    #             open(
                    #                 f"resource_after_execute_node_{node_index}.json", "w"),
                    #             indent=4
                    #         )
                    #     except Exception as e:
                    #         print(f"Error saving resource snapshot: {e}")

                    if not self._stop_event.is_set():
                        if node_instance is None:
                            print(
                                f"[PipelineManager] ERROR: node_instance is None for node {node_index}, cannot proceed")
                            return
                        # 檢查是否為最後一個 node，如果是則循環回到第一個
                        # 使用 getattr 來訪問 cfg，因為 BaseNode 是 Protocol
                        node_cfg = getattr(node_instance, 'cfg', {})
                        print(
                            f"[PipelineManager] Node {node_index} cfg: {node_cfg}")
                        if isinstance(node_cfg, dict):
                            next_node_index: Optional[int] = node_cfg.get(
                                '_next_node_index')  # type: ignore
                        else:
                            next_node_index = None
                        print(
                            f"[PipelineManager] Node {node_index} next_node_index: {next_node_index}")

                        if next_node_index is None:
                            # 最後一個 node，循環回到第一個 node
                            if self._event_emitter is not None and not self._stop_event.is_set():
                                print(
                                    f"[PipelineManager] Last node ({node_index}) executed, looping back to node 0 via event emitter")
                                self._event_emitter.emit("node_start_0")
                            else:
                                print(
                                    f"[PipelineManager] Last node ({node_index}) executed, but cannot loop: event_emitter={self._event_emitter is not None}, stop_event={self._stop_event.is_set()}")
                        else:
                            if not self._stop_event.is_set():
                                print(
                                    f"[PipelineManager] Calling node {node_index}.next() to trigger node {next_node_index}")
                                node_instance.next()
                                print(
                                    f"[PipelineManager] Node {node_index}.next() completed")
                            else:
                                print(
                                    f"[PipelineManager] Stop event set, skipping node {node_index}.next()")
                    else:
                        if node_instance is None:
                            print(
                                f"[PipelineManager] node_instance is None, skipping next() logic for node {node_index}")
                        else:
                            print(
                                f"[PipelineManager] Stop event set, skipping next() logic for node {node_index}")

                return execute_node

            # 註冊事件監聽器
            print(
                f"[PipelineManager] Registering event listeners for {len(self._node_instances)} nodes")
            for i in range(len(self._node_instances)):
                event_name = f"node_start_{i}"
                print(
                    f"[PipelineManager] Registering listener for event: {event_name}")
                self._event_emitter.on(
                    event_name, create_node_executor(i))
                print(
                    f"[PipelineManager] Registered listener for event: {event_name}")

            # 發送第一個 node 的開始信號
            if not self._stop_event.is_set():
                print(f"[PipelineManager] Emitting initial event: node_start_0")
                self._event_emitter.emit("node_start_0")
            else:
                print(
                    f"[PipelineManager] Stop event is set, not emitting initial event")

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
        """广播消息到所有连接，带错误处理和超时"""
        disconnected: List[WebSocket] = []
        for connection in self.active_connections:
            try:
                # 添加超时保护，避免单个连接阻塞整个广播
                await asyncio.wait_for(connection.send_text(message), timeout=1.0)
            except asyncio.TimeoutError:
                print(
                    f"[ConnectionManager] Timeout sending message to connection, removing it")
                disconnected.append(connection)
            except Exception as e:
                print(
                    f"[ConnectionManager] Error sending message to connection: {e}, removing it")
                disconnected.append(connection)

        # 清理断开的连接
        for conn in disconnected:
            try:
                self.active_connections.remove(conn)
            except ValueError:
                pass


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


@app.get("/view", response_class=HTMLResponse)
async def pipeline_viewer():
    """Pipeline WebSocket 客戶端視圖"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pipeline WebSocket Viewer</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .status {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.2);
            margin-top: 10px;
            font-size: 0.9em;
        }
        
        .status.connected {
            background: rgba(76, 175, 80, 0.3);
        }
        
        .status.disconnected {
            background: rgba(244, 67, 54, 0.3);
        }
        
        .content {
            padding: 30px;
        }
        
        .section {
            margin-bottom: 30px;
        }
        
        .section h2 {
            color: #333;
            margin-bottom: 15px;
            font-size: 1.5em;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        
        .messages {
            max-height: 300px;
            overflow-y: auto;
            background: #f5f5f5;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }
        
        .message {
            padding: 10px;
            margin-bottom: 8px;
            background: white;
            border-radius: 6px;
            border-left: 4px solid #667eea;
            font-size: 0.9em;
        }
        
        .message-time {
            color: #666;
            font-size: 0.8em;
            margin-right: 10px;
        }
        
        .images {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .image-card {
            background: #f9f9f9;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s;
        }
        
        .image-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        
        .image-card img {
            width: 100%;
            height: auto;
            border-radius: 6px;
            margin-bottom: 10px;
        }
        
        .image-info {
            font-size: 0.85em;
            color: #666;
        }
        
        .image-info strong {
            color: #333;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .stat-label {
            font-size: 0.9em;
            opacity: 0.9;
        }
        
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #999;
        }
        
        .empty-state::before {
            content: "📷";
            font-size: 4em;
            display: block;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎥 Pipeline WebSocket Viewer</h1>
            <div id="status" class="status disconnected">未連接</div>
        </div>
        
        <div class="content">
            <div class="section">
                <h2>📊 統計資訊</h2>
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-value" id="total-images">0</div>
                        <div class="stat-label">處理的圖像數</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="queue-size">0</div>
                        <div class="stat-label">當前 Queue 大小</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="messages-count">0</div>
                        <div class="stat-label">接收的消息數</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="cpu-percent">0%</div>
                        <div class="stat-label">CPU 使用率</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="memory-percent">0%</div>
                        <div class="stat-label">記憶體使用率</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="process-memory">0 MB</div>
                        <div class="stat-label">進程記憶體</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>💻 系統監控</h2>
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-value" id="ws-queue-size">0</div>
                        <div class="stat-label">WebSocket 消息隊列</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="active-connections">0</div>
                        <div class="stat-label">活躍連接數</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="pipeline-status">-</div>
                        <div class="stat-label">Pipeline 狀態</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>📝 消息日誌</h2>
                <div class="messages" id="messages"></div>
            </div>
            
            <div class="section">
                <h2>🖼️ 處理結果</h2>
                <div id="images" class="images">
                    <div class="empty-state">等待圖像數據...</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        const ws = new WebSocket(`${wsProtocol}//${wsHost}/ws`);
        
        const statusDiv = document.getElementById('status');
        const messagesDiv = document.getElementById('messages');
        const imagesDiv = document.getElementById('images');
        const totalImagesSpan = document.getElementById('total-images');
        const queueSizeSpan = document.getElementById('queue-size');
        const messagesCountSpan = document.getElementById('messages-count');
        const cpuPercentSpan = document.getElementById('cpu-percent');
        const memoryPercentSpan = document.getElementById('memory-percent');
        const processMemorySpan = document.getElementById('process-memory');
        const wsQueueSizeSpan = document.getElementById('ws-queue-size');
        const activeConnectionsSpan = document.getElementById('active-connections');
        const pipelineStatusSpan = document.getElementById('pipeline-status');
        
        let totalImages = 0;
        let messagesCount = 0;
        let hasImages = false;
        
        // 定期更新監控資訊
        let metricsUpdateInProgress = false;
        async function updateMetrics() {
            // 防止并发更新
            if (metricsUpdateInProgress) {
                return;
            }
            
            metricsUpdateInProgress = true;
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 2000); // 2秒超时
                
                const response = await fetch('/metrics', {
                    signal: controller.signal
                });
                clearTimeout(timeoutId);
                
                const data = await response.json();
                
                // 使用 requestAnimationFrame 批量更新 DOM
                requestAnimationFrame(() => {
                    // 更新系統資源
                    cpuPercentSpan.textContent = `${data.system.cpu_percent.toFixed(1)}%`;
                    memoryPercentSpan.textContent = `${data.system.memory_percent.toFixed(1)}%`;
                    processMemorySpan.textContent = `${data.system.process_memory_mb.toFixed(1)} MB`;
                    
                    // 更新 Pipeline 資訊
                    wsQueueSizeSpan.textContent = data.pipeline.ws_message_queue_size;
                    activeConnectionsSpan.textContent = data.pipeline.active_connections;
                    pipelineStatusSpan.textContent = data.pipeline.status;
                    
                    // 更新 Queue 大小（如果消息中有更新）
                    if (data.pipeline.priority_queue_size !== undefined) {
                        queueSizeSpan.textContent = data.pipeline.priority_queue_size;
                    }
                });
            } catch (e) {
                // 静默处理错误，避免控制台阻塞
                if (e.name !== 'AbortError') {
                    console.error('Failed to fetch metrics:', e);
                }
            } finally {
                metricsUpdateInProgress = false;
            }
        }
        
        // 每 2 秒更新一次監控資訊（降低频率，减少负载）
        setInterval(updateMetrics, 2000);
        updateMetrics(); // 立即更新一次

        function updateStatus(connected) {
            if (connected) {
                statusDiv.textContent = '✅ 已連接';
                statusDiv.className = 'status connected';
            } else {
                statusDiv.textContent = '❌ 未連接';
                statusDiv.className = 'status disconnected';
            }
        }

        // 限制消息日志数量，避免 DOM 过多导致卡顿
        const maxMessages = 100;
        
        function addMessage(text, type = 'info') {
            messagesCount++;
            messagesCountSpan.textContent = messagesCount;
            
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message';
            const time = new Date().toLocaleTimeString();
            messageDiv.innerHTML = `<span class="message-time">${time}</span>${text}`;
            messagesDiv.appendChild(messageDiv);
            
            // 限制消息数量，移除最旧的消息
            while (messagesDiv.children.length > maxMessages) {
                messagesDiv.removeChild(messagesDiv.firstChild);
            }
            
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        // 使用 requestAnimationFrame 来批量处理 DOM 更新，避免阻塞
        let pendingImages = [];
        let isProcessing = false;
        
        function processPendingImages() {
            if (pendingImages.length === 0) {
                isProcessing = false;
                return;
            }
            
            isProcessing = true;
            // 每次处理最多 5 张图像，避免一次性处理太多导致卡顿
            const batch = pendingImages.splice(0, 5);
            
            // 使用 DocumentFragment 批量插入，提高性能
            const fragment = document.createDocumentFragment();
            
            for (const data of batch) {
                totalImages++;
                totalImagesSpan.textContent = totalImages;
                if (data.queue_size !== undefined) {
                    queueSizeSpan.textContent = data.queue_size;
                }
                
                const imageCard = document.createElement('div');
                imageCard.className = 'image-card';
                
                const img = document.createElement('img');
                img.src = data.image;
                img.alt = 'Binarization Result';
                img.loading = 'lazy'; // 延迟加载，提高性能
                img.onerror = function() {
                    console.error('Failed to load image #' + totalImages);
                    this.style.display = 'none';
                };
                
                const info = document.createElement('div');
                info.className = 'image-info';
                const timestamp = new Date(data.timestamp * 1000).toLocaleString();
                info.innerHTML = `
                    <strong>Node:</strong> ${data.node_id || 'N/A'}<br>
                    <strong>Seq:</strong> ${data.seq || 'N/A'}<br>
                    <strong>Queue Size:</strong> ${data.queue_size || 0}<br>
                    <strong>Time:</strong> ${timestamp}<br>
                    <strong>#${totalImages}</strong>
                `;
                
                imageCard.appendChild(img);
                imageCard.appendChild(info);
                fragment.appendChild(imageCard);
            }
            
            // 确保 imagesDiv 已初始化
            if (!imagesDiv) {
                console.error('imagesDiv not found');
                isProcessing = false;
                return;
            }
            
            if (!hasImages) {
                imagesDiv.innerHTML = '';
                hasImages = true;
            }
            
            // 批量插入
            imagesDiv.insertBefore(fragment, imagesDiv.firstChild);
            
            // 限制顯示的圖像數量（最多 50 張）
            while (imagesDiv.children.length > 50) {
                imagesDiv.removeChild(imagesDiv.lastChild);
            }
            
            // 继续处理剩余的消息
            requestAnimationFrame(processPendingImages);
        }
        
        function addImage(data) {
            // 将新图像添加到待处理队列
            pendingImages.push(data);
            
            // 如果当前没有在处理，启动处理
            if (!isProcessing) {
                requestAnimationFrame(processPendingImages);
            }
        }

        ws.onopen = () => {
            updateStatus(true);
            addMessage('WebSocket 連接成功', 'success');
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                // 减少日志输出，避免控制台阻塞
                if (totalImages % 10 === 0) {
                    console.log('Received message:', data.type, 'seq=' + (data.seq || 'N/A'));
                }
                
                if (data.type === 'binarization_result') {
                    addImage(data);
                    // 减少消息日志，避免 DOM 操作过多导致卡顿
                    if (totalImages % 10 === 0) {
                        addMessage(`收到圖像處理結果 #${totalImages + 1} (Node: ${data.node_id}, Queue: ${data.queue_size || 0})`, 'success');
                    }
                } else {
                    addMessage(`收到消息: ${event.data.substring(0, 100)}`, 'info');
                }
            } catch (e) {
                console.error('Error parsing message:', e, event.data);
                addMessage(`收到原始消息: ${event.data.substring(0, 100)}`, 'info');
            }
        };

        ws.onerror = (error) => {
            updateStatus(false);
            addMessage('WebSocket 錯誤', 'error');
            console.error('WebSocket error:', error);
        };

        ws.onclose = () => {
            updateStatus(false);
            addMessage('WebSocket 連接已關閉，嘗試重新連接...', 'warning');
            
            // 嘗試重新連接
            setTimeout(() => {
                location.reload();
            }, 3000);
        };
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


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


@app.get("/metrics")
async def get_metrics():
    """獲取系統資源使用量和 pipeline 監控資訊"""
    system_info = {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "memory_used_mb": 0.0,
        "memory_total_mb": 0.0,
        "process_memory_mb": 0.0,
    }

    try:
        import os

        import psutil

        # 獲取系統資源
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        process = psutil.Process(os.getpid())
        process_memory = process.memory_info()

        system_info = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_mb": memory.used / (1024 * 1024),
            "memory_total_mb": memory.total / (1024 * 1024),
            "process_memory_mb": process_memory.rss / (1024 * 1024),
        }
    except ImportError:
        # 如果 psutil 未安裝，嘗試使用系統命令獲取（僅限 Unix 系統）
        try:
            import os
            import subprocess

            # 獲取 CPU 使用率（使用 top 命令）
            try:
                result = subprocess.run(
                    ['top', '-l', '1', '-n', '0'],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                # 簡單解析，這裡只是 fallback
                system_info["cpu_percent"] = 0.0  # 無法簡單解析，設為 0
            except:
                pass

            # 獲取記憶體使用（使用 vm_stat 或 free）
            try:
                # macOS 使用 vm_stat
                result = subprocess.run(
                    ['vm_stat'],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                # 簡單解析，這裡只是 fallback
                system_info["memory_percent"] = 0.0
            except:
                pass

            # 獲取進程記憶體（使用 ps）
            try:
                pid = os.getpid()
                result = subprocess.run(
                    ['ps', '-o', 'rss=', '-p', str(pid)],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if result.returncode == 0 and result.stdout.strip():
                    rss_kb = int(result.stdout.strip())
                    system_info["process_memory_mb"] = rss_kb / 1024.0
            except:
                pass
        except Exception as e:
            print(f"Error getting system metrics (fallback): {e}")
    except Exception as e:
        print(f"Error getting system metrics: {e}")
        import traceback
        traceback.print_exc()

    # 獲取 pipeline 相關資訊
    priority_queue_size = 0
    ws_queue_size = 0
    try:
        if hasattr(pipeline_manager, '_priority_queue'):
            priority_queue_size = pipeline_manager._priority_queue.qsize()  # type: ignore
        if hasattr(pipeline_manager, '_ws_message_queue'):
            ws_queue_size = pipeline_manager._ws_message_queue.qsize()  # type: ignore
    except Exception:
        pass

    return {
        "system": system_info,
        "pipeline": {
            "status": pipeline_manager.status.value,
            "priority_queue_size": priority_queue_size,
            "ws_message_queue_size": ws_queue_size,
            "active_connections": len(manager.active_connections),
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", type=bool, default=True)
    parser.add_argument("--log-level", type=str, default="info")
    args = parser.parse_args()

    uvicorn.run("main:app", host=args.host, port=args.port,
                reload=args.reload, log_level=args.log_level)


if __name__ == "__main__":
    main()
