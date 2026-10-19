# 型號實作備註

本文件供維護者使用，不隨離線 HELP 發佈。型號、連線、功能及安全限制以
[支援型號](supported-models.zh-TW.md)為準；本文不擴大正式支援範圍。

<a id="canonical-physical-model-identity"></a>

## 標準實體型號身分

Scopes Tool 為已註冊的 Keysight InfiniiVision 與 Tektronix 型號提供廠商中立的
Product API。標準實體型號 Registry 包含：

| 標準實體 Model ID | 製造商 | Model | Series | Capability Profile ID | Driver ID |
| --- | --- | --- | --- | --- | --- |
| `keysight-dsox2004a` | Keysight Technologies | DSOX2004A | 2000X | `keysight-infiniivision-2000x` | `keysight-infiniivision` |
| `keysight-dsox3024a` | Keysight Technologies | DSOX3024A | 3000X | `keysight-infiniivision-3000x` | `keysight-infiniivision` |
| `keysight-dsox4024a` | Keysight Technologies | DSOX4024A | 4000X | `keysight-infiniivision-4000x` | `keysight-infiniivision` |
| `keysight-dsox4034a` | Keysight Technologies | DSOX4034A | 4000X | `keysight-infiniivision-4000x` | `keysight-infiniivision` |
| `tektronix-tbs2074` | Tektronix | TBS2074 | TBS2000 | `tektronix-tbs2074` | `tektronix` |
| `tektronix-tds2024b` | Tektronix | TDS2024B | TDS2000B | `tektronix-tds2024b` | `tektronix` |
| `tektronix-tbs1052b` | Tektronix | TBS1052B | TBS1000B | `tektronix-tbs1052b` | `tektronix` |

標準註冊識別實體型號；每個已註冊型號明確選擇其 Runtime Capability Profile。

每個已註冊實體型號都有無硬體的一致性檢查，涵蓋廠商身分、能力查找與驅動選擇。
啟用模擬器的型號亦使用模擬器身分解析。

Core 依各實體型號註冊的 Driver ID 明確選擇驅動。已註冊的 Runtime Driver 為
`keysight-infiniivision` 與 `tektronix`。Live 選擇依偵測 `*IDN?` 解析出的標準實體型號，
規劃與預期身分不得覆蓋。未知廠商、實體型號，以及缺少或未註冊的 Driver ID 一律拒絕。

<a id="contributor-validation-and-diagnostics"></a>

### 貢獻者驗證與診斷

下列 `@py` USB 連線僅限受控的 CLI Validation Mode，未開放 Product Live：
`keysight-dsox2004a`、`keysight-dsox3024a`、`keysight-dsox4024a`、
`keysight-dsox4034a`、`tektronix-tbs1052b`。
Validation Mode 也允許三個已開放的 `@py` TCPIP 組合，但絕不覆蓋偵測型號、能力或安全要求。
WebUI 與 Worker 不可啟用此模式。`identify` 與 `list-resources` 是連線診斷，並非 Product 授權。

直接呼叫 Python `Oscilloscope.open()` 仍是低階 Session 介面，而非 Product 政策入口。
Product CLI 與 Core 執行路徑在改變儀器的操作前執行此矩陣限制。

<a id="runtime-profiles"></a>

## Runtime Profile

Core 將 Live `*IDN?` 的廠商與型號欄位解析為標準實體 Model ID，再使用註冊的
Capability Profile ID。Dry-run 的 `--model` 使用標準實體 Model ID。
已註冊的 Keysight 與 Tektronix 型號皆可模擬；模擬器的廠商／型號 IDN 欄位與能力
來自相同 Registry 項目。

| Profile ID | Series | 註冊型號 | 類比 Channel |
| --- | --- | ---: | --- |
| `keysight-infiniivision-2000x` | 2000X | DSOX2004A | 4 |
| `keysight-infiniivision-3000x` | 3000X | DSOX3024A | 4 |
| `keysight-infiniivision-4000x` | 4000X | DSOX4024A, DSOX4034A | 4 |
| `tektronix-tbs2074` | TBS2000 | TBS2074 | 4 |
| `tektronix-tds2024b` | TDS2000B | TDS2024B | 4 |
| `tektronix-tbs1052b` | TBS1000B | TBS1052B | 2 |

僅與 DSO-X 或 MSO-X 系列相似的型號字串不足以選擇能力。
未註冊名稱如 `DSOX4054A`，以及原始型號如 `DSOX4024A`，皆不可作為 `--model` 值。

Live 執行的能力只來自實際 `*IDN?` 廠商與型號解析的標準實體身分，規劃身分不可覆蓋。
Live Worker 將 `--model` 視為預期標準實體 Model ID；若與偵測身分不符，
在命令專屬 SCPI 前即失敗。

## Capability 實作備註

Core 擴充邊界請見[新增型號](adding-a-model.md)。Tektronix Dry-run 與有狀態模擬器
對允許的操作使用 Tektronix 命令語法，但模擬不代表實機支援。
這些 Profile 不提供訊號 Preset 或 System Error Queue 注入。

<a id="aggregate-projections"></a>

### 彙總投影

彙總跳過不支援的原子查詢，絕不只為探索支援就改變 Source/Display、Measurement Slot、
Trigger Mode 或 Cursor Units。

| 彙總 | TBS2074 投影 | TDS2024B 投影 | TBS1052B 投影 |
| --- | --- | --- | --- |
| `channel-summary` | CH1–CH4 的 display、scale、offset、coupling、probe ratio、bandwidth limit、invert、label、probe skew、V/A units；range、impedance、vernier 不可用。 | display、scale、offset、coupling、probe ratio、bandwidth limit、invert、units；label、probe skew、range、impedance、vernier 不可用。 | 同 TDS2024B，僅 CH1/CH2。 |
| `live-data-snapshot` / `query_instrument_summary` | CH1–CH4 的 display/scale/offset/units、同上述 Delay Mode ON 前提的 timebase scale/position、trigger type/sweep、edge source/slope、依通道 Level 與已確認來源單位。 | 通道 display/scale/offset/units、timebase scale/position、trigger type/sweep/source/slope；目前類比 Edge Source 的 MAIN:LEVEL 可作 Snapshot 資料，即使獨立指定通道 Level 不支援。 | 同 TDS2024B，限兩通道。 |
| `system-information-snapshot` / `query_acquisition_readouts` | Identity、sample rate、acquisition points、record length 可用：SUPPORTED。 | Identity、acquisition points、record length 可用；sample rate 不可用：PARTIAL AGGREGATE。 | 同 TDS2024B：PARTIAL AGGREGATE。 |
| `cursor-query` | 僅時間來源的 Time 回讀投影原生 X 位置／差值；只有確認實體伏特的 SCREEN 回讀投影 Y 位置／差值。歧義軸為 null。百分比／Hz／dB／格／安培不是秒／伏特。非啟用或未確認軸與 dydx 不可用。 | 啟用 VBARS 的秒位置／差值，或啟用 HBARS 的伏特位置／差值；另一軸／dydx 與 FFT／amp／未知單位欄位不可用。 | 同 TDS2024B。 |

三者的 `live-data-snapshot` 均為 PARTIAL AGGREGATE。每個註冊 Profile 明確宣告固定
Realtime 擷取架構，不能僅從不支援 Segmented Memory 推論。
擷取處理類型仍另以 `ACQuire:MODe` 回讀。未知欄位各自回退；Line 或 External 的
Source-channel/Units/Analog-level 保持不可用，不填入虛構值。

Cursor OFF 投影 null 位置／差值／dydx。TBS2074 使用 `CURSor:FUNCtion` 選擇第一代五值：
`OFF`、`SCREEN`、`WAVEform`、`VBArs`、`HBArs`。操作者可明確要求 Function；
未明確指定時保留依軸對應：僅 X 用 VBArs，僅 Y 用 HBArs，X 加 Y 用 SCREEN。
`OFF` 與 `WAVEform` 只切換功能，不要求來源通道或位置；此介面的 `WAVEform` 無位置 Setter。
`VBArs` 只接受 X，`HBArs` 只接受 Y，其餘組合在儀器寫入前拒絕。
`CURSor:FUNCtion?` 在 WAVEform 或 VBArs 後可回傳 `TIME`，在 SCREEN 或 HBArs 後可回傳
`SCREEN`。Query 回報原生值，不能由此確認的軸為 null；Configure 結果保留要求的 Function。
不支援 `AMPLitude`。

TBS2074 Setter 使用所選／顯示波形語義；來源選擇可啟用顯示並重設擷取，刻意不還原，
否則會將游標改指其他來源。CH3/CH4 實體伏特 Y 驗證暫用波形傳輸來源檢查單位，
在 `finally` 還原傳輸來源。B1 Setter 僅 X-only 時間或 Y-only 實體伏特，
不支援混合軸或 auto-vertical。所有位置結果來自實際回讀，而非回傳輸入。
Source/Units 規則依 TBS2000 第 64、67–73、77、161、191–201 頁及 B1 第 2-61 至 2-68 頁。

`measure-results` 刻意不納入 Nullable 投影。`MEASUrement?` 與逐槽位彙總查詢描述設定，
不是公開 Result/Raw 契約要求的單一原生結果回應。Doctor 重用允許投影；Reference Label
如上維持 Nullable。Hardcopy State 或 DVM/WGEN/Demo Query 等必要狀態結果，
不會僅因外層允許 null 就變成部分彙總。

<a id="tek-post-command-status-boundary"></a>

### Tek 命令後狀態邊界

使用透明命令後狀態介面的普通 Tek 操作，會在業務回應完成後執行一次內部 `*ESR?`。
只有 SESR 位元 5–2（CME、EXE、DDE、QYE）屬於操作錯誤；
單獨 PON、URQ、RQC、OPC 不表示失敗。

一般非量測後檢查不執行 `EVENT?`、`EVMsg?`、`ALLEv?`、`EVQty?`，不模擬正規化
System Error Queue，也不填入頂層 `system_error`。非零 Error Mask 使用既有結構化錯誤路徑，
保留 Raw SESR。因 `*ESR?` 為消耗式讀取，`system-standard-event` 恰好只讀要求的一次；
`system-clear-status`、`system-status-byte`、`system-opc` 不額外隱含讀取 SESR。
後檢查不是完成等待，也不會讓不支援操作變成支援。`capture` 原子操作使用此介面；
`measure` 與組合流程使用下方原生工作流程檢查點，不再重複讀取原子 SESR。

<a id="native-workflow-status"></a>

### 原生工作流程狀態

工作流程檢查點先讀 `DESE?`，要求啟用 Error Bits 2–5，再讀一次 `*ESR?`，
並在下次 SESR 讀取前消耗 `ALLEv?`。不改 DESE、ESE、SRE。
順序遵循手冊的消耗式 SESR/Event Cohort：後續 SESR 讀取可能丟棄前一批尚未讀取事件。
見 TBS2000 第 206–209 頁及 B1 第 3 章。

工作流程結果保留 `system_error: null`，以 `post_command_status` 呈現
`tektronix-sesr` 來源、原始 SESR／事件回應、解碼事件／類別、完整性與消耗式讀取旗標。
Sample 與 Sequence／Acquisition Step 使用相同表示法。Command、Execution、Device、Query
Error Bits 會使檢查點失敗；僅資訊事件不會。設有 Error Bit 的警告，除下方量測例外外仍失敗。
格式錯誤、Queue Overflow（350）及不完整狀態一律拒絕並阻止後續流程步驟。
不可透過重試讀第二次 SESR 隱藏未讀或格式錯誤的事件批次。

Immediate Measurement 只有在值有效且有限、SESR 除 Execution Bit 4 外無其他錯誤位元，
且事件批次完整、僅含帶訊息的 540–549 量測警告時，才允許這些事件。
值、Raw SESR、事件碼與警告訊息保留在既有量測狀態欄位。
TYPE/SOURCE 與單位設定後的嚴格檢查點將先前工作與值查詢分開；還原另做嚴格檢查。
規則適用於 measure、sweep、log、until、觸發量測迴圈、Sequence 量測步驟及 Smoke 量測。
無效值、其他事件、混合錯誤及通訊失敗仍失敗。Tektronix Smoke 遇無效量測 Sentinel 也失敗；
Keysight Smoke 將此列為警告的政策不變。Capture、Acquisition、Trigger、Cleanup
檢查點保留其錯誤規則。

Doctor 遇既存錯誤停止；其他流程依既有前置政策回報舊事件後繼續，不完整前置檢查一定失敗。
Cleanup 在明確要求下清除狀態，再驗證完成與原生狀態。
公開 `check-error`、`query_system_error`、`drain_system_errors`、
`system-operation-status` 仍不支援。

`wait_for_current_trigger_completion` 觀察目前擷取，絕不 Arm；`single_wait` Arm 一次後
委派等待。Triggered Workflow 組合一次 `single` 與目前擷取等待；
Sequence `wait-trigger` 也不會默默再執行一次 `single`。

<a id="manual-ambiguities-and-excluded-interpretations"></a>

### 手冊歧義與排除的解讀

保留下列參考，避免歧義錯誤擴張支援：

- TDS2000B/TBS1000B 手冊第 2-98 頁將 BMP 列入 TBS1000B `HARDCopy:FORMat` 語法並適用
  USB-file/USBTMC；第 2-99 頁卻稱 BMP 非 TBS1000B。因此 TBS1052B BMP 截圖仍不支援，
  需權威釐清。另一方面，第 2-98 至 2-99 頁明確記載 TBS1000B JPEG，
  第 2-96 至 2-102 頁記載 `HARDCopy START` 與 USB Device Port 路由，
  因此支援獨立 JPEG 路徑但不開放 BMP。`HARDCopy:FORMat?` 不是
  `SAVE:IMAGE:FILEFORMAT` 回讀；舊型號儀器端儲存仍不在公開操作內。
- TBS2000 FFT 文件未建立公開原子結果所需 Full-span 換算或頻率參考（第 93–97 頁）。
- TBS2000 Cursor 文件提及 Source 但無對應命令項目，因此 Selected-waveform Adapter
  使用手冊 `SELect:CONTROl` 語義，包含選擇／顯示／擷取影響（第 67–73、161 頁）。
- 部分 TBS2000 Trigger 範例與語法矛盾；僅允許獨立記載控制及明確 Runt 子集
  （第 172、174、177–180 頁）。Pulse-width 只公開所選 less-than/greater-than Threshold，
  不公開保留的獨立 Threshold 或 Range。
- TBS2000 量測彙總範例顯示 Statistics/Indicator 欄位但未定義對應控制，
  不構成公開 Measurement-statistics 或 Marker 顯示功能。

本節歧義不授權新增公開操作、Enum、波形換算、檔案系統 Helper 或支援政策。
