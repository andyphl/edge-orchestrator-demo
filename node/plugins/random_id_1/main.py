import time
from typing import Any, Dict, List

import cv2
from cv2.typing import MatLike

from aiwin_resource.base import Resource
from node.base import BaseNode, BaseNodeContext


class WebcamNode(BaseNode):
    _image_resource: Resource[MatLike] | None = None
    _cap: cv2.VideoCapture | None = None
    _seq: int = 0  # 序列號，用於追蹤處理順序

    def __init__(self, ctx: BaseNodeContext, config: Dict[str, Any]):
        self.ctx = ctx
        self.cfg = config
        self._seq = 0
        self._last_capture_time = 0.0  # 初始化 interval 時間戳

        self._image_resource = self.ctx['resource_creator'].create('image.v1', {
            'name': 'image',
            'scopes': [self.cfg['id']],
            'data': None,
            "filename": f"{self.cfg['id']}_image.jpg"
        })
        self.ctx['resource_manager'].set(
            self._image_resource.get_key(), self._image_resource)

    def _list_devices(self, max_devices: int = 10) -> List[int]:
        available: List[int] = []
        for i in range(max_devices):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()
        return available

    def prepare(self) -> None:
        # provide all available devices as resources
        devices = self._list_devices()

        use_devices_resource = self.ctx['resource_creator'].create('vision.input.usb_devices.v1', {
            'name': 'usb_devices',
            'scopes': [self.cfg['id']],
            'data': devices,
        })
        self.ctx['resource_manager'].set(
            use_devices_resource.get_key(), use_devices_resource)

        # 在 prepare 時打開相機，避免在 execute 時頻繁開關
        device_id = self.cfg.get('config', {}).get('device_id')
        if device_id is not None:
            try:
                # Check if device is available before attempting to open
                if device_id not in devices:
                    raise ValueError(
                        f"Device {device_id} is not available. "
                        f"Available devices: {devices if devices else 'none'}. "
                        f"Make sure the camera is connected and not in use by another application.")

                self._cap = cv2.VideoCapture(device_id)
                if not self._cap.isOpened():
                    raise ValueError(
                        f"Failed to open video capture for device {device_id}. "
                        f"Available devices: {devices if devices else 'none'}. "
                        f"The device may be in use by another application or may require permissions.")

                # Set some properties to help with initialization
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception as e:
                print(f"Warning: Failed to open camera in prepare: {e}")
                # 如果 prepare 時打開失敗，會在 execute 時重試
                if self._cap is not None:
                    try:
                        self._cap.release()
                    except:
                        pass
                    self._cap = None

    def setup(self, config: Dict[str, Any]) -> None:
        pass

    def execute(self) -> Any:
        print(f"[WebcamNode] execute() called, seq={self._seq}")
        device_id = self.cfg.get('config', {}).get('device_id')

        if device_id is None:
            raise ValueError("device_id is required")

        # 檢查 interval 參數，控制捕獲頻率（單位：秒）
        # 如果距離上次捕獲時間小於 interval，則跳過本次執行
        interval = self.cfg.get('config', {}).get(
            'interval', 0.0)  # 默認 0.0 表示不限制
        print(
            f"[WebcamNode] interval={interval}, _last_capture_time={self._last_capture_time}")

        if interval > 0.0:
            current_time = time.time()
            # 如果是第一次執行（_last_capture_time == 0.0），直接允許執行
            if self._last_capture_time > 0.0:
                time_since_last = current_time - self._last_capture_time
                if time_since_last < interval:
                    # 距離上次捕獲時間太短，跳過本次執行
                    print(
                        f"[WebcamNode] Skipping capture: {time_since_last:.3f}s < {interval:.3f}s interval")
                    return
            # 注意：不要在這裡更新時間戳，應該在成功捕獲後才更新
            # 這樣可以確保即使捕獲失敗，也不會影響下次檢查

        # 確保相機已打開（應該在 prepare 時已打開，這裡只是檢查）
        if self._cap is None or not self._cap.isOpened():
            # 如果相機未打開，嘗試打開（可能是 prepare 時失敗了）
            available_devices = self._list_devices()
            if device_id not in available_devices:
                raise ValueError(
                    f"Device {device_id} is not available. "
                    f"Available devices: {available_devices if available_devices else 'none'}. "
                    f"Make sure the camera is connected and not in use by another application.")

            self._cap = cv2.VideoCapture(device_id)
            if not self._cap.isOpened():
                raise ValueError(
                    f"Failed to open video capture for device {device_id}. "
                    f"Available devices: {available_devices if available_devices else 'none'}. "
                    f"The device may be in use by another application or may require permissions.")

            # Set some properties to help with initialization
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        try:
            # 確保相機已初始化
            cap = self._cap
            if cap is None:  # type: ignore
                raise ValueError("Camera not initialized")

            ret, frame = cap.read()
            if not ret:
                # 讀取失敗，但不關閉相機，讓它保持打開狀態
                # 可能是暫時的讀取問題，下次 execute 時再試
                print(
                    f"[WebcamNode] Warning: Failed to read frame from device {device_id}")
                return  # 直接返回，不抛出异常，避免中断循环

            if frame.size == 0:  # type: ignore
                print(
                    f"[WebcamNode] Warning: Received empty frame from device {device_id}")
                return  # 直接返回，不抛出异常，避免中断循环

            print(
                f"[WebcamNode] Successfully read frame: shape={frame.shape}, size={frame.size}")

            # ✅ 暫時不使用 queue，直接更新 Resource
            # 1. 更新 Resource（這是唯一存放圖像數據的地方）
            if self._image_resource is None:
                raise ValueError("Image resource not initialized")

            try:
                # 更新 resource，這是圖像數據的唯一來源
                self._image_resource.set_data(frame)
                self._seq += 1

                # 在成功捕獲後更新時間戳（用於 interval 檢查）
                if interval > 0.0:
                    self._last_capture_time = time.time()

                elapsed = time.time() - \
                    self._last_capture_time if self._seq > 1 and self._last_capture_time > 0 else 0.0
                print(
                    f"[WebcamNode] Captured frame seq={self._seq}, updated resource: {self._image_resource.get_key()}, elapsed={elapsed:.3f}s")
            except Exception as e:
                print(f"Warning: Failed to update image resource: {e}")
                import traceback
                traceback.print_exc()
                # 如果更新失敗，跳過本次處理
                return

            # 2. 暫時不使用 queue，直接通過 Resource 傳遞
            # timestamp = time.time()
            # frame_ref: FrameRef = {
            #     "resource_key": self._image_resource.get_key(),
            #     "timestamp": timestamp,
            #     "seq": self._seq
            # }
            # priority_queue.put((-timestamp, frame_ref))
        except Exception as e:
            print(f"Error processing image in WebcamNode: {e}")
            # 不關閉相機，讓它保持打開狀態，只在 dispose 時關閉

    def next(self) -> None:
        next_node_index = self.cfg.get('_next_node_index')
        print(
            f"[WebcamNode] next() called, next_node_index={next_node_index}, cfg={self.cfg.get('id', 'unknown')}")

        if next_node_index is None:
            print(f"[WebcamNode] next() returning early: next_node_index is None")
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
                f"[WebcamNode] next() detected stale _emitting_event: {current_emitting}, clearing and continuing")
            # 清除舊標記，允許繼續（這是正常的鏈式調用，不是真正的重入）
            self._emitting_event = None

        # 設置標記並發送事件
        self._emitting_event = event_name
        print(f"[WebcamNode] next() emitting event: {event_name}")
        try:
            self.ctx['event'].emit(event_name)
            print(
                f"[WebcamNode] next() event emitted successfully: {event_name}")
        except Exception as e:
            print(f"[WebcamNode] next() error emitting event: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 清除標記
            self._emitting_event = None
            print(f"[WebcamNode] next() completed, _emitting_event cleared")

    def dispose(self) -> None:
        print(f"[WebcamNode] dispose() called, releasing camera...")
        # 關閉相機（優先處理，確保資源釋放）
        if self._cap is not None:
            try:
                print(f"[WebcamNode] Camera is opened: {self._cap.isOpened()}")
                if self._cap.isOpened():
                    self._cap.release()
                    print(f"[WebcamNode] Camera released successfully")
            except Exception as e:
                print(f"[WebcamNode] Error releasing camera: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self._cap = None
                print(f"[WebcamNode] Camera reference cleared")

        # 釋放資源
        if self._image_resource is not None:
            try:
                self._image_resource.dispose()
                print(f"[WebcamNode] Image resource disposed")
            except Exception as e:
                print(f"[WebcamNode] Error disposing image resource: {e}")
                import traceback
                traceback.print_exc()
