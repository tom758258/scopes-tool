# Generic Sequence Workflow v1

Generic Sequence v1 是由 Core 擁有的有限 workflow，依嚴格順序執行既有
示波器操作。CLI 只是 adapter；本階段不透過 Worker 或 WebUI 暴露 Sequence。

## 文件格式

Sequence 文件使用 strict JSON：

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

`version` 必須是真正的 JSON integer `1`。`loop_count` 預設為 `1`，且必須
是正整數；boolean 不視為 integer。`steps` 不可為空。未知的文件、step 或
parameter 欄位、未知 action，以及 `NaN`、`Infinity` 等非標準 JSON 數值都會
fail closed。

## Actions

- `wait`：需要非負有限 `seconds`，使用共用的可中斷 host wait。
- `single`：不接受參數，啟動一次 single acquisition。
- `wait-trigger`：需要正值且有限的 `timeout_seconds`，只等待已經啟動的
  acquisition；不送出 `:SINGle`，也不 force trigger。同步 single-shot 流程應
  明確使用 `single` 後接 `wait-trigger`。
- `measure`：沿用既有 `MeasureRequest` 的 `item`、`channel`、
  `source_channel`、`reference_channel`、`time_s`、`level`、`slope` 與
  `occurrence`，並套用原有 measurement-specific 規則。
- `capture`：需要 `channels`；`points` 預設為 `1000`、`waveform_format`
  預設為 `byte`、`allow_time_axis_tolerance` 預設為 `false`。
- `screenshot`：使用既有跨系列 PNG capture，可選 `black` 或 `white`
  `background`。
- `cleanup`：接受既有 `minimal` 或 `safe` profile，直接使用 Core Safe
  Cleanup，不擴張 cleanup 安全邊界。

執行語意是有限、有序、單執行緒且 fail-fast。不支援 condition、variable、
retry、parallel、nested step、arbitrary SCPI、shell execution 或自動 cleanup。

## 執行與 artifacts

整份文件會先依 detected model 完成驗證，之後才建立 run directory。每次 run
都寫出 `manifest.json` 與 `scpi.log`。Capture 與 screenshot 使用可預測且不衝突
的 loop/step 路徑，例如：

```text
loop_0001/
  step_0004_capture/
    waveform.csv
    waveform_meta.json
  step_0005_screenshot.png
```

Manifest 使用獨立的 `schema_version: 1`，保存 normalized input、完成的 execution
records、files、failure details 與 terminal status。One-shot result 每個文件 step
只保留一筆 bounded summary；重複 execution history 放在 manifest。

Cooperative cancellation 會在 step 前、成功 step persisted 後、loop boundary，
以及 host/trigger polling wait 中檢查。已完成 step 與 artifacts 保持有效。所有
有限工作完成後才觀察到 stop request 時，`completed` 優先；system 或 step
failure 則優先於 cancellation。合作式取消回傳 `status: "cancelled"`、
`error: null` 與 exit code `130`。`KeyboardInterrupt` 使用
`status: "interrupted"`，維持可區分。除非文件實際執行到明確的 `cleanup`
step，cancellation 不會執行 cleanup。

Reporter callback 為同步呼叫，且在完成 step record persisted 後才執行。
`WorkflowProgress.completed_count` 計算已完成的 step executions，`total_count`
為 `loop_count * step_count`。

Sequence `scpi.log` 從 identity/capability preflight 完成後開始，代表 Core workflow
execution trace，不是完整 process 或 VISA session log。

## CLI

```powershell
scopes-tool sequence --simulate --file workflow.json --output-dir data\sequence-run
scopes-tool sequence --dry-run --json --file workflow.json
scopes-tool sequence --resource "$env:SCOPES_TOOL_RESOURCE" --file workflow.json
```

Dry-run 會載入並驗證整份文件，不開啟 VISA resource，也不寫出 runtime
artifacts。輸出包含 normalized steps、loop/execution counts、artifact path
templates，以及既有 operation planner 能安全提供的 bounded one-pass SCPI plan。
