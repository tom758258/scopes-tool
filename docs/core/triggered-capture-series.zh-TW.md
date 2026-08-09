# Triggered Capture Series v1（觸發擷取序列）

## 目的

Triggered Capture Series 是固定用途、有限次數的 Core waveform workflow，
在示波器自然完成觸發與擷取後讀取波形。它使用示波器目前既有的觸發設定，
不設定、取代、還原或強制觸發。

公開對應關係如下：

```text
Triggered Capture Series
  -> CLI / Worker command: triggered-capture-series
  -> Core request: TriggeredCaptureSeriesRequest
  -> Core planner: plan_triggered_capture_series()
  -> Core runner: run_triggered_capture_series()
```

## Request 與 CLI 欄位

Core request 欄位為 `channels`、`points`、`waveform_format`、`count`、
`trigger_timeout_seconds`、`interval_seconds`、`output_dir` 與 `log_scpi`。
CLI 使用 `--channel`、`--points`、`--format`、`--count`、
`--trigger-timeout-seconds`、`--interval-seconds`、`--output-dir`，以及共用的
`--log-scpi` 選項。

Channel 為必填，沿用既有 waveform capture 語意，包括可重複指定的有序
channel 與單獨使用的 `all`。Points 預設為 `1000`，format 預設為 BYTE。
Count 必須是正整數。Trigger timeout 必填、必須為有限正數，且每個 cycle
各自套用。Interval 預設為零，且必須是有限非負數。

## 執行順序

每個 cycle 依序執行：

```text
檢查 cancellation
-> :SINGle
-> 等待目前 trigger/acquisition 完成
-> 擷取指定 channel 的 waveform
-> 寫入 waveform CSV 與 metadata
-> 查詢 :SYSTem:ERRor?
-> 將 cycle 提交到 manifest.json
-> 回報 sample 與 progress
-> 視需要等待 interval_seconds
```

Trigger wait 沿用 Triggered Measurement Loop 的 current-acquisition
Operation Status Condition classifier 與 cooperative polling 路徑，不重試，
也不送出 `:TRIGger:FORCe`。Waveform 擷取、BYTE/WORD scaling、多 channel
對齊與檔案寫入沿用既有 capture implementation。

`interval_seconds` 是 persistence 與 reporting 完成後才開始的相對等待，
不是 absolute wall-clock cadence。

## Persistence 與完成邊界

只有在自然完成觸發、waveform capture 成功、CSV 與 metadata 寫入成功、
capture 後的 system-error check 成功，而且 manifest 更新成功後，cycle 才會
增加 `completed_count`。Sample 與 progress reporter 只在此提交完成後執行。

若 system-error check 回報 instrument error，已寫入的 waveform 檔案可保留
作為診斷，但失敗 cycle 不會加入 `cycles`，也不會增加 `completed_count`。
後續 cancellation、timeout、interruption、transport、query、persistence 或
instrument error 都不會破壞先前已提交的 cycles。

## Cancellation 與錯誤

Cancellation 會在 cycle 開始前、trigger polling 期間、cycle 提交後與
interval wait 期間合作式檢查。Trigger wait 期間取消時不會擷取該 cycle。
Blocking VISA 或 device read 不會被強制中斷。若最後一個 requested cycle
已提交，之後才觀察到的 stop 不會把 `completed` 改成 `cancelled`。

Trigger timeout 會回傳 `error`，記錄 cycle index 與 trigger wait elapsed，
並在不重試、不 force trigger、不開始下一個 cycle 的情況下停止。Instrument
system error 回傳 `instrument_error`，其他 runtime failure 回傳 `error`，
`KeyboardInterrupt` 回傳 `interrupted`。已完成的 artifacts 會保留。

## Artifacts

Direct CLI 預設使用 `data/triggered_capture_series/<timestamp>/`。單一 run
directory 包含：

```text
waveform_0001.csv
waveform_0001_meta.json
waveform_0002.csv
waveform_0002_meta.json
...
manifest.json
scpi.log
```

Manifest 記錄 request、session identity、status、completed count、相對路徑
files、已提交 cycle 的 compact entries 與 terminal error。每個已提交 cycle
至少記錄 index、trigger elapsed、CSV 與 metadata 路徑、actual points 與
system-error result。Raw waveform samples 保留在 CSV，不複製到 manifest。

## Dry-Run、Simulator 與 Worker

Dry-run 會驗證指定 model profile 與 request，但不開啟 VISA，也不寫入
artifacts。它回報有限 requested count 與一個代表 cycle：`:SINGle`、一次
Operation Status Condition query、waveform capture SCPI 與一次
`:SYSTem:ERRor?`。不會靜態重複展開 polling 或 cycles。

Simulator mode 會執行完整有限 workflow 並產生正常 artifacts。Common v2
Worker 只接受 `channel`、`points`、`format`、`count`、
`trigger_timeout_seconds` 與 `interval_seconds`。Worker 會拒絕 caller 提供的
`output_dir` 與 `log_scpi`，並注入 Worker 擁有的 job artifact directory。

## v1 明確不做

Triggered Capture Series v1 不加入 trigger configuration 或 restore、force
trigger、retry、duration 或 infinite execution、absolute scheduling、
measurement、condition、cleanup、screenshot、plot、segmented capture、
instrument-side Save/Export、Generic Sequence action、WebUI runtime、額外
hardware support 或新的 workflow engine。
