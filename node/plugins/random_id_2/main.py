import base64
import queue as std_queue
import time
from typing import Any, Dict, cast

import cv2
from cv2.typing import MatLike

from aiwin_resource.base import Resource
from node.base import BaseNode, BaseNodeContext


class BinarizationNode(BaseNode):
    _binary_image_resource: Resource[MatLike] | None = None
    _seq: int = 0  # 序列號，用於追蹤處理順序

    def __init__(self, ctx: BaseNodeContext, config: Dict[str, Any]):
        self.ctx = ctx
        self.cfg = config
        self._seq = 0

    def prepare(self) -> None:
        pass

    def setup(self, config: Dict[str, Any]) -> None:
        pass

    def execute(self) -> Any:
        print(f"[BinarizationNode] execute() called, current seq={self._seq}")
        # 暫時不使用 queue，直接從 Resource 獲取數據
        ws_message_queue = self.ctx['ws_message_queue']
        resource_manager = self.ctx['resource_manager']

        # ✅ 暫時不使用 queue，直接從 Resource 獲取圖像數據
        # 根據配置中的 image 引用獲取 resource key
        image_ref = self.cfg.get('config', {}).get('image', '')
        print(f"[BinarizationNode] image_ref from config: {image_ref}")
        if not image_ref:
            print(f"[BinarizationNode] Warning: No image reference in config")
            return

        # image_ref 格式應該是 "node_a.image"，需要轉換為 resource key
        # 假設格式是 "{node_id}.{resource_name}"
        resource_key = image_ref.replace(
            '.', '.')  # 保持原樣，因為 resource key 就是這個格式

        try:
            # ✅ 從 Resource 獲取實際的圖像數據（single source of truth）
            image_resource = resource_manager.get(resource_key)
            if image_resource is None:
                print(
                    f"[BinarizationNode] Warning: Resource {resource_key} not found")
                return

            frame = cast(MatLike | None, image_resource.get_data())
            if frame is None:
                print(
                    f"[BinarizationNode] Warning: Frame data is None for resource {resource_key}")
                return

            # 檢查 frame 是否有效
            if not hasattr(frame, 'shape') or not hasattr(frame, 'size'):
                print(
                    f"[BinarizationNode] Warning: Invalid frame data type for resource {resource_key}")
                return

            if frame.size == 0:
                print(
                    f"[BinarizationNode] Warning: Empty frame for resource {resource_key}")
                return

            print(
                f"[BinarizationNode] Processing frame seq={self._seq + 1} from resource {resource_key}, shape={frame.shape}, size={frame.size}")

            # 處理圖像
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame

            threshold = self.cfg.get('config', {}).get('threshold', 128)
            _, binary_image = cv2.threshold(
                gray, threshold, 255, cv2.THRESH_BINARY)

            # ✅ 更新 Resource（代表當前 pipeline 的最新狀態）
            # 先釋放舊的 resource，避免內存泄漏
            if self._binary_image_resource is not None:
                try:
                    self._binary_image_resource.dispose()
                except Exception as e:
                    print(
                        f"[BinarizationNode] Warning: Failed to dispose old binary_image_resource: {e}")

            # 創建新的 binary_image resource
            self._binary_image_resource = self.ctx['resource_creator'].create('image.v1', {
                'name': 'binary_image',
                'scopes': [self.cfg['id']],
                'data': binary_image,
                "filename": f"{self.cfg['id']}_binary_image.jpg"
            })
            self.ctx['resource_manager'].set(
                self._binary_image_resource.get_key(), self._binary_image_resource)

            # 更新序列號
            self._seq += 1

            # 將結果發送到 WebSocket
            # 將圖像編碼為 base64
            _, buffer = cv2.imencode('.jpg', binary_image)
            image_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')

            # 將消息放入 WebSocket 消息隊列
            # 如果队列满了，丢弃最旧的消息（非阻塞方式）
            timestamp = time.time()
            message: Dict[str, Any] = {
                'type': 'binarization_result',
                'node_id': self.cfg['id'],
                'timestamp': timestamp,
                'seq': self._seq,  # 使用實際的序列號
                'image': f'data:image/jpeg;base64,{image_base64}',
                'queue_size': ws_message_queue.qsize()  # 顯示當前隊列大小
            }

            # 使用非阻塞方式放入队列，如果队列满了则丢弃最旧的消息
            try:
                ws_message_queue.put_nowait(message)
                print(
                    f"[BinarizationNode] Sent result seq={self._seq} to WS queue, ws_queue_size={ws_message_queue.qsize()}")
            except std_queue.Full:
                # 队列满了，丢弃最旧的消息，然后放入新消息
                try:
                    dropped = ws_message_queue.get_nowait()  # 丢弃最旧的消息
                    ws_message_queue.put_nowait(message)  # 放入新消息
                    print(
                        f"[BinarizationNode] WS queue full, dropped seq={dropped.get('seq', 'N/A')}, added seq={self._seq}, ws_queue_size={ws_message_queue.qsize()}")
                except std_queue.Empty:
                    # 如果队列在 get_nowait 时变空了，直接放入
                    ws_message_queue.put_nowait(message)
                    print(
                        f"[BinarizationNode] WS queue was full but now empty, added seq={self._seq}, ws_queue_size={ws_message_queue.qsize()}")

            # 每 50 张图像输出一次统计信息
            if self._seq % 50 == 0:
                print(
                    f"[BinarizationNode] Processed {self._seq} images, ws_queue_size={ws_message_queue.qsize()}")

        except Exception as e:
            print(
                f"[BinarizationNode] Error processing image seq={self._seq}: {e}")
            import traceback
            traceback.print_exc()
            # 即使出錯也要繼續，不拋出異常，讓 pipeline 繼續運行
            # 這樣可以避免 pipeline 因為單個圖像處理失敗而停止

    def next(self) -> None:
        next_node_index = self.cfg.get('_next_node_index')
        print(
            f"[BinarizationNode] next() called, next_node_index={next_node_index}, cfg={self.cfg.get('id', 'unknown')}")

        if next_node_index is None:
            print(f"[BinarizationNode] next() returning early: next_node_index is None (this is the last node, should loop back)")
            return

        # 防重入機制：避免同步無限呼叫
        # 使用實例變量而不是 context，避免類型檢查問題
        event_name = f"node_start_{next_node_index}"

        # 檢查是否正在發送相同的事件
        # 注意：由於事件處理是同步的，如果 _emitting_event 還在設置狀態，
        # 這可能是因為事件處理鏈中觸發了新的調用，但原調用的 finally 還沒執行
        # 在這種情況下，我們應該清除舊標記並繼續（因為這是正常的鏈式調用）
        current_emitting = getattr(self, '_emitting_event', None)
        if current_emitting == event_name:
            print(
                f"[BinarizationNode] next() detected stale _emitting_event: {current_emitting}, clearing and continuing")
            # 清除舊標記，允許繼續（這是正常的鏈式調用，不是真正的重入）
            self._emitting_event = None

        # 設置標記並發送事件
        self._emitting_event = event_name
        print(f"[BinarizationNode] next() emitting event: {event_name}")
        try:
            self.ctx['event'].emit(event_name)
            print(
                f"[BinarizationNode] next() event emitted successfully: {event_name}")
        except Exception as e:
            print(f"[BinarizationNode] next() error emitting event: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 清除標記 - 事件處理是同步的，所以處理完成後立即清除
            self._emitting_event = None
            print(f"[BinarizationNode] next() completed, _emitting_event cleared")

    def dispose(self) -> None:
        if (self._binary_image_resource is not None):
            self._binary_image_resource.dispose()
