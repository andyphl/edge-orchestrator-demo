# Edge Pipeline Example（Orchestrator Runtime）

這是一個**簡化版的邊緣管線（Edge Pipeline）編排器示範**：透過 `FastAPI` 提供 API，動態載入 `node/plugins/` 下的節點（node），並使用事件機制把多個 node 串成一條 pipeline 逐一執行。每個 node 執行後會把輸出寫入 `ResourceInstanceManager`，並可被後續 node 取用。

---

## 專案結構

- `main.py`
  - `FastAPI` 服務入口
  - API：`/pipeline`、`/file`、`/file/{file_name}`、`DELETE /file/{file_name}`、`/ws`
  - pipeline 執行方式：在背景 thread 中用 `EventEmitter` 送出開始事件，node 完成後通知下一個 node
- `event_emitter.py`
  - 簡單事件系統：`on(event, handler)`、`emit(event, data=None)`
- `node/`
  - `base.py`：`BaseNodeContext`（包含 `resource_manager`、`resource_creator`、`file_store`、`event`）與 `BaseNode` 協議
  - `manager.py`：`NodeManager`（registry）
  - `plugins/`
    - `random_id_1/`：`WebcamNode`（webcam 取像）
      - `manifest.json`：定義 node 的 metadata 與 `backend_entrypoint`
    - `random_id_2/`：`BinarizationNode`（影像二值化）
      - `manifest.json`：定義 node 的 metadata 與 `backend_entrypoint`
    - `random_id_3/`：`RandomConditionNode`（隨機條件節點，產生 0 或 1）
      - `manifest.json`：定義 node 的 metadata 與 `backend_entrypoint`
    - `random_id_4/`：`CastResourceNode`（資源類型轉換節點）
      - `manifest.json`：定義 node 的 metadata 與 `backend_entrypoint`
- `aiwin_resource/`
  - `instance_manager.py`：`ResourceInstanceManager`（set/get/serialize/clear_all）
  - `creator.py`：`ResourceCreator`（註冊與建立 resource）
  - `base.py`：`Resource` 基礎類別
  - `plugins/`：各種 resource 實作
    - `image/v1/main.py`：`ImageResource`（影像資源，序列化時上傳到 `/file` 並回傳可下載的 URL）
    - `string/v1/main.py`：`StringResource`（字串資源）
    - `number/v1/main.py`：`NumberResource`（數字資源）
    - `numbers/v1/main.py`：`NumbersResource`（數字陣列資源）
    - `unknown/v1/main.py`：`UnknownResource`（未知類型資源）
    - `vision/input/usb_device/v1/main.py`：`UsbDeviceResource`（USB 裝置資源）
    - `vision/input/usb_devices/v1/main.py`：`UsbDevicesResource`（USB 裝置列表資源）
- `store/file.py`
  - `FileStore`：透過 HTTP 呼叫本服務的 `/file`、`/file/{file_name}`、`DELETE /file/{file_name}` 做上傳/下載/刪除
- `utils.py`
  - 工具函數（`Disposable` 協議）
- `files/`
  - 檔案上傳存放目錄（API `/file` 的落地位置）

---

## 環境需求

- Python **3.10+**
- 主要套件（見 `pyproject.toml`）：
  - `fastapi[standard]`
  - `uvicorn`
  - `opencv-python`
  - `requests`

---

## 安裝與啟動

你可以用任一種方式安裝相依套件：

### 方式 A：使用 `uv`（專案內含 `uv.lock`）

```bash
uv sync
uv run python main.py --host 0.0.0.0 --port 8000 --reload True
```

### 方式 B：使用 `pip`

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r <(python -c "import tomllib;print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))")
python main.py --host 0.0.0.0 --port 8000 --reload True
```

啟動後可用瀏覽器或 curl 確認：

```bash
curl http://localhost:8000/
```

---

## API 說明

### `POST /pipeline`

提交一個 pipeline（list of nodes），伺服器會在背景 thread 中執行：

- 先建立所有 node instance 並呼叫 `prepare()`
- 註冊事件監聽：`node_start_0`、`node_start_1`、...
- `run_pipeline_thread` 會先 `emit("node_start_0")` 作為開始信號
- 每個 node `execute()` 完成後，會用 `event_emitter` 通知下一個 node 開始

#### Pipeline 格式

每個 node 物件最少包含：

- `id`：節點識別（同時是 resource scope 的一部分）
- `name`：node 名稱（目前內建：`webcam`、`binarization`、`cast_resource`）
- `version`：版本字串（此 demo 不強制使用）
- `config`：node 的參數

> 注意：
> - node 間串接使用事件 `node_start_{index}`；下一個 index 由 runtime 在背景執行緒內自動注入到 node config（key：`_next_node_index`）。
> - node 的載入機制：系統會根據 `name` 對應到 `plugin_map`，找到對應的 plugin 目錄（如 `random_id_1`），讀取該目錄下的 `manifest.json`，從 `backend_entrypoint` 取得實際的 node 類別並載入。

#### 範例：Webcam → Binarization

```bash
curl -X POST http://localhost:8000/pipeline \
  -H "Content-Type: application/json" \
  -d '[
    {
      "id": "node_0",
      "name": "webcam",
      "version": "v1.0.0",
      "config": { "device_id": 0 }
    },
    {
      "id": "node_1",
      "name": "binarization",
      "version": "v1.0.0",
      "config": { "image": "node_0.image" }
    }
  ]'
```

##### Resource key 規則

Resource 的 key 組合方式為：

- `key = "<scope_1>.<scope_2>....<resource_name>"`

其中 `scopes` 通常包含 node 的 `id`。例如 `WebcamNode` 產生的影像資源（`ImageResource` name=`image`，scopes=`["node_0"]`）key 會是：

- `node_0.image`

`BinarizationNode` 的 `config.image` 需要填入上一個 node 的影像 resource key。

##### 可用的 Resource 類型

系統內建以下 resource 類型（schema）：

- `image.v1`：`ImageResource`（影像資源）
- `string.v1`：`StringResource`（字串資源）
- `number.v1`：`NumberResource`（數字資源）
- `numbers.v1`：`NumbersResource`（數字陣列資源）
- `unknown.v1`：`UnknownResource`（未知類型資源）
- `vision.input.usb_device.v1`：`UsbDeviceResource`（USB 裝置資源）
- `vision.input.usb_devices.v1`：`UsbDevicesResource`（USB 裝置列表資源）

---

### `POST /file`

上傳檔案到 `files/` 目錄。

```bash
curl -X POST http://localhost:8000/file \
  -F "file=@./somefile.jpg" \
  -F "filename=somefile.jpg"
```

---

### `GET /file/{file_name}`

下載/取得檔案（通常是 `ImageResource` 序列化後給的 URL）。

```bash
curl -O http://localhost:8000/file/demo.jpg
```

---

### `DELETE /file/{file_name}`

刪除檔案。

```bash
curl -X DELETE http://localhost:8000/file/demo.jpg
```

---

### `GET /ws`（WebSocket）

簡單聊天室/廣播示範（與 pipeline 無直接關聯）。

---

## 內建 Nodes（Plugins）

### 1) `webcam`（`node/plugins/random_id_1`）

- **用途**：擷取攝影機影像並產生 `ImageResource(name="image")`
- **prepare()**：列出可用攝影機索引，寫入 `UsbDevicesResource(name="usb_devices")`
- **execute() config**
  - `device_id`：OpenCV `VideoCapture` 的裝置索引（例如 0）
- **輸出資源**：
  - `{node_id}.image`：`ImageResource`（擷取的影像）
  - `{node_id}.usb_devices`：`UsbDevicesResource`（可用裝置列表，在 prepare 階段產生）

> macOS 若讀不到鏡頭，請確認系統隱私權（Camera）已允許終端機/IDE 使用。

### 2) `binarization`（`node/plugins/random_id_2`）

- **用途**：把輸入影像轉灰階後做二值化，輸出 `ImageResource(name="binary_image")`
- **execute() config**
  - `image`：輸入影像的 resource key（例如 `node_0.image`）
- **輸出資源**：
  - `{node_id}.binary_image`：`ImageResource`（二值化後的影像）

### 3) `cast_resource`（`node/plugins/random_id_4`）

- **用途**：將一個 resource 轉換為另一種類型的 resource（目前支援轉換為 `string.v1`）
- **execute() config**
  - `source`：來源 resource 的 key（例如 `node_0.some_resource`）
  - `name`：轉換後 resource 的名稱
  - `target_schema`：目標 resource 的 schema（例如 `string.v1`）
  - `cast_fn`：轉換函數的字串定義（使用 Python AST 解析，僅允許安全的語法）
- **輸出資源**：
  - `{node_id}.{name}`：轉換後的 resource（根據 `target_schema` 決定類型）

**範例**：
```json
{
  "id": "node_1",
  "name": "cast_resource",
  "version": "v1.0.0",
  "config": {
    "source": "node_0.some_resource",
    "name": "casted_string",
    "target_schema": "string.v1",
    "cast_fn": "def cast_fn(data: Any) -> str: return str(data)"
  }
}
```

> 注意：`cast_fn` 會經過 AST 檢查，僅允許安全的語法結構，不允許危險操作。

---

## 執行輸出（Debug）

每次呼叫 `/pipeline` 會在專案根目錄輸出：

- `resource_after_prepare.json`：所有 node `prepare()` 完成後的資源快照
- `resource_after_execute_node_0.json`、`resource_after_execute_node_1.json`...：
  - 每個 node `execute()` 完成後各自輸出的資源快照

此外，`EventEmitter.emit()` 會在 console 印出：

- `[emit] node_start_0 -> None`
- `[emit] node_start_1 -> None`

---

## BaseNode 生命週期

每個 node 實作 `BaseNode` 協議，包含以下方法：

- `__init__(ctx, config)`：初始化 node，接收 `BaseNodeContext` 與配置
- `prepare()`：準備階段，通常用於建立設計時資源（如列出可用裝置）
- `setup(config)`：設置階段，用於設定運行時配置（目前大部分 node 未實作）
- `execute()`：執行階段，執行 node 的主要邏輯
- `next()`：執行完成後，通知下一個 node 開始執行（透過 `event.emit("node_start_{next_index}")`）
- `dispose()`：清理階段，釋放資源（如關閉檔案、釋放記憶體）

## 備註

- 這是一個 demo，`ImageResource` 會根據 node 的 `id` 與 resource 的 `name` 產生檔名（例如 `node_0_image.jpg`），且直接呼叫本機 `http://localhost:8000`；**請勿直接用於正式環境**。
- node 的載入機制依賴 `manifest.json` 中的 `backend_entrypoint` 欄位，格式為 `{module_path}#{class_name}`（例如 `main.py#WebcamNode`）。