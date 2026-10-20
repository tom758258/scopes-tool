# Scopes Tool Core

[English](README.md)

透過 PyVISA 相容 Backend 控制示波器的廠商中立 Core Runtime 套件。

Distribution：`scopes-tool`

Import Package：`scopes_tool_core`

## 用途與責任

Core 擁有 Scopes Tool Adapter 共用的 Runtime 與硬體行為，包括：

- 安全開啟 VISA Resource，解析所選執行模式。
- 偵測 `*IDN?` 身分並解析標準實體型號。
- 套用 Registry 連結的 Capability Profile 與 Driver 行為。
- 在適用情況下，於不安全或改變狀態的操作前驗證要求。
- 產生並執行適合型號的儀器操作，包括 SCPI 查詢、設定、擷取與解析。
- 提供 Simulator、Fake Backend 與無硬體規劃路徑。
- 執行有限次同步 Core 流程，提供合作式取消、進度回報與操作專屬 Sample。

CLI、Worker、WebUI 是 Core 的 Adapter，負責命令解析、呈現、序列化、終端機／瀏覽器行為、
HTTP 控制與佇列／工作生命週期。它們必須使用 Core 的身分、能力、驗證、驅動與儀器行為，
不可另行實作。Core 不匯入 Adapter 套件。

## 身分、能力與 Runtime 邊界

Live 操作以偵測到的 `*IDN?` 與解析出的標準實體型號為權威。
Simulator 與 Dry-run 規劃由規劃實體型號選擇註冊 Capability Profile，供無硬體規劃與驗證。
Live 的預期實體型號僅作安全防護，絕不取代透過 `*IDN?` 偵測的身分或能力。
未知、未註冊或不相符的 Live 廠商、型號、Profile、Driver 一律拒絕。

Capability Profile 描述型號支援的 Runtime 範圍，不證明儀器選配或授權已安裝；
仍以實機錯誤為準。Simulator 與 Dry-run 支援無硬體開發與驗證，不構成實機驗證。

Core 擁有硬體行為及安全驗證；Adapter 不定義 Core 驗證契約。
Core 流程支援合作式取消，但不強制中斷阻塞中的 VISA 或裝置讀取。
Core 也不擁有 Worker 佇列受理、持久化工作生命週期、HTTP 控制或 WebUI 呈現。

VISA Library 選擇器正規化為以下 Core 身分：

- 未指定或空白 → `system_visa`
- `@py` → `pyvisa_py`
- `@bt` → `pyvisa_bt`
- 其他明確選擇器 → `custom_visa`

System VISA（未指定、空白或 `system_visa`）明確開啟 `@ivi`，以 PyVISA
`IVIVisaLibrary` 類型驗證已載入 Library。缺少、失敗或非 IVI Backend 一律拒絕；
驗證失敗時關閉已建立 Manager。安裝 pyvisa-py 或設定 `PYVISA_LIBRARY=@py`
不改變此選擇；其他明確選擇器原樣傳遞。

一般安裝與 Windows 封裝內含 `pyvisa-py` 及 LAN Discovery 相依性，
詳見[安裝前提](../../README.md#install)。其他 Backend 可能需另行安裝。
Backend 可用不授予 Product Live 支援。Core 在開啟 VISA 前檢查 Transport／Backend，
在 Product 命令前檢查 `*IDN?` 解析的確切實體型號。
System VISA Product 支援限核准的型號／USB 或型號／TCPIP 組合；
`@py` Product 僅開放 DSOX4024A、DSOX4034A、TBS2074 的 TCPIP，USB 未開放。
`@bt` 與明確自訂 VISA Backend（包括明確 `@ivi`）未開放 Product Live；
請使用預設 System VISA 選擇器要求已驗證的 IVI Backend。

Contributor Validation Mode 是明確的 CLI-only 選項，適用於僅限驗證的 `@py` USB
連線及支援的 `@py` TCPIP 範圍；仍要求實際 `*IDN?`，不授予 Product 存取。
WebUI 與 Worker 不可選此模式。Identify 與 Resource Discovery 仍是診斷；
Dry-run 與模擬不開啟 Live VISA Session。
直接 Python 使用 `Oscilloscope.open()` 是低階 Session 介面，不是 Product 支援入口。
確切連線及型號功能限制請見[支援型號](supported-models.zh-TW.md)。

## 工作流程 Manifest 持久化

Measurement Log、Triggered Measurement Loop、Periodic Capture、Triggered
Capture Series、Segmented Capture、Capture Until 與 Generic Sequence 將每筆
已提交歷史附加至內部 JSONL Journal。執行中的 `manifest.json` 保存精簡進度與
狀態，不包含累積歷史或 Artifact 清單。先寫入 CSV 資料列與擷取檔案；歷史與進度
快照都成功保存後，才增加完成計數並通知 Sample／Progress Callback。

正常完成、合作式取消或可處理的錯誤／中斷時，已提交紀錄會整合為完整的最終
`manifest.json`，維持既有 Schema、欄位、歷史順序與 Artifact 路徑。
最終 Manifest 經原子替換成功發布後，才移除 Journal。若最終發布失敗，流程不得
回報成功，並盡可能保留已寫入資料與 Journal。程序強制終止或斷電後的自動復原
不在此契約範圍內。原本支援 No-save 的流程不會建立 Journal 或 Manifest。

## 功能領域

Core 將儀器介面分成以下功能：

- 連線、身分、能力、狀態與安全 Resource／Runtime 管理。
- 通道、顯示、Annotation、時基、游標、擷取與唯讀儀器狀態摘要。
- 量測、依能力限制的進階統計設定／結果、波形、截圖、Reference Waveform，
  以及儀器端或主機端 Save/Export Helper。
- 各類觸發、共用觸發設定、單次觸發控制與有限次等待／擷取 Helper。
- Serial Bus 設定、Serial Trigger／Search、Lister 狀態與 Raw Lister 匯出。
- 儀器端 Math／FFT，包括支援的 Transform、Operator、Filter、Visualization 與系列專屬路徑。
- DVM、WGEN、Demo Output、Segmented Memory 等選配或儀器功能，受 Profile／儀器限制。
- 有限次 Core 流程與模擬器，供無硬體執行、規劃、Callback 及確定性錯誤路徑測試。

此處為功能概覽，不是命令參考，也不是完整 API、SCPI、型號、韌體或選配支援矩陣。

## 工作流程基礎

Core 以既有儀器操作組成有限次同步流程，可接受合作式停止要求、同步進度回報與操作專屬
Sample Callback；不引入非同步 Runtime、Scheduler 或 Event Bus。

目前流程包括 `measure-log`、透過 `capture-batch` 的 Periodic Capture、Capture Until、
Capture Monitor、Triggered Measurement Loop、Triggered Capture Series、Measure Until
Condition、Generic Sequence，以及 Profile 支援時的 `segmented-capture`。
流程所持有的波形可在有界限 RAM 分析或保留，不改變獨立 `capture` 產生檔案的行為。
Core Integration 記載各流程的要求欄位、預設值、終態、產物 Schema，
以及適用的 Generic Sequence 規則，詳見 [Core Integration](integration.md)。

## 公開套件介面

下游 Python 使用者應優先從 `scopes_tool_core` 套件根目錄匯入。
根目錄 `__all__` 定義公開匯入邊界；完整公開清單與整合範例維護於
[Core Integration](integration.md)。

僅供實作的子模組與 Helper 不因可匯入就成為公開 API；README 整理不擴張此邊界。

## 型號 Profile 與 Tektronix 實作邊界

使用者可用的型號及連線組合以[支援型號](supported-models.zh-TW.md)為準。
Core 使用以下註冊 Profile；Keysight Driver ID 為 `keysight-infiniivision`，
Tektronix Driver ID 為 `tektronix`。Live 依實際 `*IDN?` 身分選擇 Profile，
要求的規劃型號或預期型號不能覆蓋偵測結果。

| Profile ID | Series | 註冊型號 | 類比 Channel |
| --- | --- | ---: | --- |
| `keysight-infiniivision-2000x` | 2000X | DSOX2004A | 4 |
| `keysight-infiniivision-3000x` | 3000X | DSOX3024A | 4 |
| `keysight-infiniivision-4000x` | 4000X | DSOX4024A, DSOX4034A | 4 |
| `tektronix-tbs2074` | TBS2000 | TBS2074 | 4 |
| `tektronix-tds2024b` | TDS2000B | TDS2024B | 4 |
| `tektronix-tbs1052b` | TBS1000B | TBS1052B | 2 |

僅供驗證的 `@py` USB 型號及 CLI 維護者驗證方式見
[CLI README](../cli/README.zh-TW.md)；不會擴大 Product Live 支援。

<a id="aggregate-projections"></a>

### 彙總投影

彙總跳過不支援的原子查詢，絕不只為探索支援就改變 Source/Display、Measurement Slot、
Trigger Mode 或 Cursor Units。

| 彙總 | TBS2074 投影 | TDS2024B 投影 | TBS1052B 投影 |
| --- | --- | --- | --- |
| `channel-summary` | CH1–CH4 的 display、scale、offset、coupling、probe ratio、bandwidth limit、invert、label、probe skew、V/A units；range、impedance、vernier 不可用。 | display、scale、offset、coupling、probe ratio、bandwidth limit、invert、units；label、probe skew、range、impedance、vernier 不可用。 | 同 TDS2024B，僅 CH1/CH2。 |
| `live-data-snapshot` / `query_instrument_summary` | CH1–CH4 的 display/scale/offset/units、同[支援型號](supported-models.zh-TW.md#acquisition-timebase-and-channels) 的 Delay Mode ON 前提的 timebase scale/position、trigger type/sweep、edge source/slope、依通道 Level 與已確認來源單位。 | 通道 display/scale/offset/units、timebase scale/position、trigger type/sweep/source/slope；目前類比 Edge Source 的 MAIN:LEVEL 可作 Snapshot 資料，即使獨立指定通道 Level 不支援。 | 同 TDS2024B，限兩通道。 |
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
不是公開 Result/Raw 契約要求的單一原生結果回應。Doctor 重用允許投影；Reference Label 可能依型號維持 Nullable。Hardcopy State 或 DVM/WGEN/Demo Query 等必要狀態結果，
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

## 驗證

從 Repository Root 執行聚焦的 Core 文件與責任檢查：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_core_docs_ownership.py -q -p no:cacheprovider --basetemp .tmp_tests\core-docs
```

## 文件

- [Core Integration](integration.md)
- [支援型號](supported-models.zh-TW.md)
- [CLI 文件](../cli/README.zh-TW.md)
- [共用 CLI、Worker 與 Orchestrator 契約](../contracts/)
