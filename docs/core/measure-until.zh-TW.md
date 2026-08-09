# Measure Until Condition v1

## 用途

Measure Until Condition 是一個 fixed-purpose、finite、read-only 的量測
workflow。它會重複查詢一個既有的單 channel 量測，直到數值條件成立，或
workflow timeout 到期。

```text
產品名稱：Measure Until Condition
CLI / Worker command：measure-until
Core request：MeasureUntilRequest
Core planner：plan_measure_until()
Core runner：run_measure_until()
```

此 workflow 只觀察示波器目前的 acquisition state，不會設定、啟動、停止、
強制或等待 trigger。

## Request

| 欄位 | 規則 |
|---|---|
| `channel` | 必填且只能是一個 analog channel。不支援 `all`、array、digital channel 或 aggregation。 |
| `item` | 必填，限既有的非參數化單 channel measurement item。拒絕 pair 與 parameterized items。 |
| `operator` | 必填，只接受 `gt`、`gte`、`lt`、`lte`。 |
| `threshold` | 必填有限數值，單位沿用所選 measurement 的 native unit。 |
| `timeout_seconds` | 必填正有限數值，是 workflow 的有限 timeout。 |
| `interval_seconds` | 選填非負有限數值，預設 `1.0`。 |
| `output_dir` | 僅 direct CLI 可指定；預設 `data/measure_until/<timestamp>/`。 |
| `log_scpi` | Direct CLI 執行選項，沿用既有 workflow SCPI log 行為。 |

四個 operator 分別代表 `value > threshold`、`value >= threshold`、
`value < threshold` 與 `value <= threshold`。v1 不做單位轉換。

## 執行與 timeout 邊界

每次 iteration 的順序是：

```text
檢查 cancellation
-> 檢查 timeout
-> 查詢 measurement
-> 查詢 :SYSTem:ERRor?
-> 判斷條件
-> 保存 CSV row
-> 更新 manifest
-> 回報 sample 與 progress
-> matched 時完成，否則等待 interval_seconds
```

Timeout 決定是否可以開始下一次 measurement query。已在 deadline 前開始的
blocking VISA/device read 不會被強制中斷；回傳後仍會完成 system-error
檢查、comparison 與 persistence。即使 read 期間超過 deadline，已 commit
的 matching sample 仍成功完成；已 commit 的 non-matching sample 則在下一個
安全邊界回傳 `condition_timeout`。Interval wait 最長只等到剩餘 timeout。

`interval_seconds` 是前一筆 sample 與 manifest 完成 persistence、reporters
執行後的相對等待時間，不是 absolute cadence。

## Persistence 與終止行為

只有 CSV row 與更新後的 manifest 都成功保存，該 sample 才會增加
`completed_count`。Sample 與 progress reporters 只在 commit 後執行；後續
失敗不會破壞先前已 commit 的 samples。若 manifest 寫入失敗，先前寫出的
CSV diagnostic row 可以保留，但不算 completed。

有效且符合條件的 sample 會回傳 `status: "completed"`、`matched: true`、
`termination_reason: "condition_met"` 與 exit code `0`。Compact
`matched_sample` 保存 index、value 與 elapsed time。只有在該 commit 後才觀察
到的 cancellation 不會取代 completed result。

有限 timeout 內未符合條件時，workflow 回傳 `status: "error"`、
`matched: false`、`termination_reason: "condition_timeout"`、exit code `1`，
以及 type 為 `condition_timeout` 的 compact error。Cancellation、interruption、
transport、query、parsing、persistence 與 instrument system error 繼續沿用
既有 workflow status/error contract。

正常的 invalid measurement sentinel 會保存為 `NaN`、視為 non-match 並繼續；
真正的 measurement parsing、query、transport、persistence 或 instrument
system error 會立即停止。

## Artifacts

```text
data/measure_until/<timestamp>/
  measurements.csv
  manifest.json
  scpi.log
```

CSV 欄位為：

```text
index,timestamp_iso,elapsed_seconds,value,matched
```

Schema 1 manifest 保存固定 request、runtime identity、compact completion 與
matching summary、terminal state、artifact paths 及 error，不會複製完整 sample
series；measurement values 保留在 CSV。

## Dry-run、Simulator 與 Worker

Dry-run 會驗證所選 model profile 與 request，不開啟 VISA、也不寫 artifacts。
它會回報有限 timeout 與 interval，只顯示一個代表性 iteration：所選
measurement query 與一次 `:SYSTem:ERRor?`，不展開 runtime polling。

Simulator mode 會執行實際的有限 Core workflow 並建立正常 artifacts。Common
v2 Worker 只接受 `channel`、`item`、`operator`、`threshold`、
`timeout_seconds` 與選填的 `interval_seconds`。Worker 會拒絕 `output_dir` 與
`log_scpi`，並注入自己擁有的 job artifact directory。Core completed 對應
Worker succeeded，Core cancelled 對應 Worker cancelled，timeout 或其他 Core
failure 對應 Worker failed。

## v1 non-goals

v1 不支援 multiple channels 或 conditions、AND/OR aggregation、pair 或
parameterized measurements、equality/tolerance/hysteresis/debounce、retry、
trigger 或 acquisition control、waveform capture、screenshots、match 後 actions、
Generic Sequence integration、nested workflows、count 或 infinite execution、
absolute scheduling、cron、plots、WebUI runtime 或新硬體支援。
