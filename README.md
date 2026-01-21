# Edge Pipeline Example（Orchestrator Runtime）

這是一個**簡化版的邊緣管線（Edge Pipeline）編排器示範**：透過 `FastAPI` 提供 API，動態載入 `node/plugins/` 下的節點（node），並使用事件機制把多個 node 串成一條 pipeline 逐一執行。每個 node 執行後會把輸出寫入 `ResourceManager`，並可被後續 node 取用。

---

## 專案結構

- `main.py`
  - `FastAPI` 服務入口
  - API：`/pipeline`、`/file`、`/file/{file_name}`、`/ws`
  - pipeline 執行方式：在背景 thread 中用 `EventEmitter` 送出開始事件，node 完成後通知下一個 node
- `event_emitter.py`
  - 簡單事件系統：`on(event, handler)`、`emit(event, data=None)`
- `node/`
  - `base.py`：`BaseNodeContext`（包含 `resource`、`file_store`、`event`）
  - `manager.py`：`NodeManager`（registry）
  - `plugins/`
    - `random_id_1/`：`WebcamNode`（webcam 取像）
    - `random_id_2/`：`BinarizationNode`（影像二值化）
- `aiwin_resource/`
  - `manager.py`：`ResourceManager`（set/get/serialize）
  - `plugins/image/v1/main.py`：`ImageResource`（demo：把影像存成 `demo.jpg` 並上傳到 `/file`，序列化時回傳可下載的 URL）
- `store/file.py`
  - `FileStore`：透過 HTTP 呼叫本服務的 `/file` 與 `/file/{file_name}` 做上傳/下載
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
- `name`：node 名稱（目前內建：`webcam`、`binarization`）
- `version`：版本字串（此 demo 不強制使用）
- `config`：node 的參數

> 注意：node 間串接使用事件 `node_start_{index}`；下一個 index 由 runtime 在背景執行緒內自動注入到 node config（key：`_next_node_index`）。

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

- `key = "<id>.<resource_name>"`

因此 `WebcamNode` 產生的影像資源（`ImageResource` name=`image`）key 會是：

- `node_0.image`

`BinarizationNode` 的 `config.image` 需要填入上一個 node 的影像 resource key。

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

### `GET /ws`（WebSocket）

簡單聊天室/廣播示範（與 pipeline 無直接關聯）。

---

## 內建 Nodes（Plugins）

### 1) `webcam`（`node/plugins/random_id_1`）

- **用途**：擷取攝影機影像並產生 `ImageResource(name="image")`
- **prepare()**：列出可用攝影機索引，寫入 `UsbDevicesResource(name="usb_devices")`
- **execute() config**
  - `device_id`：OpenCV `VideoCapture` 的裝置索引（例如 0）

> macOS 若讀不到鏡頭，請確認系統隱私權（Camera）已允許終端機/IDE 使用。

### 2) `binarization`（`node/plugins/random_id_2`）

- **用途**：把輸入影像轉灰階後做二值化，輸出 `ImageResource(name="binary_image")`
- **execute() config**
  - `image`：輸入影像的 resource key（例如 `node_0.image`）

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

## 備註

- 這是一個 demo，`ImageResource` 目前固定上傳成 `demo.jpg`（會覆蓋同名檔案），且直接呼叫本機 `http://localhost:8000`；**請勿直接用於正式環境**。