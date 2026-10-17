<a id="scopes-tool-webui"></a>

# Scopes Tool WebUI

[English](README.md) | [User Guide](USER_GUIDE.md) | [使用指南](USER_GUIDE.zh-TW.md)

Scopes Tool WebUI 是 `scopes_tool_core` 的 Localhost-only 瀏覽器 Adapter。
不匯入或依賴 CLI Adapter，也不擁有 VISA、SCPI、儀器身分、能力或安全行為。

Import Package：`scopes_tool_webui`

維護者變更命令公開範圍、瀏覽器狀態、能力呈現或結果行為前，應先讀
[WebUI Change Rules](web-ui-change-rules.md)。

<a id="installation"></a>

## 安裝

從 Repository Root 建立或重用本地虛擬環境，安裝選用 WebUI 相依性：

```powershell
uv venv .venv
uv sync --extra webui --link-mode=copy
```
此 Extra 提供 FastAPI 與 Uvicorn；WebUI 仍屬唯一的 `scopes-tool` Distribution。

<a id="start-the-webui"></a>

## 啟動 WebUI

Server 入口預設直接綁定 `127.0.0.1:8025`，指定固定連接埠不可用時失敗：

```powershell
.\.venv\Scripts\scopes-tool-webui.exe
.\.venv\Scripts\scopes-tool-webui.exe --port 8030
```
建議以 Launcher 作為本地瀏覽器入口：

```powershell
.\.venv\Scripts\scopes-tool-webui-launcher.exe
.\.venv\Scripts\scopes-tool-webui-launcher.exe --port 8030
```
未指定連接埠時，Launcher 從 8025 起最多嘗試 100 個，對占用與權限拒絕衝突自動改用下一個。
等待 `GET /api/health` 驗證 `scopes-tool-webui` 身分，就緒成功才開瀏覽器。
所有自動選項不可用時提供手動連接埠。明確 `--port` 為固定，除非同時指定 `--auto-port`。

不支援遠端綁定。

<a id="device-and-resource"></a>

## 裝置與 Resource

預設執行模式為 **Live**。開啟 Device / Resource 齒輪設定可選 Live、Simulate、Dry-run。

- Live 要求明確 VISA Resource。偵測型號為唯讀，Core 由 `*IDN?` 取得身分並驗證能力。
- Simulate 與 Dry-run 使用 Core 明確註冊的 Profile，預設規劃型號 `keysight-dsox4024a`。
- WebUI Simulate 在 Server 存續期間為每個規劃實體型號保留獨立虛擬儀器狀態 Snapshot。
  每個工作仍開新模擬 SCPI Session，不重用 Session History、Timeout 或 Close State。
  重啟 WebUI 會清除 Snapshot。獨立 CLI 模擬為單次；Worker 在其 Runtime 內保留成功模擬狀態。
- Core/CLI 原始 `list-resources` 仍提供主機 VISA Discovery。WebUI Scan Device
  是獨立 Live-only 動作，要求 `live_only` Discovery 並有界限地探測 `*IDN?`。
- Simulate/Dry-run 停用 Scan Device。直接 WebUI Simulate `list-resources` API 工作
  使用 Core 模擬器回傳所選規劃型號的一個虛擬 Resource，不存取 VISA。
  Dry-run 在建立工作前拒絕 `list-resources`。Live Discovery 不要求已選 Resource 或儀器鎖定。

齒輪設定為 Live 選擇 **System VISA**（預設）或 **pyvisa-py (@py)**。
System VISA 要求已安裝 IVI Runtime，絕不退回 @py。一般安裝與 Windows 封裝內含
`@py` 與 LAN Discovery 相依性，見[安裝前提](../../README.md#install)。
WebUI 不自動切換 Backend；Simulate/Dry-run 忽略此設定。

Product Live 取決於確切偵測型號、Transport、Backend。
PyVISA-py 命令、Basic Controls、Live Data 僅適用已開放的 DSOX4024A、DSOX4034A、TBS2074
TCPIP 連線；相同 Core 政策也拒絕直接 API 未核准要求。變更 Backend 時不連線，
清除已選裝置識別與搜尋顯示；Identity、Editor/Result Cache、Snapshot 仍依 Backend、
Mode、Resource、Model 區分。其他 Backend 的延遲結果不能覆蓋目前裝置狀態。

**Supported devices** 依廠商顯示各 Backend 的 Core 已開放 Product 連線。
System VISA 含七個註冊型號與核准 USB/TCPIP；@py 分頁含三個核准 TCPIP。
其他 `@py` 連線未開放。顯示分頁不改目前 Backend，也不授權命令。

API Client 的 `POST /api/jobs` 可帶頂層選用 `visa_library`：`null`、`""`、
`"system_visa"` 選 System VISA，`"@py"` 選 pyvisa-py；省略預設 System VISA。
規劃模式忽略此選擇。工作內部保留提交 Backend，不新增回應欄位，也不改生命週期、取消或 HTTP 語義。
`GET /api/supported-devices` 保留 List 回應，各項有 Core Registry `model_id`；
選用 `?backend=%40py` 回傳已開放 @py 連線。瀏覽器依 Core 投影停用未核准型號／Backend／
Transport 的 Live 動作，仍允許 Identify 與 Discovery。顯示端點不授權操作；
Core 仍拒絕未核准的直接 API、CLI、Worker 執行。

Math/FFT 回讀先識別 Math Function Slot 的啟用 Operation Family。
讀取其他編輯器（例如目前 FFT 卻讀 Math Visualization）時，將啟用 Family/Operation
呈現為資訊性完成結果，不將有效儀器操作視為格式錯誤。已知但沒有 WebUI 編輯器的
Bus Timing/Bus State 等回報為其他啟用 MATH 操作；未知 Operation 回讀仍是錯誤。

<a id="basic-controls-and-commands"></a>

## Basic Controls 與命令

Basic Controls 提供 Acquisition（Run、Stop、Single）、Trigger（Force Trigger）、
Screenshot（黑底／白底捷徑），提交與 Command Workbench 相同的工作。
它也擁有唯一 **PC output folder** 設定；空白使用 `data`。
**Select Folder** 開 Windows 選擇器，取消不改值；**Open Folder** 必要時建立有效資料夾，
透過 Windows Shell 開啟，是檢視主機輸出的主要入口。此值僅為瀏覽器 Session 狀態，
每次提交工作時擷取其值。

此設定適用 `screenshot`、`capture`、`serial-lister-export`、`segmented-capture`、
`capture-batch`、`capture-until`、`capture-monitor`、`measure-log`、`measure-until`、
`triggered-measure-loop`、`triggered-capture-series`、`sequence` 的電腦端產物。
`smoke` 只在 Diagnostics 啟用儲存產物時使用。工作區顯示目前共用資料夾，不新增路徑控制。
Serial Lister Export 只接受檔名，不能選擇或跳脫共用資料夾。

Command Workbench Single + Wait 支援 Live/Simulate，觸發逾時以秒顯示，預設 5.0 s；
Force-on-timeout 預設未勾。Advanced 預設收合，只含 100 ms Poll Interval。
逾時須為有限正數且換算至少 1 ms，輪詢間隔為正且不大於逾時。
結果使用既有 Trigger-wait 狀態欄位，無產物。

Autoscale 是明確改變狀態的 Live/Simulate 命令。Source Channels、Acquire Mode
（`normal`/`current`）、Channels Mode（`all`/`displayed`）可省略。
Source 只接受型號支援類比通道；省略時不傳清單。選來源後儀器啟用該來源、隱藏其他來源，
依顯示通道 Autoscale。它可改 Channel Display/Scale、Timebase/Delay、Trigger Level，
可能關閉 Cursor、Measurement、Math、Reference Waveform。
WebUI 不新增回讀、Rollback 或瀏覽器 SCPI 行為。

Command Workbench 提供：

- System Information：System 分類的唯讀呈現，Read 執行隱藏 `system-information-snapshot`；
  `identify` Backend 仍負責 Live Resource/Model 偵測與能力限制。
- Acquisition：Acquisition Control 組合 `run`、`single`、`single-wait`、`stop-acquisition`、
  `force-trigger`，使用既有命令／驗證；Acquisition Settings 使用 `acquisition` Query/Apply，
  `autoscale` 保持獨立。
- Timebase：`timebase-scale`、Time Offset（`timebase-position`，成功讀取後依目前 time/div
  提供 Div 快填）、`timebase-reference`。
- Channel：Vertical Scale / Range（`channel-scale-range`）組合 `channel-scale` 與
  `channel-range`；底層命令仍供 CLI/Worker。Vertical Offset（`channel-offset`）成功讀取後
  依所選通道 Scale 提供 Div 快填；另有 `channel-display`、`channel-summary`、`channel-label`、
  `channel-coupling`、`channel-probe`、`channel-bandwidth-limit`、`channel-impedance`、
  `channel-invert`、`channel-units`、`channel-vernier`、`channel-probe-skew`。
- Display：`display-label`、`display-clear`、`display-persistence`、`display-intensity`。
- Measurement：Single Measurement 組合 `measure` 與持續性的 `measure-window`，
  使用標準 `channel` 與量測 Item；`phase`/`delay` 另需 `reference_channel`。
  Multiple Measurements 依型號投影通道及選用通道對，Dry-run 用既有 Core Planner。
  Front Panel Measurements 組合 `measure-install`、`measure-results`、`measure-show`、
  `measure-clear`，每次安裝一個量測並管理顯示／Marker；亦可明確 `measure-menu`
  開啟儀器 Measurement 頁。支援批次結果查詢時，安裝成功後更新結果；不支援查詢仍可安裝。
  支援的 3000X/4000X 同工作區有 Advanced Measurement Statistics，Results Mode 固定 All：
  獨立儀器統計顯示、Infinite 或 2..2000 最大次數、Relative Standard Deviation、Reset、
  明確 Read Statistics 與儀器累積統計表。讀取為唯讀，成功回讀後才可 Apply，不自動輪詢，
  不在瀏覽器計算。2000X 不提供此區。2000X/3000X Marker 永遠開啟，4000X 可顯示／隱藏。
  `measure-source` Backend Helper 仍供既有 API，不在一般 Workbench 顯示。
- Capture：`screenshot`、`capture`。
- Reference：以 `reference-save`、`reference-clear`、`reference-query` 組成 Reference
  Waveform；獨立 `reference-display` 控制槽位 1、2；另有 `reference-label` 與共用
  `display-label` 的 Reference Labels 工作區。
- Save / Export：Save Image（`save-image`）、Save Waveform（`save-waveform`）、Save Setup
  （`setup-save`）三個獨立可見命令共用專用 `editor: save-export`。
  低階設定隱藏，由編輯器讀取／套用；`setup-recall` 不在 Command Browser 或 Save Setup UI。
- System：Diagnostics 組合 `doctor`（不改設定、先查既存錯誤，無錯才 Snapshot，最後仍查錯）
  與完整 `smoke`；另有 `check-error`、`system-status-byte`、`system-operation-status`、
  `system-clear-status`、`system-opc`、`system-standard-event`、`system-options`。
- DVM：`dvm-enable`、`dvm-source`、`dvm-mode`、`dvm-auto-range`、`dvm-query`；
  `dvm-current` 仍供 Backend 呼叫，但在 Command Browser 隱藏。
- FFT / MATH：依能力提供 `fft`，支援型號有基本控制，4000X 有進階控制；另有
  `math-display`、`math-vertical`、`math-operator`、`math-transform`、`math-filter`、
  `math-visualization`、`math-composite-source`、`math-clear`。
- Trigger：專用編輯器涵蓋既有 Edge、External、Glitch/Pulse-width、Runt、Transition、Delay、
  Setup/Hold、Edge-burst、TV、Pattern/OR、Sweep、Reject、Coupling、Holdoff。
- Search：獨立 State/Mode/Count、依能力提供 Event Navigation，以及可選 Bus 的 UART/I2C/SPI/CAN
  Serial Search。
- Serial：以既有隱藏 Serial 基礎命令提供三個工作區：Decode（Bus、目前／待套用協定、Display、
  UART/I2C/SPI/CAN 設定以單一有序 Apply）、Trigger（目前 Decode 協定、條件 Apply 與 Mode
  再檢查）、Lister（Decoded-bus Display、Reference、主機匯出）。
- Segmented Memory：透過 `segmented-memory` 提供明確 Read、Enter、Exit、Segment 選擇與
  目前 Time Tag；持有目標 Segment Count，Enter/Apply 用它設定 Segmented Mode。
- Segmented Capture：以 `segmented-capture` 提供 Channel、Points、Format、Start Capture。
  無可編輯 Segment Count；Live/Simulate 開始時先讀 Memory 的設定 Count 並傳相同值。
  此前置讀取只供執行，不覆蓋 Memory 工作區結果／Cache；Dry-run 因無儀器狀態保留規劃用 Count。
- Cursor：明確 `cursor-query`、手動 `cursor-set`、`cursor-off` 與目前狀態回讀。
- Annotation：`annotation-query`、文字／顏色／背景 `annotation-set`、`annotation-on`、
  `annotation-off`、`annotation-clear` 與回讀；Slot/Position 依 Core 投影。
- WGEN：彙總 `wgen-query` 與獨立 Output/Function/Frequency/Amplitude/Offset/Load；
  設定不會自動開啟輸出。
- DEMO：彙總 `demo-query` 與獨立 Output/Function/Phase，Function 來自 `demo_functions`；
  設定不會自動開啟輸出。
- Workflow：`capture-batch`、`capture-until`、`capture-monitor`、`measure-log`、
  `measure-until`、`triggered-measure-loop`、`triggered-capture-series`，
  以及 Automation 的 Generic Sequence v1。

Resource Scan 使用內部 `list-resources`；工作保留於 Result History，但不在 Workbench。
只在 Live 使用實際 VISA，Simulate 回傳規劃型號虛擬 Resource，Dry-run 拒絕。

Command Browser 第一層為 Category。有 Group Metadata 時顯示 Category → Group → Commands，
否則 Category → Commands。Group 預設展開，可收合；狀態僅存目前頁面，重載後全部展開。
篩選只作用於目前 Category，Group 有相符命令時暫時展開，清除篩選後恢復原收合狀態。
選擇收合 Group 內命令時先展開該 Group。

分組僅為呈現，不改 Core 語義、型號／能力限制或 Metadata 表單。
下述專用編輯器使用既有 Group。

Reference Waveform 工作區可儲存與控制所選 Reference。
Save and Display 先執行 `reference-save`，成功完成後執行 `reference-display`，
最後用 `reference-query` 更新所選狀態。Query 仍回傳 Display/Label，供波形控制使用。
共用 Reference 選擇器在 Live 身分可用前即顯示，之後依偵測型號能力限制。
選擇為被動；Read Reference State 才讀取。Clear 是獨立動作。

Reference Waveform Display 是獨立工作區，各槽位 1、2 各一核取方塊。
Read 透過 `reference-display` 查每槽；Run 套用方塊值再重讀兩槽，
因啟用一槽可能改變另一槽。

Reference Labels 為獨立工作區，以所選槽位操作 `reference-label`，用 `reference-query`
讀狀態。共用儀器 Label Visibility 透過 `display-label` 讀取／套用，屬儀器全域，非單槽設定。
Channel Label 也有共用 Label Visibility，以既有 Query/Set Readback 明確 Apply；
讀取跟隨工作區頂部 Read。此全域設定仍可在 Display 使用。

選擇 `measure-log`、`triggered-measure-loop`、`capture-batch`、`measure-until`、
`capture-until`、`capture-monitor`、`triggered-capture-series` 時開啟以命令命名的共用
Workflow 編輯器，各保留命令名稱與描述。前兩者提供型號投影通道／量測、Channel-pair Row、
共用 Pair Measurement 與既有執行上限。`capture-batch`、`measure-until`、
`triggered-capture-series` 以各流程專屬面板呈現。Capture Until 提供擷取通道、
限所選通道的 Condition Channel、Points、Format、單一 Metric/Operator/Threshold、
`1..255` Matches、整體逾時與相對間隔。符合時儲存剛評估的確切多通道擷取，不再擷取一次。

獨立 `capture` 與非觸發流程 `capture-batch`、`capture-until`、`capture-monitor`
讀取儀器已存在波形；WebUI 提醒先啟用所選通道並完成有效擷取。
`triggered-capture-series` 與 `segmented-capture` 自行啟動／等待擷取，故不使用此前提提示。

Capture Monitor 提供 Channel、Points、Format、有限 Count、相對間隔、Retention Points、
**Save results to files**。執行前說明每通道有界限保留、溢位丟棄最舊完整擷取、
Metric 涵蓋所有觀察 Sample，而圖與 CSV 僅涵蓋保留歷史；重複擷取不是連續時域波形。
預設儲存，關閉則無主機流程產物。選擇／編輯只在瀏覽器被動進行，Run 透過共用前景受理提交一工作。

選擇 Workflow / Automation 的 Sequence 會開 Generic Sequence v1 編輯器，可載入／儲存
`.sequence.json`/JSON 並編輯七個 Core 動作 `wait`、`single`、`wait-trigger`、`measure`、
`capture`、`screenshot`、`cleanup`。Load/Save/Execute 皆透過 Core 驗證；Dry-run 委派
`plan_sequence()`，Live/Simulate 經正常工作、進度、取消、結果、產物設施委派 `run_sequence()`。
**Save results to files** 預設啟用，使用 `field.save_results`；停用時不建立主機 Run 目錄、
Manifest、`scpi.log`，結果不顯示 Files/Output dir/Manifest/SCPI log 路徑。
文件含 `capture`/`screenshot` 時不支援停用儲存。編輯器不自行執行步驟，也不接受任意 SCPI。
Sequence `capture` 使用相同 Core 操作，故同樣顯示既有波形前提提示。

文件使用 `1..255` 步驟、`loop_count` `1..255`，總計最多 65,025 次執行。
每迴圈最多 10 個 Capture/Screenshot 步驟合計，255 次迴圈自然最多 2,550 次。
這是 Scopes Tool 產品限制，不是儀器硬體限制。

Trigger 命令使用專用編輯器，唯一導覽仍為 Command Browser 的 Category → Group → Commands，
不增加第二組分頁。選命令只顯示該表單；Group Metadata 僅導覽，不一起呈現相鄰命令。
編輯器供編輯既有設定，不回報或改變儀器目前 Trigger Type。選擇與 Query Selector 變更僅呈現。
Read Trigger Settings 只讀所選命令設定，Apply 成功後讀回該命令。Read/Apply 序列化，
目前讀寫完成前停用兩動作。各命令維持獨立 Metadata 表單與 Apply，不合併 Payload、
不做 Transaction 或 Apply All。`external-trigger-settings` 等資訊命令保留明確 Read。
切換命令／Group 不確認就捨棄未套用編輯；Read 重讀所選命令但保留編輯。
型號呈現仍來自 Core；不支援命令在 Browser 停用且不在編輯器顯示。

Search 使用專用編輯器，命令不分 Group，每次只呈現所選命令，導覽不執行 I/O。
各設定有自己的 Metadata 表單及獨立 Apply，不做 Apply All、Transaction 或合併 Payload。
`search-count` 唯讀，明確 Read，無 Apply。Event 依能力提供導覽；不支援型號顯示原因，
目前事件 0 原樣顯示，但 Apply 仍使用 Core 驗證，不將顯示 0 變可編輯目標。
Serial Search 依點選命令選協定，Bus 選擇來自型號數量，無額外 Protocol 選擇器。
換 Bus／命令捨棄未套用編輯，不查詢；明確 Read Serial Settings 只讀目前協定／Bus。
Apply 恰好送一個既有 `serial-search-*` 寫入，帶所選 Bus 與 Metadata 條件，
不另送 `search-state`/`search-mode` 或 Decode Mode 再檢查。
結果直接同步表單與狀態列，不再查詢。無前端能力資料庫或 SCPI 產生，
非 Serial Search 條件編輯器仍不提供。

Serial 提供 Decode（`serial-decode`）、Trigger（`serial-trigger`）、Lister（`serial-lister`）
三個任務入口；底層命令仍可執行但不在一般 Browser 導覽。Bus 數與協定來自 Core。
Decode 並列唯讀目前協定與待套用協定，Display／協定設定共用工作區，
Apply Decode Settings 依 Mode、Display、受保護 Configuration 順序只寫 Dirty 區塊，
再做 Decode-only 回讀。待套用目標協定草稿跨 Mode 變更保留；外部改變 Bus Mode 時跳過過期寫入。
Trigger 無自己的 Protocol 選擇器，只讀 Mode Guard 與有效協定 Trigger State，
套用既有 Trigger 命令前再確認 Mode。若是 LIN/FlexRay/A429 等已知協定，
顯示目前協定與不支援設定說明，不發協定專屬查詢。
換 Bus 前確認捨棄編輯，改待套用 Decode Protocol 前確認捨棄舊協定草稿；導覽不查儀器。
Lister 不依目前協定，但 Target 取決於對應 Decode Display；明確 Read 查
`serial-lister-query` 及各可用 Bus 的 `serial-display`，不啟用或改設定。
Display／Reference 透過既有命令套用；Export 取回 Raw CSV 並註冊工作產物。
檔名欄位只寫入 Basic Controls 共用 PC 資料夾，同名已存在時失敗，不覆寫。

Cursor、Annotation、WGEN、DEMO 使用專用編輯器，唯一導覽仍為 Command Browser，無第二層分頁。
Cursor 提供明確 `cursor-query`、手動 `cursor-set`（Source Channel 與型號支援 X1/X2/Y1/Y2，
只寫提供的位置暫存器）、`cursor-off` 及 Mode/Position/Delta/儀器可提供 DYDX 回讀。
Core 依型號及軸決定 Mode。TBS2074 另有可選第一代 `off`、`screen`、`waveform`、`vbars`、
`hbars` Function；明確選擇優先，off/waveform 不需位置或來源即可切換。
TBS2074 支援 X/Y 合併，提示套用會保留所選／顯示來源，必要來源選擇可能重設擷取。
既有 Keysight Manual 與舊 Tek 單軸子集保留。Annotation 提供 `annotation-query`、
`annotation-set`（文字／色彩／背景，不啟用 Annotation）、`annotation-on`、`annotation-off`、
只清文字的 `annotation-clear` 與回讀；單槽型號隱藏 Slot，X/Y 僅在 Core 宣告支援時顯示。
WGEN 每次只顯示所選表單，Read 以一次彙總 `wgen-query` 讀整個狀態；
Output/Function/Frequency/Amplitude/Offset/Load 各有既有命令獨立 Apply，不自動開輸出。
DEMO 同樣每次只顯示所選表單，Read 以一次 `demo-query` 讀整體，Output/Function/Phase
各自 Apply，不自動開輸出。不支援命令保留停用及既有能力原因。

Save / Export 有三個獨立命令：Save Image（`save-image`）、Save Waveform（`save-waveform`）、
Save Setup（`setup-save`），皆使用 `editor: save-export`，Mode 由命令固定。
`setup-recall` 仍在 Browser 隱藏，不經此介面公開。低階 `save-pwd`、`save-image-format`、
`save-image-palette`、`save-image-ink-saver`、`save-image-factors`、`save-waveform-format`、
`save-waveform-length`、`save-waveform-length-max`、`save-filename` 隱藏，由編輯器讀／套用。

Image/Waveform 各使用儀器端 Save 編輯器，提供共用儀器路徑、每次儲存檔名、獨立 Apply、
全寬目的地預覽與進階 Base Filename。各自需明確檔名；TBS2074 Save Waveform 另需
依 Core 的 CH1..CH4 Source Channel，Keysight 隱藏此欄。每次只送既有儀器端 Save，
不繼承或更新 `save-filename`，介面明確區分。不加副檔名、不更新無關設定、不建電腦輸出。
Screenshot 在 TBS2074 用黑底原生 PNG、TDS2024B 用 BMP、TBS1052B 用 USBTMC JPEG。
後兩者不提供 Setup、Reference Memory、儀器端儲存命令／設定。
Screenshot/Capture 仍是獨立主機取回路徑並註冊可下載產物。
PC Folder 不改 `save-pwd`、`save-filename` 或儀器 `:SAVE:*`。

Save Setup 獨立指定儀器槽位（Keysight 0–9，TBS2074 1–9），或支援 Keysight 上的
儀器端檔案如 `\usb\baseline.scp`。Setup 不用共用 Save PWD/Filename 流程。
UI 只提供 Save；Backend `setup-recall` 仍存在但在 Browser 隱藏，不經此介面公開。
同其他 Save，目標在儀器端，不是 PC 下載。

一般 Command Form 以簡單 Metadata 控制一般值、Enum、數字、布林、多選與小型條件群組。
Multiple Measurements 使用 Measurement 編輯器的型號通道／項目、Source/Reference Pair Row
與共用 Pair 選項。`measure-log`、`triggered-measure-loop` 的流程控制在 Workflow 編輯器；
Periodic Capture（`capture-batch`）、Measure Until、Triggered Capture Series 也使用它。
Trigger、Search、Serial、Segmented Memory、Workflow、Cursor、Annotation、WGEN、DEMO
只使用既有 Core 參數語義所需的條件顯示。

以既有 Core `query`/`set` 公開儀器設定的命令，在瀏覽器採讀取、編輯、Apply。
選命令與呈現導覽為被動。Read Current Settings 讀目前值，Apply 送既有 Set，
其 Core 回讀更新編輯器。未儲存編輯不被後續回讀覆蓋；資訊／診斷保留明確 Read/Run。

命令可用性與欄位限制投影自 Core。Live 使用偵測實體型號，Simulate/Dry-run 使用規劃型號。工作區顯示同命令與情境的最新成功結果；History/Raw Detail 保留完整工作診斷。成功的 System/Workflow 結果依操作語義摘要，完整結構與 Raw 仍保留於 Detail。

Timebase Scale、Position、Reference 採相同讀取、編輯、Apply、驗證模式。
Reference 接受 Left、Center、Right。Core 尚無公開 Timebase Mode 控制，WebUI 不自行新增。
Display Persistence 使用明確 Minimum、Infinite、Timed，不要求特殊字串。

這些儀器設定命令使用 Live/Simulate 與既有 Core 能力／驗證邊界，不新增 WebUI 專屬 SCPI。
FFT/Math 為平面表單；4000X FFT 依能力投影 Core Operation、Start/Stop、Gate、Phase Reference、
Detector。Math Transform/Filter/Visualization 同為 Metadata 表單，Operation/Source 來自 Core
常數／能力。2000X/3000X Trend 使用 Source/Measurement，4000X Trend 選既有量測槽。
Cascade Math Source 仍遵守較小 Function 編號規則。

Dry-run 僅限已有 Core Planner 的命令，包括 Acquisition **Query**、Measurement、Sweep、
Waveform Capture、Generic Sequence。WebUI Resource Discovery 不可用於 Dry-run。
Acquisition `set` 在排隊前拒絕；無 Planner 的額外儀器命令不宣告 Dry-run。
Dry-run 不開儀器 Backend，Simulate 用確定性 Core 模擬器，Live 經 Core 開明確 Resource。

<a id="live-data"></a>

## Live Data

Live Data 保留既有 WebUI、Command、Live 狀態，新增唯讀類比通道、水平設定、擷取記憶體模式、
處理類型與共用觸發摘要，以通道識別色卡及 Horizontal/Trigger/Acquisition 卡呈現。
**Read live data** 是明確前景動作，共用 Core 工作受理。識別後選 Live Resource，
或選支援 Snapshot 的模擬型號時自動讀一次；支援型號仍可手動重試。
Live 要求已選且確認身分的 Resource，Simulate 用 Core，Dry-run 顯示不可用。

`acquisition.mode` 為 realtime、segmented、equivalent_time、unknown，來自明確固定 Profile
或對應 Query。`acquisition.type` 另依 Driver Query 回報 normal、average、peak、
high_resolution、unknown。失敗只影響自身欄位，不依廠商或另一欄推論。

Mode、Resource、偵測／規劃型號變更時清摘要。相同情境 Read 失敗保留前次成功摘要。
Live State 以瀏覽器本地時間顯示最近成功完成時間；失敗刷新保留，情境變更隨摘要清除。
不自動輪詢或串流波形。

<a id="jobs-results-and-artifacts"></a>

## 工作、結果與產物

提交回傳 Job ID，瀏覽器經 API 輪詢 `queued`、`running`、`completed`、`failed`、`cancelled`，
呈現結構化 Core 結果、錯誤及診斷。Workflow Result 使用精簡專屬摘要；量測流程可顯示最後量測，
擷取流程只顯示完成／保留計數。獨立 Capture 只顯示通道、實際／要求點數、Format、輸出檔案數。
Preamble、Byte Order、逐次 Metadata、Cycle/Step、Artifact Path、Raw Diagnostic 保留於
Result Detail／流程檔案。傳輸逾時在 Result 用操作語言摘要，原始 VISA/SCPI 留 Detail。
完整 Sample History 不複製到終態工作結果；啟用儲存時仍由既有流程檔案持久保留。

Diagnostics 使用既有 Doctor/Smoke。Doctor 不改設定，先查既有錯誤，無錯才 Snapshot，最後再查。
Smoke 驗證前 Drain 舊錯誤，總會做 Doctor Snapshot、CH1 量測、1000 點 BYTE 傳輸、截圖、最後查錯。
WebUI 預設不儲存 Smoke 產物，仍保留 Result History 精簡結果，不建目錄／檔案。
啟用 **Save diagnostic artifacts** 後在共用 PC Root 寫既有 Report、SCPI Log、CSV、Metadata、截圖。
Diagnostics 在控制下顯示目前情境最新 Doctor/Smoke，History 不變。
失敗 Smoke 保留部分診斷，包括量測 Query 逾時原因。

`capture-monitor` 執行時，既有輪詢只取比瀏覽器最後 Sequence 更新的暫態資料。
每筆正常更新含一個完整 Capture Chunk、精簡計數與全 Session Metric。
前後端皆在 Retention 邊界丟棄最舊完整 Chunk，不無限保留或每次重傳整個視窗。
只有 Client 落後保留範圍才做有界限 Reset。暫態陣列只屬 WebUI Runtime，不複製到最終
Job Result、CLI JSON、Common Worker Result，也不需跨工作完成保留。
摘要顯示目前執行／保留狀態；Channel Statistics 涵蓋所有 Sample，圖只顯示保留視窗。
X 用全域 Sample Index，大視窗依像素做 Min/Max 顯示抽稀；Hover 可查精確 Raw Sample。
每次 `time_s` 仍局部，重複擷取為獨立記錄，非連續時域，可能有空隙。

佇列工作可立即取消；執行中採合作式取消，Core／Session 清理完成前仍 Running，不強制中斷 VISA。
Segmented Capture 以 Core 終態為準：全部 Segment 已匯出後才收到 Stop，不覆蓋 completed；
Core Partial/Error 不改標為 Cancelled。關閉 Launcher 先停止受理、要求取消、
等待工作完成且關自己的 Session，再停 Uvicorn。有逾時；工作未完或 Close 失敗時顯示
**Shutdown incomplete**，保留 Launcher 可重試 Quit，不隱含 Safe Cleanup。
啟用儲存的 Capture Monitor 在至少一次成功後取消，Core 寫停止時最終保留視窗，WebUI 維持取消，
不重新擷取或當自然完成；第一次成功前取消不建空 CSV，不儲存時無流程產物。
Screenshot/Capture 註冊產物；儀器端 `save-image`/`save-waveform` 回傳 Core Save 結果，無主機產物。
UI 保留結構化 Detail，不加下載連結，請用 Basic Controls **Open Folder**。
Backend 註冊與 Job-scoped Download API 保留，只能解析該工作精確註冊檔案，且須仍在提交 Root 內。

提交的 PC Folder 就是實際主機輸出根目錄。Screenshot/Capture 用既有 Core/CLI 時戳命名直接寫入；
Lister Export 用明確檔名；多檔 Workflow 保留命令專屬時戳子目錄。
無產物工作不建立／驗證 Folder，Dry-run 只規劃。
接受絕對／相對 Root，在輸出需要時建立；建立／寫入失敗回報，不退回其他位置。

有限流程執行時，中央 Result History 顯示已完成工作與經過時間；有固定總量時另顯示完成／總計。
`capture-monitor` 流程自有波形／Metric 呈現，Generic Sequence 自有 Step Progress，與一般流程進度分開。

<a id="core-coverage-boundary"></a>

## Core 涵蓋邊界

Workbench 刻意只公開有明確瀏覽器互動的操作者設定、擷取、有限流程與資訊命令。
Discovery 用隱藏 `list-resources`；System Information 是 System 分類唯讀視圖，
無主頁獨立區，Read 執行隱藏 `system-information-snapshot`。
底層 `identify` 仍負責 Resource/Model 偵測與能力限制。

進階／診斷 CLI 不自動變成 Browser 命令。刻意省略直接 SCPI、廣泛 Cleanup、Worker/Hardware-report。
獨立低階擷取查詢不公開；Sample Rate、Acquisition Points、Record Length 只在唯讀 System
Information 經 Core 能力回讀顯示，無 Setter 或直接控制。
避免沒有適當互動、能力、結果模型就公開 Core 操作。
基本 FFT Units/Window 在 Core 提供可直接投影的公開選項 Metadata 前，仍為 Core 驗證文字。

<a id="language-help-and-current-limitations"></a>

## 語言、Help 與目前限制

既有 Help 按鈕依 Locale 在新分頁以 `noopener` 開 `/static/help/webui.html` 或
`/static/help/webui.zh-TW.html`，資源沿用 no-store Static Service。
System/Light/Dark 沿用既有主題 Cookie，偏好透過 URL 傳遞。
Electron 僅允許清單內同源本地 Help 由系統瀏覽器開啟，其他 Popup 仍拒絕。
Desktop 共用 WebUI Help，閱讀時需本地 Host；CLI 則直接開封裝檔案，無須 Server。

Browser Launcher、Electron Desktop 啟動、目錄建置與共用 `_internal` 請見
[根目錄 README](../../README.md)；離線 Help 維護請見 [Help Maintenance](../help/README.md)。


瀏覽器支援 English 與繁體中文（`zh-TW`），本地記憶 Locale。
Launcher 僅英文。Command ID、Model ID、VISA Resource、SCPI、JSON Key、Raw Diagnostic 不變。

WebUI 不含遠端存取、驗證、多儀器 Session、WebSockets/SSE、一般 Live 波形串流、
自動 Live Data 輪詢、專用 FFT/Advanced Math 編輯器，或 Core 未公開功能的條件編輯器。
Dry-run 仍只限已有 Core Planner 的命令；`capture-batch`、`measure-log` 僅 Live/Simulate。
