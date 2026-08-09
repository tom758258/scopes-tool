# Periodic Capture v1（週期擷取）

## 用途與對應關係

Periodic Capture 是既有固定用途、有限次數、時間驅動 waveform capture
workflow 的產品層名稱，不會新增另一套 runtime surface：

```text
Periodic Capture
  -> CLI / Worker command: capture-batch
  -> Core request: CaptureBatchRequest
  -> Core operation: run_capture_batch()
```

本 workflow 沒有 `periodic-capture` command、alias、request type、Core runner
或第二套 capture loop。

## Request 欄位

既有 machine-facing 欄位與 normalized Core request 的對應如下：

| CLI / Worker 欄位 | Core 欄位 | 可用範圍 |
| --- | --- | --- |
| `channel` | `channels` | CLI 與 Worker |
| `points` | `points` | CLI 與 Worker |
| `format` | `waveform_format` | CLI 與 Worker |
| `count` | `requested_count` | CLI 與 Worker |
| `interval_seconds` | `interval_seconds` | CLI 與 Worker |
| `output_dir` | `output_dir` | 僅 direct CLI；Worker 會注入自己的 job directory |
| `log_scpi` | `log_scpi` | 僅 direct CLI |

`count` 是必要的正整數。`interval_seconds` 預設為零，且必須是有限的非負
數值。Channel、points 與 BYTE／WORD format 繼續依既有 model capability
驗證。

## 執行與時間語意

每次 iteration 會擷取指定 waveform、寫入 CSV 與 metadata、將 capture 後的
system error 結果記錄到 `manifest.json`，再呼叫選用的 sample 與 progress
reporter。下一段 interval 只會在這個 persistence／reporting boundary 完成後
開始。

`interval_seconds` 是相對等待時間：從前一次 capture 完成 persistence 與
reporting，到下一次 capture 開始。它不是 absolute wall-clock cadence。
數值為零時，通過前一次 boundary 後立即開始下一次。除非先發生失敗或取消，
workflow 會在完成 `count` 次後結束。

## 取消與錯誤

取消採 cooperative 模式。Core 會在 capture 前、完成 persistence／reporting
後，以及 interval wait 期間檢查取消；不會強制中斷 blocking VISA 或 device
read。已完成的 capture 與 artifacts 會保留。若 stop request 只在最後一次
capture 完成後才出現，不會將 `completed` 改成 `cancelled`；terminal
precedence 維持 `instrument_error > completed > cancelled`。

Capture 後的 instrument system error 會記錄於該筆 capture，並停止剩餘工作。
Transport、query、write 或 persistence error 沿用既有 `capture-batch` contract，
並在可行時保留已寫入的 artifacts。Periodic Capture 不會 retry。

## Artifacts

既有 `capture-batch` artifact layout 完全不變：

```text
waveform_0001.csv
waveform_0001_meta.json
waveform_0002.csv
waveform_0002_meta.json
...
manifest.json
scpi.log
```

Direct CLI 可以指定 `output_dir`。Worker job 一律使用 Worker 擁有的 job
artifact directory，不接受 caller 提供的 `output_dir` 或 `log_scpi` argument。
`scpi.log` 一律建立；direct CLI 的 `--log-scpi` 另會將 workflow SCPI log
輸出到 stderr。

## Dry-Run 與 Simulator

Direct CLI dry-run 會驗證指定 model 與 request，不開啟 VISA，也不寫入
artifacts。結果包含一次代表性 waveform capture transaction，以及有限次數的
所有預計 artifact paths。Simulator mode 會透過 hardware-free simulator 執行
完整的有限 workflow，並寫入正常 artifacts。

## v1 Non-Goals

Periodic Capture v1 不加入 duration 或無限執行、trigger／wait-trigger、
screenshot、measurement、retry、condition、cleanup、state restore、absolute
scheduling、cron、plot、nested workflow、Generic Sequence action 或 WebUI
runtime。Triggered waveform behavior 不屬於本 workflow。
