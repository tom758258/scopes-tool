# Generic Sequence Workflow v1

Generic Sequence v1 是 Core 擁有的有限工作流（finite workflow），用於按嚴格順序執行現有的示波器操作。CLI 為配接器（adapter）；Sequence 不透過 Worker 或 WebUI 對外公開。

## 文件規格

Sequence 文件採用嚴格的 JSON 格式：

```json
{
  "version": 1,
  "loop_count": 2,
  "steps": [
    {"action": "single", "parameters": {}},
    {"action": "wait-trigger", "parameters": {"timeout_seconds": 5}},
    {"action": "measure", "parameters": {"item": "vpp", "channel": 1}},
    {"action": "wait", "parameters": {"seconds": 1}}
  ]
}
```

`version` 必須為 JSON 整數 `1`。`loop_count` 預設為 `1`，且必須為正 JSON 整數。不接受 Boolean 作為整數。`steps` 必須為非空陣列。未知的文件、步驟或參數欄位會觸發 fail-closed，未知的 action 以及非標準 JSON 數字（如 `NaN` 和 `Infinity`）亦同。Public Core API 入口點（`plan_sequence()`、`run_sequence()`）會在進行硬體存取、建立檔案目錄或初始化 Manifest 前進行嚴格驗證與正規化。

## Actions

- `wait`：需要非負有限數字 `seconds`，並使用共享的視可中斷 host wait。
- `single`：不接受參數，啟動一次 single 擷取。
- `wait-trigger`：需要正有限數字 `timeout_seconds`，等待已啟動的擷取完成。它不會發送 `:SINGle` 或強制觸發。同步單次流程請按順序使用 `single` 接 `wait-trigger`。若在 trigger polling 期間觀察到 cancellation，會立即退出且不發送額外的系統錯誤查詢。
- `measure`：使用現有 `MeasureRequest` 欄位（`item`、`channel`、`source_channel`、`reference_channel`、`time_s`、`level`、`slope` 與 `occurrence`），並遵守其現有特定項目之規則。
- `capture`：需要 `channels`；`points` 預設為 `1000`，`waveform_format` 預設為 `byte`，`allow_time_axis_tolerance` 預設為 `false`。
- `screenshot`：擷取現有的跨系列 PNG 格式，並接受可選的 `black` 或 `white` `background`。Screenshot 的 dry-run 規劃僅列出保證查詢的靜態指令（`:HARDcopy:INKSaver?`、`:DISPlay:DATA? PNG, COLor`、`:SYSTem:ERRor?`），不宣稱條件式的運行階段背景寫入。
- `cleanup`：接受現有的 `minimal` 或 `safe` profile，並直接使用 Core Safe Cleanup。它不會擴大清理的安全邊界。

執行過程為有限、有序、單執行緒且 fail-fast。沒有條件判斷、變數、重試、平行或巢狀步驟、任意 SCPI、Shell 執行或自動清理。

## 執行與產出物（Artifacts）

完整文件會在建立執行目錄前針對偵測到的型號完成驗證。一次執行會寫入 `manifest.json` 與 `scpi.log`。Capture 與 screenshot 檔案使用確定性的 loop 與 step 路徑，例如：

```text
loop_0001/
  step_0004_capture/
    waveform.csv
    waveform_meta.json
  step_0005_screenshot.png
```

Manifest 使用獨立的 `schema_version: 1`，並儲存正規化後的輸入、已完成的執行紀錄、檔案列表、失敗細節與終端狀態。單次回傳結果保持受限，每個文件步驟回傳一個摘要；Manifest 則保存重複執行的歷史紀錄。若步驟在產出 artifact 或更新 Manifest 期間失敗，實際已存在之確定性檔案會保留於 partial results 中，但未完成之步驟不會算入 completed，亦不會觸發進度回調（progress callback）。

Cooperative cancellation 會在入口點、步驟執行前、已持久化成功步驟後、迴圈邊界以及 host 與 trigger polling wait 期間進行檢查。啟動前取消（Pre-start cancellation）完全不進行硬體 I/O，亦不建立執行目錄（`output_dir: null`、`manifest_path: null`、`scpi_log_path: null`）。已完成的步驟與產出物保持有效。若在所有有限工作完成後才觀察到停止請求，`completed` 優先於 cancellation；系統或步驟失敗則優先於 cancellation。Cooperative cancellation 回傳 `status: "cancelled"`、`error: null` 與離開碼 `130`。`KeyboardInterrupt` 保持獨立回傳 `status: "interrupted"`。除非文件執行至明確的 `cleanup` 步驟，否則 cancellation 絕不自動執行清理。

Reporter callback 為同步執行，並在完成的步驟紀錄持久化後發送。`WorkflowProgress.completed_count` 計算已完成的步驟執行次數，`total_count` 為 `loop_count * step_count`。

Sequence 的 `scpi.log` 在身分與功能 preflight 完成後開始紀錄。它是 Core 工作流的執行軌跡，並非完整的處理程序或 VISA session log。

## CLI

```powershell
scopes-tool sequence --simulate --file workflow.json --output-dir data\sequence-run
scopes-tool sequence --dry-run --json --file workflow.json
scopes-tool sequence --resource "$env:SCOPES_TOOL_RESOURCE" --file workflow.json
```

Dry-run 載入並驗證完整文件，不開啟 VISA 資源，也不寫入任何執行階段產出物。在現有 operation planner 可安全提供的情況下，它會回報正規化後的步驟、迴圈與執行計數、產出物路徑範本以及受限的單次 SCPI 規劃。
