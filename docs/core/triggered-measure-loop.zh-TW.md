# 觸發量測迴圈 v1

觸發量測迴圈是用途固定且次數有限的 Core 工作流程。每個 cycle 會啟動
`Single`，透過既有的 Operation Status Condition Run-bit 路徑等待目前擷取
完成，查詢所選量測，保存已完成的 cycle，並可在開始下一個 cycle 前等待
指定間隔。它使用示波器上已設定的觸發狀態，不會另外設定觸發。

request 欄位為 `channels`、`items`、`pairs`、`pair_items`、`count`、
`trigger_timeout_seconds`、`interval_seconds` 與 `output_dir`，另沿用既有的
`log_scpi` 執行選項。`count` 與 `trigger_timeout_seconds` 必填；count 至少為
一，觸發逾時必須是正值有限數，interval 預設為零且必須是非負有限數。
量測選擇與預設值和 `measure-log` 相同：未指定 channel 時使用既有預設
channel 集合，items 預設為 `vpp,frequency`，pairs 預設為空，pair items
預設為 `phase,delay`。

每個完成的 cycle 都會先寫入一列 CSV 並更新 `manifest.json`，之後才呼叫
sample 與 progress reporter。interval 從這個保存與回報邊界之後才開始。
`WorkflowProgress.total_count` 等於要求的 count。正常量測回應中的無效值或
sentinel 會保存為 `NaN`，不會讓 cycle 失敗；query、transport、parsing 或
儀器 system error 則立即失敗。

觸發逾時會讓工作流程失敗，不會強制觸發、重試或開始下一個 cycle。取消
採合作式方式在安全邊界處理，不會強制中斷 VISA read。逾時、失敗、取消或
中斷時，先前完成的 cycle 都會保留且仍有效。

執行期使用單一目錄，預設為
`data/triggered_measure_loops/<timestamp>/`，其中包含：

- `measurements.csv`：包含 `index`、`timestamp_iso`、`elapsed_seconds`、
  `trigger_elapsed_seconds`，以及 `ch1_vpp`、`ch1_ch2_phase` 等量測欄位；
- `manifest.json`：包含 request、已完成 cycle 摘要、檔案，以及適用時的
  精簡終止錯誤；
- `scpi.log`：記錄 Core 工作流程內送出的 SCPI。

dry-run 會驗證 request 與所選 model profile，不開啟 VISA，也不寫入執行期
artifact。它會回報有限的要求次數及一個代表性 cycle：`:SINGle`、
`:OPERegister:CONDition?`、所選量測 query，以及一次 `:SYSTem:ERRor?`。

此工作流程不設定觸發、不擷取 waveform 或 screenshot、不執行 cleanup、
不強制觸發、不重試，也不擴張 Generic Sequence v1。
