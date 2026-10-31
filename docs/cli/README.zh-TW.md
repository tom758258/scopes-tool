<a id="scopes-tool-cli"></a>

# Scopes Tool CLI

[English](README.md) | [User Guide](USER_GUIDE.md) | [使用指南](USER_GUIDE.zh-TW.md)

透過 Core 與 PyVISA 操作已註冊 Keysight InfiniiVision 與 Tektronix 示波器的 CLI Adapter。
型號限制以[支援型號](../core/supported-models.zh-TW.md)為準。

Distribution：`scopes-tool`

Console Script：`scopes-tool`

Module 入口：`python -m scopes_tool_cli.cli`

<a id="install-for-development"></a>

## 開發安裝

從 Repository Root 執行：

```powershell
uv sync --all-extras --link-mode=copy
```
<a id="basic-usage"></a>

## 基本用法

Editable Install 後，一般 CLI 操作建議使用 Windows 虛擬環境 Console Wrapper：

```powershell
.\.venv\Scripts\scopes-tool.exe identify --simulate --json
```
Module 形式仍可作開發或備援入口：

```powershell
.\.venv\Scripts\python.exe -m scopes_tool_cli.cli identify --simulate --json
```
儀器命令提供 Live 與支援的 Simulate/Dry-run，依操作與型號而定。
Agent／自動化應先 Dry-run、Simulate，再要求實機存取。
JSON 含 `schema_version: 2` 與 `timestamp_utc`。

Scopes Worker 使用 Common schema `3`、`v3-only` 相容性與
`multi_job` / `startup` 執行模式。Manifest 與一般 CLI JSON 維持 schema `2`。
Manifest 宣告 `common.async_jobs` 版本 1 和選配的 `common.streaming` 版本 1；
一般 Worker 仍僅採用 Async Jobs，原有行為不變。使用
`scopes-tool worker --streaming --simulate --model keysight-dsox4024a --format jsonl`
可選擇延後啟動、一次性開始的唯讀數值 Measure Stream，透過既有 `POST /command`
控制，持續以 JSONL `sample` 輸出多通道數值；詳見[Worker 契約](../contracts/scopes-worker-contract.md)。
支援有限 Cycle 數及真正無限量測直到 `POST /stop`；不提供 v2 fallback 或 Common Job Cancel。

共用機器契約仍在根目錄：

- `docs/contracts/common-cli-jsonl-contract.md`
- `docs/contracts/scopes-cli-jsonl-contract.md`
- `docs/contracts/common-worker-protocol.md`
- `docs/contracts/scopes-worker-contract.md`
- `docs/contracts/common-orchestrator-workflows.md`
- `docs/contracts/scopes-orchestrator-workflows.md`

CLI 整合說明在 [CLI Integration](cli-integration.md)。

<a id="implemented-scope"></a>

## 已實作範圍

目前實作：

- 列出所選 Backend 回報的 VISA Resource，並可篩選能開啟且回應 `*IDN?` 的項目。
- 查詢／解析 `*IDN?` 驗證基本通訊，透過標準實體型號 Registry 選擇能力。
  `--model` 僅接受已註冊標準 ID，不接受原始型號或僅相似系列字串。
- Keysight ID 為 `keysight-dsox2004a`、`keysight-dsox3024a`、`keysight-dsox4024a`、
  `keysight-dsox4034a`，對應 DSOX2004A、DSOX3024A、DSOX4024A、DSOX4034A；
  Tektronix 為 `tektronix-tbs2074`、`tektronix-tds2024b`、`tektronix-tbs1052b`，
  對應 TBS2074、TDS2024B、TBS1052B。下列儀器命令除明確標 Tektronix 外採 Keysight 語法，
  不擴張 Supported Models 矩陣的 Tek 支援。
- 以 `:SYSTem:ERRor?` 讀一或多筆 System Error Queue。
- 基本擷取控制 `:STOP`、`:RUN`、`:SINGle`；以 `:ACQuire:TYPE`、`:ACQuire:COUNt`
  設定／查詢擷取類型與平均次數。
- 以 `:ACQuire:SRATe?` 查目前類比取樣率 Hz；以 `:ACQuire:POINts?` 查目前擷取點數，
  與 `capture --points` 傳輸點數分開，均為唯讀。
- 以 `:ACQuire:RLENgth?` 查目前 Record Length，與 Acquisition Points／Transfer Points 分開；
  此 Keysight 功能僅 4000X，不支援 2000X/3000X。
- `:CHANnel<n>:DISPlay` 開／關／查類比通道顯示；`:CHANnel<n>:LABel` 設／查標籤，
  2000X/3000X 最多 10 可列印 ASCII，4000X 最多 32，不轉大寫、不截斷。
- `:CHANnel<n>:SCALe`、`:CHANnel<n>:OFFSet` 設／查 Scale/Offset；
  `:CHANnel<n>:COUPling`、`:CHANnel<n>:PROBe`、`:CHANnel<n>:BWLimit` 設／查 Coupling、
  Probe Ratio、Bandwidth Limit。
- `:CHANnel<n>:IMPedance`、`:CHANnel<n>:INVert`、`:CHANnel<n>:RANGe`、`:CHANnel<n>:UNITs`、
  `:CHANnel<n>:VERNier`、`:CHANnel<n>:PROBe:SKEW` 設／查阻抗、反相、全幅範圍、單位、微調、偏移。
- `:TIMebase:SCALe`、`:TIMebase:POSition`、`:TIMebase:REFerence` 設／查時基。
- `:TRIGger:MODE EDGE`、`:TRIGger:EDGE:*` 設／查類比 Edge Source/Level/Slope；
  `:TRIGger:EDGE:COUPling`、`:TRIGger:EDGE:REJect` 設／查 Coupling/Reject。
- `:TRIGger:SWEep`、`:TRIGger:NREJect`、`:TRIGger:HFReject` 設／查共用 Sweep/Reject。
- `:TRIGger:MODE GLITch`、`:TRIGger:GLITch:*` 設／查類比 Pulse-width。
- `:TRIGger:MODE RUNT`、`:TRIGger:RUNT:*` 與共用 `:TRIGger:LEVel:LOW/HIGH` 設／查 Runt。
- `:TRIGger:MODE TRANsition`、`:TRIGger:TRANsition:*` 與相同 Threshold 命令設／查 Transition。
- `:TRIGger:MODE DELay`、`:TRIGger:DELay:*` 設／查 DSO 類比 Edge Then Edge/Delay。
- `:TRIGger:MODE SHOLd`、`:TRIGger:SHOLd:*` 設／查 Setup-hold。
- `:TRIGger:MODE EBURst`、`:TRIGger:EBURst:*` 與選用來源限定 `:TRIGger:EDGE:LEVel`
  設／查 Nth Edge Burst。
- `:TRIGger:MODE TV`、`:TRIGger:TV:*` 設／查基本 TV/Video。
- `:TRIGger:MODE PATTern`、`:TRIGger:PATTern:FORMat ASCii`、`:TRIGger:PATTern "<pattern>"`、
  `:TRIGger:PATTern:QUALifier ENTered` 設／查 DSO 類比 ASCII Pattern。
- `:TRIGger:MODE OR`、`:TRIGger:OR "<pattern>"` 設／查類比 OR；寬度依型號通道能力，
  已註冊 Keysight 皆四通道，Bit 順序 CH4、CH3、CH2、CH1。
- `:DISPlay:LABel` 控制標籤；`:DISPlay:CLEar` 清波形顯示；`:DISPlay:PERSistence`、
  `:DISPlay:INTensity:WAVeform`、`:DISPlay:VECTors` 設／查顯示；
  `:DISPlay:ANNotation` 設／清／查註記，4000X 索引 `1..10` 並支援 X1Position/Y1Position。
- 查／隱藏／設手動游標、設／查 Holdoff、明確 Autoscale、儲存／召回 Setup Slot 或 `.scp`、FFT。
- 唯讀 Vpp、Frequency、Period、顯示平均／DC RMS、Min/Max、Rise/Fall、Amplitude/Top/Base、
  Overshoot/Preshoot、正負 Width/Duty、Area（3000X/4000X）、Edge/Pulse Count、參數化時間、
  Phase 與安全 4000X Delay，明確處理無效 Sentinel。
- `measure-results` 在 3000X/4000X 傾印目前前面板量測，不清除／安裝／改設定。
- `measure-install` 安裝一個支援的簡單量測，不清既有量測或查值；
  `measure-stats` 在 3000X/4000X 重建 Quick Measurement 並查統計。
- `measure-clear`、`measure-show`、`measure-source`、`measure-window` 控制量測子系統，
  `measure-menu` 開儀器量測介面。
- `reference-save`、`reference-display`、`reference-label`、`reference-clear`、`reference-query`
  管理 Reference 槽位 1、2。
- `search-state`、`search-mode`、`search-count`、`search-event` 控制／查詢 Search 與事件導覽。
- 儀器端 SAVE 設定與 Image/Waveform Save 寫入儀器目前儲存位置，不建立主機檔案。
- `demo-query`、`demo-output`、`demo-function`、`demo-phase` 操作依選配的 DEMO；
  `wgen-*` 查／設 Output、Function、Frequency、Amplitude、Offset、Load。
- `serial-status`、`serial-uart-set`、`serial-uart-show`、`serial-i2c-set`、`serial-i2c-show`、
  `serial-spi-set`、`serial-spi-show`、`serial-can-set`、`serial-can-show` 查狀態與基本 Decode。
- `doctor` 收集唯讀診斷；多通道／可選 Pair Sweep 遇失敗繼續並摘要。
- `measure-log` 有限批次唯讀記錄，預設在一 Run 目錄寫 CSV、`manifest.json`、`scpi.log`。
- `measure-until` 查單一唯讀量測直到數值條件符合或逾時失敗。
- `capture-until` 在 RAM 評估，只儲存符合的確切擷取，保留所有選擇通道。
- `capture-monitor` 有限 Session，逐通道有界限保留波形並維持全 Session Metric。
- `measure-log`、`measure-until`、`triggered-measure-loop`、`capture-monitor` 可 `--no-save`，
  不寫主機檔案但保留精簡結果；預設儲存。獨立 `capture` 無此選項，始終產生檔案。
- `sequence` 執行嚴格有限 Generic Sequence v1 JSON，與 WebUI 共用 Core 驗證／執行與確定性產物。
- Capture-safe Smoke 寫 JSON、SCPI Log、CSV、Metadata、截圖診斷目錄。
- BYTE/WORD 多類比通道 Capture 匯出 CSV/JSON，可選 PNG Plot、`data` 下預設時戳 CSV，
  以及明確 `capture --wait-trigger`。
- `capture-batch` 執行 Periodic Capture，在一 Run 目錄寫每次 CSV/Metadata、Manifest、SCPI Log。
- `triggered-capture-series` 每次等自然觸發再在一 Run 目錄寫波形。
- `segmented-capture` 有限單通道逐 Segment CSV，加共用 Manifest/SCPI Log。
- 截取目前畫面為 PNG/BMP/BMP8bit，可使用 `data` 下預設時戳路徑。
- `FakeBackend` 提供無硬體測試；`force-trigger` / `:TRIGger:FORCe` 明確強制一次觸發，
  不改獨立 `single` 或預設 `capture`。

套件不送 `*RST`、不改 VISA 預設逾時、不執行 Return-to-local。
改狀態行為僅透過明確 CLI；`doctor`、`smoke`、`acquisition-check` 不呼叫新增的
Cursor/Holdoff/Autoscale/Setup/Statistics/FFT 路徑。

目前無公開 Acquisition Run-state Query，CLI 不使用 `:RSTate?`。

<a id="development"></a>

## 開發

PowerShell 進入專案，建立／重用虛擬環境，安裝開發相依性後執行預設無硬體測試：

```powershell
cd path\to\scopes-tool
```

```powershell
uv venv .venv
```

```powershell
uv sync --all-extras --link-mode=copy
```
Repository 以已提交 `uv.lock` 同步相依性，不設定為 uv Workspace；CI／嚴格檢查使用：

```powershell
uv sync --all-extras --locked --link-mode=copy
```
從根目錄執行無硬體測試：

```powershell
New-Item -ItemType Directory -Force .tmp_tests | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --basetemp .tmp_tests\full
```
涵蓋 `tests/core`、`tests/cli`、`tests/webui`、`tests/tooling`。
使用 Repository 本地 pytest 暫存目錄避免 Windows 共用 Temp 權限衝突，成功後可移除。
額外參數直接傳 pytest。

未指定 `--visa-library`、空白或 `system_visa` 時，Core 明確要求
`pyvisa.ResourceManager("@ivi")` 並驗證 IVI；缺少／失敗即拒絕，`PYVISA_LIBRARY=@py` 不改選擇。
其他明確選擇器原樣傳 PyVISA，`@py` 為 `pyvisa_py`、`@bt` 為 `pyvisa_bt`，其餘非空為 `custom_visa`。

Worker 啟動時可指定 `--visa-library`，例如 `--visa-library @py`。
選定 Backend 固定供所有 Job 使用，包含 Serial Trigger；Request 不可覆寫。
未指定時維持 System VISA。Worker Live 身分驗證與 Core Product Support Policy 維持不變，
Ready 與 Status 不新增 Backend 欄位。

一般安裝與 Windows 封裝內含 pyvisa-py 與 LAN Discovery 相依性，見[安裝前提](../../README.md#install)。
Product Live 要求核准的偵測型號／Transport／Backend。System VISA 支援表列 USB/TCPIP；
`@py` 只開放 DSOX4024A、DSOX4034A、TBS2074 的 TCPIP/LAN，其他 @py、@bt、自訂選擇器
（包括明確 @ivi）未開放。預設／system_visa 使用已驗證 IVI。

`list-resources`/`identify` 可用已安裝選定 Backend 診斷，不代表 Product 授權。
Product 在開 VISA 前查 Transport，在業務 SCPI 前用真實 `*IDN?`，型號能力與選配另行限制。
確切範圍見[支援型號](../core/supported-models.zh-TW.md)。

貢獻者硬體驗證使用隱藏的 `--validation-allow-pending-live-support` CLI 選項；
維護中的 `scripts/live-*.ps1` 在選用 `-Backend "@py"` 時傳入此選項。
此選項只允許 Core 已正式支援或明確登記為僅供驗證的精確型號、傳輸方式與後端組合，
不限 `@py`。System VISA 沿用既有正式支援連線，未增加任何僅供驗證的組合；
`@bt` 與自訂後端沒有已登記的驗證連線。
僅供驗證的 `@py` USB 型號為 `keysight-dsox4024a`、`keysight-dsox4034a`、
`tektronix-tbs2074`；一般操作仍不開放這三組連線。
其他連線仍以[支援型號](../core/supported-models.zh-TW.md)的正式連線矩陣為準。

Core 在開啟 VISA 前拒絕未登記的後端／傳輸方式組合，儀器操作前再核對實際 `*IDN?` 型號。
`--model` 不能覆寫偵測身分。既有型號能力、已安裝選配、儀器狀態、安全與清理檢查繼續生效；
此選項不允許不支援的操作。Worker 與 WebUI 不能選用貢獻者驗證。
驗證結果不會改變正式支援，必須經過審查與明確核准，詳見 [Core README](../core/README.zh-TW.md)。
直接呼叫 Python `Oscilloscope.open()` 不受 Product Policy Gate 管理。

<a id="agent-safe-automation"></a>

## Agent 安全自動化

接受儀器連線的命令也接受 `--json`、`--simulate`、`--dry-run`、`--model`，實際模式可用性依命令而定。
`--dry-run` 驗證參數並檢視產生的 SCPI，不開 VISA、不寫檔；加 `--json` 可取得機器可讀 Payload。
`--simulate --json` 使用確定性的 Hardware-free Simulator；Capture Workflow 仍寫入模擬 Output File 供離線驗證。
JSON 含 `schema_version: 2` 與 `timestamp_utc`。

僅 `--simulate` 時可用 Preset、JSON Scenario、重複 Signal Override、Error Injection：

```text
--simulate-preset noisy-sine
--simulate-scenario path\to\scenario.json
--simulate-signal CH:shape:frequency_hz:vpp_v:offset_v:phase_deg[:noise_rms_v]
--simulate-system-error -113
--simulate-binary-transfer-failure
--simulate-invalid-measurement CH2
--simulate-display-off CH1
```
`CH` 可為 `CH1` 或 `1`。Shape 支援 `sine`、`square`、`ramp`、`dc`、`noise`。
內建 Preset 為 `noisy-sine`、`square-with-offset`、`phase-shifted-pair`、`dc-invalid-frequency`、`trigger-misaligned`。
設定依序套用 Built-in Default、`--simulate-preset`、`--simulate-scenario`，最後是 `--simulate-signal` 與 Error Injection 等明確 CLI Override。Scenario File 只接受 JSON。

Agent 只有明確使用者授權後才可存取實機。單次命令明確 `--resource <RESOURCE>` 或
`SCOPES_TOOL_RESOURCE` 即選擇該單一實機。Live Worker 仍需 `--live --resource`。
`--log-scpi` 寫 stderr，不可當 JSON 解析。

Dry-run/Simulate 的 `--model` 是規劃用標準實體 Model ID；Simulator IDN 與 Capability 來自該 Registry Entry。
One-shot Live 從實際 `*IDN?` 取得 Physical Identity/Capability，`--model` 不覆寫偵測結果。
Live Worker 的 `--model` 是預期標準實體 Model ID，不符時在命令專屬 SCPI 前失敗。

```powershell
.\.venv\Scripts\scopes-tool.exe identify --dry-run --json
.\.venv\Scripts\scopes-tool.exe identify --simulate --json
.\.venv\Scripts\scopes-tool.exe acquisition-points --query --dry-run --json --model keysight-dsox4024a
.\.venv\Scripts\scopes-tool.exe acquisition-points --query --simulate --json --model keysight-dsox4024a
.\.venv\Scripts\scopes-tool.exe record-length --query --simulate --json --model keysight-dsox4024a
.\.venv\Scripts\scopes-tool.exe capture --simulate --json --simulate-preset phase-shifted-pair --channel 1 --channel 2 --csv .tmp_tests\preset.csv
.\.venv\Scripts\scopes-tool.exe measure --simulate --json --simulate-scenario path\to\scenario.json --channel 1 --item frequency
.\.venv\Scripts\scopes-tool.exe measure --simulate --json --simulate-signal CH1:square:1000:1.0:0:0:0.02 --channel 1 --item vpp
.\.venv\Scripts\scopes-tool.exe capture --simulate --json --simulate-binary-transfer-failure --channel 1 --csv .tmp_tests\failure.csv
.\.venv\Scripts\scopes-tool.exe capture-batch --simulate --json --channel 1 --count 2 --output-dir .tmp_tests\sim_batch
.\.venv\Scripts\scopes-tool.exe measure-log --simulate --json --channel 1 --items vpp,frequency --count 2 --output-dir .tmp_tests\sim_measure_log
.\.venv\Scripts\scopes-tool.exe measure-log --simulate --json --channel 1 --items vpp --count 2 --no-save
```
自動化與 Orchestrator 契約位於 `docs/contracts/`；先讀 `docs/contracts/scopes-worker-contract.md`、`docs/contracts/common-cli-jsonl-contract.md`、`docs/contracts/scopes-cli-jsonl-contract.md`、`docs/contracts/scopes-orchestrator-workflows.md`。
Live 前先做 Dry-run/Simulate，並使用操作人員明確選定的 Resource。

<a id="commands"></a>

## 命令

不需 VISA 或 Server 即可開啟已封裝離線指南：

```powershell
scopes-tool user-guide
scopes-tool user-guide --lang en
scopes-tool user-guide --lang zh-TW
```
預設英文，系統瀏覽器開本地 HTML。缺檔／瀏覽器失敗寫 stderr，回傳 1；Parser 錯誤回傳 2。
不接受機器輸出或儀器選項。


離線顯示靜態工具身分與 Worker 協定相容性：

```powershell
.\.venv\Scripts\scopes-tool.exe manifest --json
```
`manifest` 完全離線，不建 VISA ResourceManager、不探索／連儀器、不啟動 Worker/HTTP、不寫檔。
--json 的 stdout 恰好一物件，含 `tool_id`、`tool_version`、Worker `schema_versions` 與
`compatibility_policy`，供 Orchestrator 在任何 Runtime Session 前識別執行檔。

不接觸硬體即可顯示 Core 註冊型號能力：

```powershell
.\.venv\Scripts\scopes-tool.exe capabilities --json
.\.venv\Scripts\scopes-tool.exe capabilities --model keysight-dsox2004a --json
```
`capabilities` 同樣離線，只讀 Core Registry 並回報標準身分與 Profile，不偵測 Live。
省略 --model 用預設 keysight-dsox4024a。未知／未註冊／歧義 ID 回傳 Usage Code 2，不退回其他型號。
Payload 見 [Scopes CLI JSONL Contract](../contracts/scopes-cli-jsonl-contract.md)。

列出所選 Backend 回報 VISA Resource：

```powershell
.\.venv\Scripts\scopes-tool.exe list-resources
```
僅被動 Discovery，儀器不可達仍可能出現。一般 list-resources 不開列出 Resource 或送 SCPI。

只列可開啟且可查 `*IDN?` 的 Resource：

```powershell
.\.venv\Scripts\scopes-tool.exe list-resources --live-only
```
此操作開啟每個列出 Resource 並送 `*IDN?`；無法開啟或不回應 `*IDN?` 的 Resource 會省略。
加 `--log-scpi` 可顯示每次 Live Discovery 的驗證 Query。

ASRL/RS-232 Discovery 採盡力而為且有界限 1000 ms Open/Query，避免過期 Port 阻止後續 USB/TCPIP。
此相容檢查僅 Discovery，不代表 Runtime 支援完整 RS-232 擷取／控制。

僅 ASRL Live Discovery，可依特定 Adapter／儀器設定 Serial Termination：

```powershell
.\.venv\Scripts\scopes-tool.exe list-resources --live-only --serial-read-termination CRLF --serial-write-termination NONE
```
接受 CRLF、LF、CR、NONE；省略保留 PyVISA Session 屬性，明確 NONE 設對應屬性為 None。

在目前 PowerShell Session 一次設定操作者選定 Live Resource：

```powershell
$env:SCOPES_TOOL_RESOURCE = "USB0::...::INSTR"
```
後續 Live 範例假設此環境變數已設定；請以操作者選定 Resource 取代佔位符。

驗證一個 Resource 能否開啟並回應 `*IDN?`：

```powershell
.\.venv\Scripts\scopes-tool.exe identify --resource "$env:SCOPES_TOOL_RESOURCE"
```
手動實機檢查可加 --log-scpi 顯示 SCPI Log：

```powershell
.\.venv\Scripts\scopes-tool.exe identify --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
```
讀取一筆 System Error Queue：

```powershell
.\.venv\Scripts\scopes-tool.exe check-error --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
```
Drain System Error Queue，直到無錯或達讀取上限：

```powershell
.\.venv\Scripts\scopes-tool.exe check-error --resource "$env:SCOPES_TOOL_RESOURCE" --all --log-scpi
```
以 Dry-run/Simulate 使用低風險系統／狀態命令：

```powershell
.\.venv\Scripts\scopes-tool.exe system-clear-status --dry-run --json
.\.venv\Scripts\scopes-tool.exe system-opc --query --simulate --json
.\.venv\Scripts\scopes-tool.exe system-status-byte --query --simulate --json
.\.venv\Scripts\scopes-tool.exe system-standard-event --query --simulate --json
.\.venv\Scripts\scopes-tool.exe system-operation-status --query --simulate --json
.\.venv\Scripts\scopes-tool.exe system-options --query --simulate --json
```
`system-clear-status` 送 `*CLS`，無命令專屬參數；其他五者唯讀且需明確 --query，
依序送 `*OPC?`、`*STB?`、`*ESR?`、`:OPERegister:CONDition?`、`*OPT?`。
Register 保留 raw，回傳整數 value 與由低到高 Set Bit Index。
Options 保留 raw 並以逗號拆分去空白；0 回應仍 raw: "0" 且 options 含 "0"。

`system-standard-event` 是會消耗事件的 Read：`*ESR?` 依 SCPI 行為清除其回傳事件。
`system-operation-status` 使用 `:OPERegister:CONDition?`，刻意不支援 `:RSTate?`。
讀取或 Drain `:SYSTem:ERRor?` 請用 `check-error`；這些命令不取代它，CLI 每個命令仍保留正常的一筆 System Error Post-check。

使用共用 Core/CLI/Simulator/Worker 路徑，不新增 WebUI Runtime 行為。

<a id="safe-cleanup-profiles"></a>

### Safe Cleanup Profile

`cleanup` 清除一般自動化殘留，不做完整 Reset。
預設 `minimal` 清 Status/Transient Display Data、用 `*OPC?` 等待並做一次最終 Error Check。
`safe` 另關 DVM、Search、Demo Output，清除支援的主要 Annotation。
不支援 Step 會略過並回報；WGEN 刻意回報 `wgen_not_implemented`。

```powershell
.\.venv\Scripts\scopes-tool.exe cleanup --profile minimal --dry-run --json
.\.venv\Scripts\scopes-tool.exe cleanup --profile safe --simulate --json
```
絕不送 `*RST`、`:SYSTem:PRESet`、Autoscale，不重設 Channel/Timebase/Trigger。
Worker /command 經既有 CLI 接受相同命令與可選 profile。

送基本擷取控制：

```powershell
.\.venv\Scripts\scopes-tool.exe stop-acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
.\.venv\Scripts\scopes-tool.exe run --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
.\.venv\Scripts\scopes-tool.exe single --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
```
Library `stop()`、`run()`、`single()` 各只送一條 SCPI；CLI 另透明查一筆
`:SYSTem:ERRor?` 並顯示結果，查詢會從儀器錯誤佇列移除該項目。

啟動一次 Single 並等待觸發完成：

```powershell
.\.venv\Scripts\scopes-tool.exe single-wait --resource "$env:SCOPES_TOOL_RESOURCE"
.\.venv\Scripts\scopes-tool.exe single-wait --simulate --json
.\.venv\Scripts\scopes-tool.exe single-wait --dry-run --json --force-trigger-on-timeout
```
single-wait 送 `:SINGle` 後用既有有限 Operation Condition 等待。
預設逾時 5000 ms、間隔 100 ms、Force-on-timeout 關。
--trigger-timeout-ms/--trigger-poll-interval-ms 須正數，間隔不可超過逾時。
--force-trigger-on-timeout 使用既有條件式 `:TRIGger:FORCe` 路徑。
結構化結果用既有 Trigger-wait 欄位，不產生波形、量測或檔案。

明確強制一次觸發：

```powershell
.\.venv\Scripts\scopes-tool.exe force-trigger --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
.\.venv\Scripts\scopes-tool.exe force-trigger --dry-run --json
.\.venv\Scripts\scopes-tool.exe force-trigger --simulate --json --log-scpi
```
`force-trigger` 是明確改狀態的 One-shot Action：先查 `*IDN?`，送 `:TRIGger:FORCe`，再做一次 `:SYSTem:ERRor?`。
不 Arm Single、不等 Trigger/Acquisition Completion、不 Capture；不改 Timebase、Acquisition Points、Record Length、Acquisition Mode、Sample-rate Mode、Waveform Points/Format、Display、VISA Timeout、Trigger Source/Level/Slope/Sweep 或 Return-to-local。
不能與 `capture`、`measure`、`doctor`、`smoke`、`acquisition-check`、`single`、`run`、`stop-acquisition`、`autoscale`、`setup-save`、`setup-recall` 合併。
Worker `/command` 僅透過明確 `force-trigger` 與 `arguments: {}` 開放。
Triggered Capture 整合只透過明確 `capture --wait-trigger` 選項；獨立命令不變。

使用完整 Trigger Force 拼法以相容 DSO-X 4000X 韌體 07.20。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command force-trigger --arguments-json "{}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command single-wait --arguments-json '{"trigger_timeout_ms":5000,"trigger_poll_interval_ms":100,"force_trigger_on_timeout":false}' --json
```
設定／查詢擷取類型與平均次數：

```powershell
.\.venv\Scripts\scopes-tool.exe acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --type normal --log-scpi
.\.venv\Scripts\scopes-tool.exe acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --type average --count 16 --log-scpi
.\.venv\Scripts\scopes-tool.exe acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --type high_resolution --log-scpi
.\.venv\Scripts\scopes-tool.exe acquisition --resource "$env:SCOPES_TOOL_RESOURCE" --type peak --log-scpi
```
`acquisition` 先查 `*IDN?`，只送要求的 `:ACQuire:TYPE` 與選填 `:ACQuire:COUNt`，再做一次 `:SYSTem:ERRor?`。
`--query` 讀 Type 與 Average Count。`--count` 僅 Average Mode，可用 2–65536；在開連線或改狀態 SCPI 前驗證，無效 Count 不改 Type。
Type Alias 為 `norm`、`aver`、`avg`、`high-resolution`、`hresolution`、`hres`、`peak_detect`、`peak-detect`。
不改 Timeout Default、Trigger Wait Strategy、Acquisition Mode、Run/Stop 或 Return-to-local。

查目前類比取樣率：

```powershell
.\.venv\Scripts\scopes-tool.exe sample-rate --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```
查最大類比取樣率：

```powershell
.\.venv\Scripts\scopes-tool.exe sample-rate --resource "$env:SCOPES_TOOL_RESOURCE" --query --maximum --log-scpi
```
`sample-rate` 僅 Query，要求 `--query`。先查 `*IDN?`，再送 `:ACQuire:SRATe?`；提供 `--maximum` 時改送 `:ACQuire:SRATe? MAXimum`，最後做一次 `:SYSTem:ERRor?`。
Readback 以 NR3 Number 解析，以 Hz 回報並保留 Raw。
Maximum JSON 含 `query_kind: "maximum"`、`maximum_sample_rate_hz`。
不改 Timebase、Acquisition Points、Record Length、Acquisition Mode、Sample-rate Auto/Manual、Waveform Points、Trigger、VISA Timeout 或 Return-to-local。
Short Query Form 用於 DSO-X 4000X 韌體 07.20 相容性。

Worker 同樣要求明確唯讀意圖：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command sample-rate --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command sample-rate --arguments-json "{\"query\":true,\"maximum\":true}" --json
```
查目前類比擷取點數：

```powershell
.\.venv\Scripts\scopes-tool.exe acquisition-points --query --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
```
`acquisition-points` 僅 Query，要求 `--query`。先查 `*IDN?`，送 `:ACQuire:POINts?`，再做一次 `:SYSTem:ERRor?`。
回應解析為目前類比 Acquisition Points 整數並保留 Raw。
不設定 Acquisition Points、Record Length、Acquisition Mode、Timebase、Sample-rate、Trigger、Waveform Format/Points、VISA Timeout 或 Return-to-local。
`acquisition-points --query` 與控制傳輸 Point Count 的 `capture --points` 不同。

Worker 同樣要求明確唯讀意圖：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command acquisition-points --arguments-json "{\"query\":true}" --json
```
查目前類比 Record Length：

```powershell
.\.venv\Scripts\scopes-tool.exe record-length --query --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
```
`record-length` 僅 Query，要求 `--query`，限 4000X Profile。先查 `*IDN?`，送 `:ACQuire:RLENgth?`，再做一次 `:SYSTem:ERRor?`。
2000X/3000X 在 Record-length SCPI 前回報 Unsupported。回應解析為目前類比 Record Length 整數並保留 Raw。
不設定 Record Length、Acquisition Points/Mode、Timebase、Sample-rate、Trigger、Waveform Format/Points、VISA Timeout 或 Return-to-local。
`record-length --query` 與控制傳輸 Points 的 `capture --points` 不同。

Worker 同樣要求明確唯讀意圖：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command record-length --arguments-json "{\"query\":true}" --json
```
查詢或明確設定 Segmented Memory：

```powershell
.\.venv\Scripts\scopes-tool.exe segmented-memory --query --simulate --json
.\.venv\Scripts\scopes-tool.exe segmented-memory --query --dry-run --json
.\.venv\Scripts\scopes-tool.exe segmented-memory --enable --segments 25 --simulate --json
.\.venv\Scripts\scopes-tool.exe segmented-memory --disable --dry-run --json
.\.venv\Scripts\scopes-tool.exe segmented-memory --resource "$env:SCOPES_TOOL_RESOURCE" --query --json --log-scpi
```
segmented-memory 在註冊 Keysight 2000X/3000X/4000X 提供 Query、Enable/Count、Disable。
只有 Segmented Mode 查設定／已取得 Count，已取得非零才查 Index/Time Tag。
Enable 先查 `:ACQuire:TYPE?`，Average 在任何分段寫入前拒絕，再設 Mode/Count。
2000X 2–250，3000X/4000X 2–1000，實際上限可能依記憶深度較低。
Disable 只送 `:ACQuire:MODE RTIMe`，不重設 Count。不啟動擷取、取波形或輸出。
可能需 SGM 選配／授權，能力不宣稱已安裝。

有限次 Segmented Capture，各 Segment 匯出主機 CSV：

```powershell
.\.venv\Scripts\scopes-tool.exe segmented-capture --channel 1 --segments 2 --points 1000 --format byte --timeout-ms 30000 --poll-interval-ms 100 --output-dir data\segmented_test --json --simulate
.\.venv\Scripts\scopes-tool.exe segmented-capture --channel 1 --segments 2 --dry-run --json
```
segmented-capture 支援單類比通道、BYTE/WORD、有限逾時輪詢與既有解碼。
--timeout-ms 為等要求分段就緒匯出的整體期限，--poll-interval-ms 為系列專屬間隔；
每輪以剩餘期限作暫時 VISA Timeout。

2000X/3000X 送 `:SINGle` 後輪詢 `:WAVeform:SEGMented:COUNt?`，直到取得要求的 Segment Count。

4000X 輪詢 `:OPERegister:CONDition?`，連續兩次 Ready 後查 `:WAVeform:SEGMented:COUNt?` 確認數量，再匯出。
Ready 要求兩個相隔 `--poll-interval-ms` 的 Sample 都 RUN Bit Clear、Remote-interface-enabled Bit Set；任何非 Ready 會重設連續次數。
WAIT TRIG Bit 不必 Clear。Readiness Timeout 不查 Acquired Count，也不嘗試部分匯出。

任何 Segmented-capture SCPI Read Timeout 後，不再對該 Session 送 SCPI，保留已完成 CSV、Manifest、`scpi.log`。
流程只送一次 `:SINGle`，依序選取 Ready Segment、查 Time Tag，每次成功 Transfer 後立即寫 `segment_0001.csv`、`segment_0002.csv` 等。
CSV 欄位依 Channel Unit 使用 `_v`/`_a`；目錄另含共用 `manifest.json`（Schema Version `2` 與頂層 `vertical_unit`）、`scpi.log`。
Timeout 或後續錯誤以非零結束，保留完整 CSV，記錄 `partial`/`failed`。
不 Force Trigger、不停用 Segmented、不還原、不合併 CSV、不做儀器 Save/Export。
Common v3 Worker 透過嚴格 `segmented-capture` 契約提供相同 Series-specific Polling 與 Read-timeout 語義。

Worker 僅接受下列精確 Arguments 物件：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command segmented-memory --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command segmented-memory --arguments-json "{\"enable\":true,\"segments\":25}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command segmented-memory --arguments-json "{\"disable\":true}" --json
```
執行擷取設定驗證並寫報告目錄：

```powershell
.\.venv\Scripts\scopes-tool.exe acquisition-check --dry-run --json --model keysight-dsox4034a
.\.venv\Scripts\scopes-tool.exe acquisition-check --simulate --json --model keysight-dsox4034a --output-dir .tmp_tests\acquisition_check
.\.venv\Scripts\scopes-tool.exe acquisition-check --resource "$env:SCOPES_TOOL_RESOURCE" --json --log-scpi
```
`acquisition-check` 執行驗證順序 `query -> normal -> average count 16 -> query -> high_resolution -> peak ->
final query`；Capability 不支援的 Mode 記為 Skipped，不送儀器。
預設將 `report.json`、`scpi.log` 寫入 `data/hardware_acquisition/YYYY-MM-DD-HH-mm-ss`，可用 `--output-dir` 指定。
`--average-count N` 可覆寫預設 16。成功後刻意留在 `peak`，保持明確命令順序，避免隱藏 Restore Write。

開／關／查類比通道顯示：

```powershell
.\.venv\Scripts\scopes-tool.exe channel-display --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --on --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-display --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-display --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --off --log-scpi
```
查所有類比通道精簡唯讀摘要：

```powershell
.\.venv\Scripts\scopes-tool.exe channel-summary --resource "$env:SCOPES_TOOL_RESOURCE" --json --log-scpi
```
channel-summary 彙總有效 Profile 的通道／探棒設定，只查不改，不含 Digital/MSO 或延伸 Probe Inventory。

Worker `/command` 接受空 Arguments 的 `channel-summary`，保留相同唯讀 `result.channels` 結構。

`channel-display` 先查 `*IDN?`，依偵測 Model 驗證 Channel，再送 Display Command。
印出要求的變更或 Query，最後做一次 `:SYSTem:ERRor?`。`--query` 只讀 `:CHANnel<n>:DISPlay?`，不應改畫面。

設／查通道 Vertical Scale：

```powershell
.\.venv\Scripts\scopes-tool.exe channel-scale --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --volts-per-division 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-scale --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```
設／查通道 Vertical Offset：

```powershell
.\.venv\Scripts\scopes-tool.exe channel-offset --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --volts 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-offset --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```
Scale 為正有限 V/div，Offset 為有限 Volt。兩者先查 `*IDN?`，依偵測 Model 驗證 Channel，最後做一次 `:SYSTem:ERRor?`。

設／查通道 Input Coupling：

```powershell
.\.venv\Scripts\scopes-tool.exe channel-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --coupling dc --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```
設／查 Probe Attenuation Ratio：

```powershell
.\.venv\Scripts\scopes-tool.exe channel-probe --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --ratio 10 --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-probe --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```
開／關／查 Bandwidth Limit：

```powershell
.\.venv\Scripts\scopes-tool.exe channel-bandwidth-limit --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --on --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-bandwidth-limit --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-bandwidth-limit --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --off --log-scpi
```
Coupling 為 `ac`/`dc`；Probe Ratio 必須正有限；Bandwidth Limit 為每 Channel On/Off。
先查 `*IDN?` 驗證 Channel，最後做一次 `:SYSTem:ERRor?`。

設／查額外通道設定：

```powershell
.\.venv\Scripts\scopes-tool.exe channel-impedance --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --impedance one-meg --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-impedance --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --impedance fifty --allow-50-ohm --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-impedance --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-invert --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --on --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-invert --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-range --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --volts-full-scale 4 --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-range --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-units --resource "$env:SCOPES_TOOL_RESOURCE" --channel 4 --units amp --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-units --resource "$env:SCOPES_TOOL_RESOURCE" --channel 4 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-units --resource "$env:SCOPES_TOOL_RESOURCE" --channel 4 --units volt --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-vernier --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --off --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-vernier --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-probe-skew --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --seconds 1e-9 --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-probe-skew --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```
先查 `*IDN?`、依偵測 Model 驗證 Channel，只送要求的命令／Query，再做一次 `:SYSTem:ERRor?`。
`channel-range --volts-full-scale` 必須正有限；`channel-probe-skew --seconds` 必須有限且在 `-100e-9..100e-9`。
Units 為 `volt`/`amp`，Impedance 為 `one-meg`/`fifty`。
設定 `fifty` 要在開 Backend 前明確給 `--allow-50-ohm`；只支援 DSO-X 3000X/4000X。
2000X 僅 one-meg，即使給 `--allow-50-ohm`，偵測 2000X 後也會在 `*IDN?` 之後、`:CHANnel<n>:IMPedance FIFTy` 之前拒絕。

`channel-units --units amp` 把選定 Channel 垂直單位改為 Ampere；以 `--query` 讀回、`--units volt` 還原 Volt。
不會把 Voltage Probe 變 Current Probe，也不做 Host Voltage-to-current Conversion；請設定符合所接 Current Probe 的 Probe Ratio。
Waveform CSV 依 Voltage/Current 使用 `_v`/`_a`，Metadata 回報對應 Vertical Unit。

Worker `/command` 用 CLI 選項去掉前導 Dash 的同名 JSON Key 接受這些進階命令；例如 `channel-range` 用 `volts_full_scale`，不是 `volts`。

設／查通道 Label：

```powershell
.\.venv\Scripts\scopes-tool.exe channel-label --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --text "Input A" --log-scpi
.\.venv\Scripts\scopes-tool.exe channel-label --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --query --log-scpi
```
Label 接受無雙引號／控制字元的可列印 ASCII。送 SCPI 前依型號驗證長度：2000X/3000X 10、4000X 32。
部分儀器可能正規化大小寫，JSON 依 SCPI 解析實際回讀。

開／關／查前面板 Label 顯示：

```powershell
.\.venv\Scripts\scopes-tool.exe display-label --resource "$env:SCOPES_TOOL_RESOURCE" --on --log-scpi
.\.venv\Scripts\scopes-tool.exe display-label --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```
執行共用 Display 單次命令：

```powershell
.\.venv\Scripts\scopes-tool.exe display-clear --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
.\.venv\Scripts\scopes-tool.exe display-persistence --resource "$env:SCOPES_TOOL_RESOURCE" --mode minimum --log-scpi
.\.venv\Scripts\scopes-tool.exe display-persistence --resource "$env:SCOPES_TOOL_RESOURCE" --seconds 1.0 --log-scpi
.\.venv\Scripts\scopes-tool.exe display-persistence --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe display-intensity --resource "$env:SCOPES_TOOL_RESOURCE" --value 75 --log-scpi
.\.venv\Scripts\scopes-tool.exe display-intensity --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe display-vectors --resource "$env:SCOPES_TOOL_RESOURCE" --on --log-scpi
.\.venv\Scripts\scopes-tool.exe display-vectors --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```
先查 `*IDN?`，送指定 Display Command/Query，再做一次 `:SYSTem:ERRor?`。
`display-clear` 清 Waveform Display Data 並重設相關量測。
Persistence 接受 `minimum`、`infinite` 或 `0.1`–`60.0` 有限秒數；Intensity 接受 `0`–`100` 整數。
`display-vectors` 只開放 Query 與 ON，不含 OFF；共同命令集不支援 `display-persistence-clear`。

設／清／查 Annotation：

```powershell
.\.venv\Scripts\scopes-tool.exe annotation --resource "$env:SCOPES_TOOL_RESOURCE" --on --text "Run note" --color white --background opaque --log-scpi
.\.venv\Scripts\scopes-tool.exe annotation --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe annotation --resource "$env:SCOPES_TOOL_RESOURCE" --model keysight-dsox4024a --slot 2 --text "Run note" --x 10 --y 20 --log-scpi
```
`annotation --query` 不能合用 Setter；非 Query 至少需一個 Setter/Action。
`--clear` 送空文字，不能與 `--text` 合用。
2000X/3000X 使用未編號 `:DISPlay:ANNotation`，不送／查 X/Y；JSON 仍含 `x: null`、`y: null`。
4000X 使用 `:DISPlay:ANNotation<n>` Slot 1–10，先驗證 `--x`（0–800）與 `--y`（0–480）才送 `:X1Position`/`:Y1Position`，避免 Y 無效卻已寫 X。
Background 為 `opaque`、`inverted`、`transparent`；Color 為 `ch1`、`ch2`、`ch3`、`ch4`、`dig`、`math`、`ref`、`marker`、`white`、`red`。
Text 最多 254 個可列印 ASCII，不可含雙引號／控制字元。各種值形式不同：

- CLI Alias：white、marker、transparent。
- SCPI Token：WHITE、MARKer、OPAQ。
- Query 標準 Enum：WHITE、MARK、DIG、OPAQ、TRAN。

Query 用標準 SCPI Enum 保留儀器語義，WHIT 等縮寫正規化 WHITE；Background 為 OPAQ/INV/TRAN。

Worker /command 亦接受，參數名與 CLI 相同但去前導橫線。

設／查 Timebase Scale：

```powershell
.\.venv\Scripts\scopes-tool.exe timebase-scale --resource "$env:SCOPES_TOOL_RESOURCE" --seconds-per-division 0.001 --log-scpi
.\.venv\Scripts\scopes-tool.exe timebase-scale --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```
設／查 Timebase Position：

```powershell
.\.venv\Scripts\scopes-tool.exe timebase-position --resource "$env:SCOPES_TOOL_RESOURCE" --seconds 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe timebase-position --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```
設／查 Timebase Reference：

```powershell
.\.venv\Scripts\scopes-tool.exe timebase-reference --resource "$env:SCOPES_TOOL_RESOURCE" --reference center --log-scpi
.\.venv\Scripts\scopes-tool.exe timebase-reference --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```
Timebase Scale 為正有限 s/div；Position 為有限秒數。
TBS2074 的 `timebase-position` 先讀 Horizontal Delay Mode，要求 `ON`，再使用原生 Delay Time 秒數。
`OFF` 時不改 Mode 而失敗，也不把原生 Percent Position 換算成秒。
TBS2074 Simulator 預設 Delay Mode `ON`；實機仍須符合此前置條件，Scopes Tool 不開放或自動啟用該 Mode。

Timebase Reference 接受 `left`、`center`、`right`。先查 `*IDN?` 確認 Model 可識別，最後做一次 `:SYSTem:ERRor?`。

以標準 trigger-edge 設／查類比 Source/Level/Slope：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --level 0.25 --slope positive --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-edge --simulate --json --model keysight-dsox4024a --source-channel 1 --level 0.5 --slope positive
```
Configure 送 `:TRIGger:MODE EDGE`，再設定 Source、Level、Slope。
Slope 為 `positive`、`negative`、`either`、`alternate`；Source 僅 DSO 類比 Channel，Level 為有限 Volt。
不包含 External、Digital/MSO、Coupling/Reject 或廣泛 Trigger Tree。舊名 `edge-trigger` 不接受。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge --arguments-json "{\"source_channel\":1,\"level\":0.5,\"slope\":\"positive\"}" --json
```
`trigger-edge` Worker JSON 僅接受 `query`、`source_channel`、`level`、`slope`。
Alias 與未知欄位在 Enqueue、Artifact、Simulator/VISA Open 或 SCPI 前拒絕。

僅設／查 Edge Source 的標準 trigger-edge-source：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-source --dry-run --json --model keysight-dsox2004a --source-channel 1
.\.venv\Scripts\scopes-tool.exe trigger-edge-source --simulate --json --model keysight-dsox3024a --source external
.\.venv\Scripts\scopes-tool.exe trigger-edge-source --simulate --json --model keysight-dsox4024a --source line
.\.venv\Scripts\scopes-tool.exe trigger-edge-source --simulate --json --model keysight-dsox4034a --query
```
必須精確選一項：`--query`、`--source-channel <int>`、`--source external|line`。
類比對應 `:TRIGger:EDGE:SOURce CHANnel<n>`；External 為 `:TRIGger:EDGE:SOURce EXTernal`；AC Line 為 `:TRIGger:EDGE:SOURce LINE`；Query 送 `:TRIGger:EDGE:SOURce?`。
不送 `:TRIGger:MODE EDGE`，不改 Level、Slope、Coupling、Reject、Sweep、Noise Reject、HF Reject、Holdoff 或 Acquisition。

與組合 Source/Level/Slope 的 trigger-edge 不同。Source-only 為四個 Keysight 型號手冊共用
CHANnel<n>/EXTernal/LINE，類比通道依 Profile 檢查。不設定 External Level/Range、WGEN、WMOD、Digital。
Query 保留 raw_source，只正規化 Analog/External/Line；NONE/WaveGen/Digital/未知／不支援
回讀的正規化欄位為 null，不僅因此失敗。

Worker 僅接受標準 JSON：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-source --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-source --arguments-json "{\"source_channel\":1}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-source --arguments-json "{\"source\":\"external\"}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-source --arguments-json "{\"source\":\"line\"}" --json
```
Worker 必須精確一項操作，Source 為小寫 `external`/`line`，Analog Channel 為 Profile 範圍內的非 Boolean 整數。
Query/Configure 混合、`query: false`、Alias、CamelCase/未知 Key、大寫或不支援 Source 均在 Enqueue、Artifact、Simulator/VISA Open 或 SCPI 前拒絕。

獨立 Edge Slope/Analog Level 兩命令。trigger-edge-slope 恰需 --query 或
--slope positive|negative|either|alternate：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-slope --dry-run --json --model keysight-dsox2004a --slope positive
.\.venv\Scripts\scopes-tool.exe trigger-edge-slope --simulate --json --model keysight-dsox4034a --query
```
Configure 映射：`positive` → `:TRIGger:EDGE:SLOPe POSitive`、`negative` → `NEGative`、`either` → `EITHer`、`alternate` → `ALTernate`；Query 送 `:TRIGger:EDGE:SLOPe?`。
Query 正規化文件規定的 Short/Long Readback（`POS`、`NEG`、`EITH`、`ALT`），保留 `raw_slope`；未知值的 `slope` 為 null。
不查／改 Trigger Mode，也不轉向 TV Polarity。

`trigger-edge-level` 一律要求 `--source-channel <int>`，精確選一個 `--query` 或 `--level-volts <number>`：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-level --dry-run --json --model keysight-dsox2004a --source-channel 1 --level-volts 0.5
.\.venv\Scripts\scopes-tool.exe trigger-edge-level --simulate --json --model keysight-dsox4034a --source-channel 2 --query
```
Set 用 `:TRIGger:EDGE:LEVel <level>,CHANnel<n>`，Query 用 `:TRIGger:EDGE:LEVel? CHANnel<n>`，
不使用隱含有效來源形式，不切換 Source。只驗證通道數與有限 Level，動態範圍依目前垂直 Range/Center
由儀器限制；不查 Scale/Offset/Range，不 Clamp。

兩者與同時設定 Mode/Source/Level/Slope 的 `trigger-edge` 不同，沒有 Alias。
`trigger-edge-slope` Worker 為 `{"query":true}` 或 `{"slope":"positive"}`；`trigger-edge-level` 為 `{"query":true,"source_channel":1}` 或 `{"source_channel":1,"level_volts":0.5}`。
Worker 在 Enqueue、Artifact、Simulator/VISA Open 或 SCPI 前拒絕未知／Alias Key、Alias、Query/Configure 混合、大寫或未載 Slope、無效／Boolean Channel、非有限／非數值 Level。
不開放 External、Line、WaveGen、WMOD、Digital/MSO Level。

External Trigger Range 與 External Edge Level 是獨立控制。
`external-trigger-range` 精確接受一個 `--query` 或 `--range-volts <finite-positive-number>`：

```powershell
.\.venv\Scripts\scopes-tool.exe external-trigger-range --dry-run --json --model keysight-dsox2004a --range-volts 8.0
.\.venv\Scripts\scopes-tool.exe external-trigger-range --simulate --json --model keysight-dsox4034a --query
```
只送 `:EXTernal:RANGe <range>` 或 `:EXTernal:RANGe?`；不查／改 `:EXTernal:PROBe`、Edge Source/Mode/Level 或 Acquisition。
本地只驗證正有限值，不限制為 1.6/8 V。手冊記載 1:1 Probe 時 2000X/3000X 為 8 V，4000X 為 1.6/8 V。
因不檢查 Probe Attenuation，實際 Model/Firmware/Probe/Hardware Range 由儀器與 Error Queue 決定。
Simulator 僅驗證正有限值，不模擬全部 Model/Probe Range Rejection。

`trigger-edge-external-level` 精確接受一個 `--query` 或 `--level-volts <finite-number>`：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-external-level --dry-run --json --model keysight-dsox2004a --level-volts 0.5
.\.venv\Scripts\scopes-tool.exe trigger-edge-external-level --simulate --json --model keysight-dsox4034a --query
```
只送 `:TRIGger:EDGE:LEVel <level>,EXTernal` 或 `:TRIGger:EDGE:LEVel? EXTernal`，
不隱含 Source、不改 Source/Mode、不查／改 External Range，與類比 trigger-edge-level 分開。
本地接受有限正／負／零，不查動態 Range、不 Clamp，由實機限制；兩命令均無 Alias。

`external-trigger-range` Worker 為 `{"query":true}` 或 `{"range_volts":8.0}`；`trigger-edge-external-level` 為 `{"query":true}` 或 `{"level_volts":0.5}`。
Worker 在 Enqueue、Artifact、Simulator/VISA Open 或 SCPI 前拒絕空 Arguments、`query: false`、混合操作、未知／Alias Key、Boolean、非數值／非有限值，以及零／負 External Range。
DSOX2004A/DSOX3024A/DSOX4024A/DSOX4034A 保留既有 Analog/External 限制。

External Input 提供三個共同 DSO-X 2000X/3000X/4000X 獨立命令。
`external-trigger-probe` 精確選 `--query` 或 `--attenuation <finite-positive-number>`，只送 `:EXTernal:PROBe?` 或 `:EXTernal:PROBe <attenuation>`。
不套共用硬體 Attenuation Range；Probe/Model/Firmware/AutoProbe 接受範圍由儀器／Error Queue 決定。

`external-trigger-units` 精確選 `--query`、`--units volts`、`--units amps`，只送 `:EXTernal:UNITs?`、`:EXTernal:UNITs VOLT`、`:EXTernal:UNITs AMPere`。
`external-trigger-settings` 僅 Query，要求明確 `--query`，只送一次 `:EXTernal?`，不是四個 Query。
JSON 保留 `raw_response`，正規化已知 Probe Attenuation、Range、Units、BWL。
Units Readback 接受 `VOLT`、`AMP`、`AMPere`；保留未知 Readback，不將它視為 Configure Support。

`external-trigger-probe` Worker 為 `{"query":true}` 或 `{"attenuation":10}`；`external-trigger-units` 為 `{"query":true}` 或 `{"units":"volts"}`；`external-trigger-settings` 只接受 `{"query":true}`。
空 Arguments、`query: false`、混合操作、Alias、未知 Key、錯誤 JSON Type、非有限值、過大整數在 Enqueue、Artifact、Simulator/VISA Open 或 SCPI 前拒絕。
不設定 External BWLimit（Aggregate BWL 僅相容性 Readback；共同 HF Rejection 用 `trigger-hf-reject`）、不偵測 AutoProbe/Probe Type、不換算 Range/Level、不改 Trigger Source/Mode、不控制 Acquisition。
真實韌體可能連動這些設定，但程式不送補償 Write；Simulator 分別保留 Probe、Units、Range、External Edge Level，以發現意外副作用。

設／查共用觸發設定：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-sweep --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-sweep --resource "$env:SCOPES_TOOL_RESOURCE" --mode auto --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-sweep --resource "$env:SCOPES_TOOL_RESOURCE" --mode normal --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-noise-reject --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-noise-reject --resource "$env:SCOPES_TOOL_RESOURCE" --enabled true --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-noise-reject --resource "$env:SCOPES_TOOL_RESOURCE" --enabled false --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-hf-reject --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-hf-reject --resource "$env:SCOPES_TOOL_RESOURCE" --enabled true --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-hf-reject --resource "$env:SCOPES_TOOL_RESOURCE" --enabled false --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-sweep --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-noise-reject --simulate --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-hf-reject --simulate --json --model keysight-dsox4024a --enabled true
```
`trigger-sweep` 使用 `:TRIGger:SWEep`，只接受 `--mode auto`/`--mode normal`；Query 送 `:TRIGger:SWEep?`，JSON 回報正規化 `mode` 與 `raw_value`。
`trigger-noise-reject` 用 `:TRIGger:NREJect`，`trigger-hf-reject` 用 `:TRIGger:HFReject`。
兩者只接受 `--enabled true`/`--enabled false`；Query 將 `0`/`1` 正規化為 Boolean `enabled` 並保留 `raw_value`。
各命令拒絕 `--query` 與 Configure 混用，也拒絕非 Query 卻未提供 Configure 選項。

明確單次寫入／Query，不改 Holdoff、不新增 Generic API，不 Run/Stop/Single/Force/Wait/Capture，
不改 WebUI Runtime。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-sweep --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-sweep --arguments-json "{\"mode\":\"normal\"}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-noise-reject --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-noise-reject --arguments-json "{\"enabled\":false}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-hf-reject --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-hf-reject --arguments-json "{\"enabled\":true}" --json
```
`trigger-sweep` Worker 僅接受 `query` 或 `mode`；`trigger-noise-reject`/`trigger-hf-reject` 僅接受 `query` 或 `enabled`。
`query` 必須精確 JSON `true`，`enabled` 必須 JSON Boolean。
未知欄位與 `sweep`、`sweep_mode`、`trigger_sweep`、`noise_reject`、`nreject`、`nrej`、`state`、`on`、`enable`、`hf_reject`、`hfreject`、`high_frequency_reject` 等 Alias 在 Enqueue、Artifact、Simulator/VISA Open 或 SCPI 前拒絕。

設／查固定 Holdoff：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --query --json
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --seconds 1e-6 --json
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --dry-run --json --model keysight-dsox4024a --seconds 1e-6
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --simulate --json --model keysight-dsox4024a --query
```
`trigger-holdoff --seconds` 明確改狀態。
4000X 先以 `:TRIGger:HOLDoff:RANDom OFF` 停用 Random Holdoff，再送 `:TRIGger:HOLDoff <seconds>`；2000X/3000X 只送 `:TRIGger:HOLDoff <seconds>`。
TBS2074 用 `TRIGger:A:HOLDOff:TIMe`；B1 Tektronix 用 `TRIGger:MAIn:HOLDOff:VALue`。
TBS2074 範圍 20 ns–8 s；TDS2024B/TBS1052B 500 ns–10 s；Keysight 40 ns–10 s。
`doctor`、`smoke`、`acquisition-check` 從不執行 `trigger-holdoff`。

`trigger-holdoff` Worker 僅接受 `{"query": true}` 或 `{"seconds": 0.000001}`。
空 Arguments、`query: false`、Query+Seconds、String/Boolean/null Seconds、未知欄位、Holdoff Mode Alias 在 Enqueue、Artifact、Simulator/VISA Open 或 SCPI 前拒絕。
不支援 Random 或 Minimum/Maximum Holdoff 命令。

以標準 trigger-edge-coupling/trigger-edge-reject 設／查 Keysight Edge Coupling/Reject：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --coupling ac --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --coupling dc --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --coupling lf-reject --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-coupling --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi

.\.venv\Scripts\scopes-tool.exe trigger-edge-reject --resource "$env:SCOPES_TOOL_RESOURCE" --reject off --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-reject --resource "$env:SCOPES_TOOL_RESOURCE" --reject lf-reject --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-reject --resource "$env:SCOPES_TOOL_RESOURCE" --reject hf-reject --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-reject --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```
`trigger-edge-coupling` 用 `:TRIGger:EDGE:COUPling`，只接受 `--coupling ac`、`--coupling dc`、`--coupling lf-reject`。
`trigger-edge-reject` 用 `:TRIGger:EDGE:REJect`，只接受 `--reject off`、`--reject lf-reject`、`--reject hf-reject`。

各命令拒絕 `--query` 與 Configure 混用，非 Query 則必須提供 Configure 選項。

**Coupling 交互影響**：實機改 Coupling 可能改 Reject 回讀，反之亦然。
系統不強制同時設定、不自動還原、不加隱含修正 SCPI；各命令只操作自身設定，模擬器不模擬所有副作用。

**與既有命令區別**：trigger-hf-reject 使用共用 `:TRIGger:HFReject`，
trigger-edge-reject 使用 Edge 專屬 `:TRIGger:EDGE:REJect`；兩者獨立，不互相取代／轉送。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-coupling --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-coupling --arguments-json "{\"coupling\":\"ac\"}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-reject --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-reject --arguments-json "{\"reject\":\"hf-reject\"}" --json
```
`trigger-edge-coupling` Worker 僅接受 `query` 或 `coupling`；`trigger-edge-reject` 僅接受 `query` 或 `reject`。
無效 Input、大寫 Value、未知欄位、Alias Command/Key（如 `edge-trigger-coupling`、`edge-trigger-reject`、`couple`、`reject_mode`、`filter`）在 Enqueue、Artifact、Simulator/VISA Open 或 SCPI 前拒絕。


以標準 trigger-pulse-width 設／查 Keysight Pulse-width：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-pulse-width --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --polarity positive --qualifier less-than --time-seconds 1e-6 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-pulse-width --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --polarity negative --qualifier greater-than --time-seconds 5e-6 --level-volts 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-pulse-width --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --polarity positive --qualifier range --min-time-seconds 1e-6 --max-time-seconds 10e-6 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-pulse-width --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```
`trigger-pulse-width` 透過 `:TRIGger:GLITch...` SCPI 設／查 Keysight Pulse Width。
Configure 改狀態：選 Mode、設類比 Source、選填 Level，再設 Polarity 與 Qualifier。
Range Configure 將 `--max-time-seconds` 映射至第一個 SCPI `RANGe` 參數，`--min-time-seconds` 映射第二個。
Query 保留 Raw Source/Level，容忍目前 Digital、External 或 `NONE` Readback。

Set 僅類比，不 Run/Stop/Single/Force/Wait/Capture，不支援 Pattern/Delay/TV/USB/Serial/Digital/Zone 等其他觸發。
僅手冊類比介面。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-pulse-width --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-pulse-width --arguments-json "{\"channel\":1,\"polarity\":\"positive\",\"qualifier\":\"less_than\",\"time_seconds\":0.000001}" --json
```
以標準 trigger-runt 設／查類比 Runt：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-runt --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --polarity either --qualifier none --low-level-volts -0.5 --high-level-volts 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-runt --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --polarity positive --qualifier greater-than --time-seconds 5e-6 --low-level-volts -0.25 --high-level-volts 0.75 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-runt --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```
`trigger-runt` 使用 `:TRIGger:MODE RUNT`、`:TRIGger:RUNT:*` 與共用 `:TRIGger:LEVel:LOW/HIGH`。
Configure 改狀態：選 Runt、設類比 Source、Low/High Threshold，再設 Polarity/Qualifier。
Qualifier 為 `greater-than`、`less-than`、`none`；只有前兩者送 `:TRIGger:RUNT:TIME`，`none` 拒絕 `--time-seconds`。
Query 先讀 Mode/Source/Polarity/Qualifier/Stored Time，再只對安全解析為 `CHAN<n>`/`CHANnel<n>` 的類比 Source 查 LOW/HIGH。
非類比／未知 Source 保留 JSON，`channel`、`low_level_volts`、`high_level_volts` 為 `null`。

Set 僅類比，不 Run/Stop/Single/Force/Wait/Capture，也不支援 Generic Trigger、Transition、Pattern、
Search、Waveform 或額外 WebUI Runtime 行為。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-runt --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-runt --arguments-json "{\"channel\":1,\"polarity\":\"either\",\"qualifier\":\"none\",\"low_level_volts\":-0.5,\"high_level_volts\":0.5}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-runt --arguments-json "{\"channel\":1,\"polarity\":\"positive\",\"qualifier\":\"greater_than\",\"time_seconds\":0.000005,\"low_level_volts\":-0.25,\"high_level_volts\":0.75}" --json
```
以標準 trigger-transition 設／查類比 Transition：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-transition --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --slope positive --qualifier greater-than --time-seconds 5e-6 --low-level-volts -0.5 --high-level-volts 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-transition --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --slope negative --qualifier less-than --time-seconds 2e-6 --low-level-volts -0.25 --high-level-volts 0.75 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-transition --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
```
`trigger-transition` 使用 `:TRIGger:MODE TRANsition`、`:TRIGger:TRANsition:*` 與共用 `:TRIGger:LEVel:LOW/HIGH`。
Configure 改狀態：選 Mode、設類比 Source、Low/High，再設 Slope/Time/Qualifier。
Slope 為 `positive`/`negative`，Qualifier 為 `greater-than`/`less-than`。
`--time-seconds`、`--low-level-volts`、`--high-level-volts` 必填，Low 必須小於 High。

Query 先讀 Mode、Source、Slope、Qualifier、Transition Time，再只對安全解析為 `CHAN<n>`/`CHANnel<n>` 的類比 Source 查 LOW/HIGH。
非類比／未知 Source 保留 JSON，`channel`、`low_level_volts`、`high_level_volts` 為 `null`。

Set 僅類比，不含 Digital/MSO/External、不加 Alias、不 Run/Stop/Single/Force/Wait/Capture 或 Generic Trigger Tree。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-transition --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-transition --arguments-json "{\"channel\":1,\"slope\":\"positive\",\"qualifier\":\"greater_than\",\"time_seconds\":0.000005,\"low_level_volts\":-0.5,\"high_level_volts\":0.5}" --json
```
以標準 trigger-delay 設／查類比 Edge Then Edge/Delay：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-delay --resource "$env:SCOPES_TOOL_RESOURCE" --arm-channel 1 --arm-slope positive --trigger-channel 2 --trigger-slope negative --time-seconds 1e-6 --count 2 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-delay --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-delay --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-delay --simulate --json --query
```
`trigger-delay` 用 `:TRIGger:MODE DELay` 與 `:TRIGger:DELay:*` 設／查 Keysight Edge Then Edge/Delay。
Configure 改狀態、僅 DSO 類比：設 Arm Source/Slope、Delay Time、Nth Trigger Edge Count、Trigger Source/Slope。
Slope 只有 `positive`/`negative`，拒絕 `pos`、`neg`、`rising`、`falling`、`either`、`alternate`。
`--time-seconds` 為 `4e-9`–`10.0`，`--count` 為至少 `1` 的整數。

Query 讀 `:TRIGger:MODE?`、`:TRIGger:DELay:ARM:SOURce?`、`:TRIGger:DELay:ARM:SLOPe?`、`:TRIGger:DELay:TDELay:TIME?`、`:TRIGger:DELay:TRIGger:COUNt?`、`:TRIGger:DELay:TRIGger:SOURce?`、`:TRIGger:DELay:TRIGger:SLOPe?`。
保留 Raw，容忍 Digital/未知 Source；Configure 不接受 Digital、External、level-volts、Threshold、Source Alias 或 Generic Trigger Tree。
每次 Live/Simulate 都做一次 `:SYSTem:ERRor?`；不整合 Run/Stop/Single/Force-trigger/Wait-trigger/Capture。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-delay --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-delay --arguments-json "{\"arm_channel\":1,\"arm_slope\":\"positive\",\"trigger_channel\":2,\"trigger_slope\":\"negative\",\"time_seconds\":0.000001,\"count\":2}" --json
```
以標準 trigger-setup-hold 設定或查詢類比 Setup/Hold Trigger：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-setup-hold --resource "$env:SCOPES_TOOL_RESOURCE" --clock-channel 1 --data-channel 2 --slope positive --setup-time 5e-9 --hold-time 5e-9 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-setup-hold --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-setup-hold --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-setup-hold --simulate --json --query
```
`trigger-setup-hold` 用 `:TRIGger:MODE SHOLd`、`:TRIGger:SHOLd:*` 設／查 Keysight Setup/Hold。
Configure 改狀態且限 DSO 類比，設 Clock/Data Source、Clock Slope、Setup/Hold Time。
Slope 只 `positive`/`negative`，拒絕 `pos`、`neg`、`rising`、`falling`。
`--setup-time`、`--hold-time` 為正有限秒數，不解析時間後綴。

Query 讀 `:TRIGger:MODE?`、`:TRIGger:SHOLd:SOURce:CLOCk?`、`:TRIGger:SHOLd:SOURce:DATA?`、`:TRIGger:SHOLd:SLOPe?`、`:TRIGger:SHOLd:TIME:SETup?`、`:TRIGger:SHOLd:TIME:HOLD?`。
JSON 保留 Raw Mode/Source/Slope/Time，將 `SHOL`/`SHOLD` 正規化為 `setup-hold`，正規化常見類比 Channel 與 positive/negative Slope。
Digital/未知 Source 保留 Raw，解析類比 Channel 為 null；不因目前 Mode 不是 Setup-hold 而失敗。

Configure 在儀器存取前拒絕部分設定、`--query` 混合 Configure、非整數／超出 Profile Channel、`D0`/`DIG0`/`digital0`/`pod`/`bus` 等 Digital/MSO Alias、未知 Alias、無效 Slope，以及非有限、零、負或非數值時間。
即使 MSO 的 SCPI 支援 Digital，此介面仍不支援 MSO/Digital/External Source。
不提供 Threshold/Level Helper、Run/Stop/Single/Force/Wait-trigger、Capture Integration、Signal-trigger Acquisition 或 Generic Trigger Tree Framework。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-setup-hold --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-setup-hold --arguments-json "{\"clock_channel\":1,\"data_channel\":2,\"slope\":\"positive\",\"setup_time\":0.000000005,\"hold_time\":0.000000005}" --json
```
Worker 使用標準 Key `setup_time`、`hold_time`，對應 CLI `--setup-time`、`--hold-time`。

以標準 trigger-edge-burst 設定或查詢類比 Edge Burst Trigger：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --slope positive --count 3 --idle-time 1e-6 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --slope positive --count 3 --idle-time 1e-6 --level-volts 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --dry-run --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-edge-burst --simulate --json --query
```
`trigger-edge-burst` 用 `:TRIGger:MODE EBURst`、`:TRIGger:EBURst:SOURce`、`:TRIGger:EBURst:SLOPe`、`:TRIGger:EBURst:COUNt`、`:TRIGger:EBURst:IDLE`。
Configure 改狀態且限 DSO 類比，接受 `--source-channel`、`--slope positive|negative`、`--count`、`--idle-time`、選填 `--level-volts`。
提供 `--level-volts` 才在 EBURst 欄位後送 `:TRIGger:EDGE:LEVel <level>, CHANnel<n>`；省略則不寫 Level。

Query 讀 EBURst Mode/Source/Slope/Count/Idle；Source 安全解析為 `CHAN<n>`/`CHANnel<n>` 類比時才讀 Edge Level。
Digital、`NONE`、未知 Source 保留 Raw，不因目前 Source 超出 Configure 子集而失敗。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-burst --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-burst --arguments-json "{\"source_channel\":1,\"slope\":\"positive\",\"count\":3,\"idle_time\":0.000001}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-edge-burst --arguments-json "{\"source_channel\":1,\"slope\":\"positive\",\"count\":3,\"idle_time\":0.000001,\"level_volts\":0.5}" --json
```
Worker 僅接受 query、source_channel、slope、count、idle_time 與選填 level_volts。
不接受 channel/source/edge_count/idle_time_seconds/time_seconds/trigger_level/level Alias；不增加 MSO、Wait 或 Capture 整合。

以標準 trigger-tv 設定或查詢類比 TV Trigger：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-tv --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-tv --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --standard ntsc --mode field1 --polarity negative --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-tv --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --standard ntsc --mode line-field1 --line 20 --polarity negative --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-tv --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 2 --standard pal --mode line-field2 --line 400 --polarity positive --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-tv --dry-run --json --model keysight-dsox4024a --query
.\.venv\Scripts\scopes-tool.exe trigger-tv --simulate --json --query
```
`trigger-tv` 用 `:TRIGger:MODE TV`、`:TRIGger:TV:SOURce`、`:TRIGger:TV:STANdard`、`:TRIGger:TV:MODE`、選填 `:TRIGger:TV:LINE`、`:TRIGger:TV:POLarity` 設／查共同 Keysight TV Trigger。
Configure 改狀態且限 DSO 類比，接受 `--source-channel`、`--standard ntsc|pal|palm|secam`、`--mode field1|field2|all-fields|all-lines|line-field1|line-field2|line-alternate`、`--polarity positive|negative`，`--line` 只在 Line Mode 選填。
不含延伸 Video Standard、UDTV、3000X/4000X 專屬 `LINE` Mode、Digital/MSO、External、USB、NFC、Serial/Bus、Zone Trigger。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-tv --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-tv --arguments-json "{\"source_channel\":1,\"standard\":\"ntsc\",\"mode\":\"field1\",\"polarity\":\"negative\"}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-tv --arguments-json "{\"source_channel\":1,\"standard\":\"ntsc\",\"mode\":\"line-field1\",\"line\":20,\"polarity\":\"negative\"}" --json
```
Worker 僅接受 `query`、`source_channel`、`standard`、`mode`、`line`、`polarity`。
不接受 `channel`、`source`、`tv_source`、`tv_standard`、`trigger_standard`、`tv_mode`、`trigger_mode`、`line_number`、`field`、`pol`、`trigger_polarity`、`polarity_raw`、`sourceChannel`、`source_channel_number` 等 Alias。

以標準 trigger-pattern 設定或查詢類比 ASCII Pattern Trigger：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-pattern --resource "$env:SCOPES_TOOL_RESOURCE" --pattern XXX1 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-pattern --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-pattern --dry-run --json --pattern XXX1
.\.venv\Scripts\scopes-tool.exe trigger-pattern --simulate --json --query
```
`trigger-pattern` 只開放 DSO 類比 ASCII Entered Pattern。Configure 改狀態，送 `:TRIGger:MODE PATTern`、`:TRIGger:PATTern:FORMat ASCii`、`:TRIGger:PATTern "<pattern>"`、`:TRIGger:PATTern:QUALifier ENTered`。
Raw ASCII Pattern 只含 `0`、`1`、`X`，小寫轉大寫，長度符合選定 Profile 類比 Channel 數。
空字串、空白、逗號、引號、`R`、`F`、`0x...` 或其他字元在開儀器前拒絕。

Query 讀 `:TRIGger:MODE?`、`:TRIGger:PATTern:FORMat?`、`:TRIGger:PATTern?`、`:TRIGger:PATTern:QUALifier?`。
JSON 將 `ASC`/`ASCii` 正規化為 `ascii`、`HEX` 為 `hex`、`ENT`/`ENTered` 為 `entered`，保留 Raw Pattern Response、Edge-source、Edge Readback。

不加入 HEX 設定、Digital R/F Edge、Duration/Range、來源／Level 設定、Alias 或 Generic Trigger 操作。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-pattern --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-pattern --arguments-json "{\"pattern\":\"XXX1\"}" --json
```
以標準 trigger-or 設定或查詢類比 OR Trigger：

```powershell
.\.venv\Scripts\scopes-tool.exe trigger-or --resource "$env:SCOPES_TOOL_RESOURCE" --pattern XXXR --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-or --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-or --dry-run --json --pattern XXXR
.\.venv\Scripts\scopes-tool.exe trigger-or --simulate --json --query
```
`trigger-or` 只開放 DSO 類比 `:TRIGger:OR`。Configure 改狀態，送 `:TRIGger:MODE OR` 再送 `:TRIGger:OR "<pattern>"`。
Raw Edge String 只含 `R`（Rising）、`F`（Falling）、`E`（Either）、`X`（Don't care），小寫轉大寫。
空字串、空白、逗號、引號、`0`/`1`、`0x...` 或其他字元在開儀器前拒絕；長度符合註冊 Model 的 Analog-channel Capability。

目前註冊的 Keysight 型號皆有四個類比 Channel，Bit 順序為 CH4、CH3、CH2、CH1。
CH1 Rising 為 XXXR；CH1 Rising 或 CH2 Falling 為 XXFR；任何 Channel 的任意 Edge 為 EEEE。

Query 讀 `:TRIGger:MODE?`、`:TRIGger:OR?`；JSON 保留 `raw_mode`、`raw_pattern`，將常見有／無引號的有效 Readback 正規化為大寫 `pattern`。
不因目前 Mode 不是 OR 而失敗。

不加入 MSO/Digital、Alias、Generic Trigger 或 Run/Stop/Single/Force/Wait/Capture。

Worker 用法：

```powershell
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-or --arguments-json "{\"query\":true}" --json
.\.venv\Scripts\scopes-tool.exe send-command --port 8765 --command trigger-or --arguments-json "{\"pattern\":\"XXXR\"}" --json
```
管理儀器前面板的量測系統：

```powershell
.\.venv\Scripts\scopes-tool.exe measure-clear --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-install --source-channel 1 --item frequency --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-show --on --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-show --query --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-source --source-channel 1 --source2-channel 2 --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-source --query --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-window --window gate --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-window --query --simulate --json
.\.venv\Scripts\scopes-tool.exe measure-menu --simulate --json
```
`measure-install` 設選定類比 Source，送一個非 Query `:MEASure` 安裝支援的簡單量測，不清原清單、不查值，不接受 Pair、參數化或 Power 量測。
`measure-clear` 清已安裝畫面量測。`measure-menu` 開 Measurement 介面（2000X/3000X 為 `:SYSTem:MENU MEASure`，4000X 為 `:DISPlay:SIDebar MEASurements`）。
`measure-show` 只接受 ON/Query，不開放 OFF，因共同 2000X/3000X 行為為量測標記固定顯示。
`measure-source` 接受 Profile 驗證的一或兩個類比 Channel，不接受 Digital、Math/Function、Reference。
`--source-channel <n>` 設 Source1，不一定清既有 Source2；後續 Query 可回 Source1 與保留 Source2，只要 Source1 相符且 Error Queue 乾淨即成功。
需要明確雙 Source Default 時，同時使用 `--source-channel <n>`、`--source2-channel <m>`。Source2 主要用於 Delay/Phase 等雙來源量測。

`measure-window` 接受 `main`、`zoom`、`auto`、`gate`。
`zoom` 要求儀器已顯示 Zoomed Timebase；未顯示時設定 `zoom` 可能回 `-221,"Settings conflict"`。
未知 Zoom 狀態時，`auto` 是較安全可攜選擇。

查詢或設定內建 DVM：

```powershell
.\.venv\Scripts\scopes-tool.exe dvm-enable --enabled true --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-enable --query --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-source --channel 1 --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-source --query --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-mode --mode dc-rms --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-mode --query --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-auto-range --enabled false --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-current --query --simulate --json
.\.venv\Scripts\scopes-tool.exe dvm-query --query --simulate --json
```
公開 Mode 只有 `dc`、`dc-rms`、`ac-rms`，不接受 Alias/大寫。Boolean Configure 只用 `--enabled true|false`。
DVM Source 是 Profile 驗證的類比 Channel。
Current/Aggregate 保留 Raw；Sentinel 或非有限值回 `value: null`、`valid: false` 與 Reason，不造成程式崩潰。
Aggregate `dvm-query` 另含 Source 的標準 Unit（`volt`/`amp`），獨立 `dvm-current` 不含 Unit Metadata。
功能可能依 Option/License，Live Rejection 沿用正常儀器錯誤路徑。

DVM 介面刻意不支援 `dvm-frequency`、`:DVM:FREQuency?`、`:DVM:MODE FREQuency`、獨立 `:COUNter` 子系統、Counter CLI 或 `:MEASure:COUNter`。

Worker 用相同標準值，Query 要求 `{"query": true}`。
未知 Key、Alias、混合 Query/Configure、非 Boolean `enabled`、超出 Profile Channel，在 Enqueue 或 Artifact/Session 建立前拒絕。

查詢或設定內建 Demo 輸出：

```powershell
.\.venv\Scripts\scopes-tool.exe demo-query --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-output --query --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-output --enabled true --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-function --query --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-function --function runt --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-phase --query --simulate --json
.\.venv\Scripts\scopes-tool.exe demo-phase --degrees 90 --simulate --json
```
`demo-output`、`demo-function`、`demo-phase` 精確要求一個 Query 或 Configure。
Function 僅小寫標準名稱，Phase 為 0–360（含）有限值；開 Session 前驗證 Profile Function Support。
Aggregate `demo-query` 保留精確 Raw；未知 Function 回 `function: null`、`function_scpi: null`，Malformed Output/Phase 依正常錯誤處理失敗。

共同 Core Function：`sine`、`noisy`、`phase`、`lf-sine`、`am`、`rf-burst`、`fm-burst`、`harmonics`、`coupling`、`ringing`、`single`、`clock`、`runt`、`transition`、`setup-hold`、`mso`、`burst`、`glitch`、`edge-then-edge`、`i2c`、`uart`、`spi`、`can`、`lin`。
3000X/4000X 另有 `i2s`、`can-lin`、`flexray`、`arinc`、`mil`、`mil2`；其他 4000X 專屬 DEMO Function 排除於正式 Capability 外。

Demo 是選配功能，使用正常的命令後錯誤檢查，與 WGEN 分開；不加入 WebUI Runtime 控制。

查詢或設定 Waveform Generator：

```powershell
.\.venv\Scripts\scopes-tool.exe wgen-query --simulate --json
.\.venv\Scripts\scopes-tool.exe wgen-output --enabled true --simulate --json
.\.venv\Scripts\scopes-tool.exe wgen-output --query --simulate --json
.\.venv\Scripts\scopes-tool.exe wgen-function --function sine --simulate --json
.\.venv\Scripts\scopes-tool.exe wgen-frequency --hz 1000 --simulate --json
.\.venv\Scripts\scopes-tool.exe wgen-voltage --amplitude 0.5 --simulate --json
.\.venv\Scripts\scopes-tool.exe wgen-offset --volts 0 --simulate --json
.\.venv\Scripts\scopes-tool.exe wgen-load --load one-meg --simulate --json
```
每個 Focused Command 精確要求一個 Query/Configure。Settable Function 為 `sine`、`square`、`ramp`、`pulse`、`noise`、`dc`，Load 為 `one-meg`/`fifty`。
Frequency/Amplitude/Offset 限制依 Series、Function、Load，以及 4000X Amplitude/Offset 的目前對應值。
規劃／入列前驗證使用 Planning Model 的 Series Envelope；Live 在任何 SCPI Write 前依偵測 Identity 驗證。
已知共同 Waveform 的 Live 驗證使用偵測 Model、目前 Waveform/Load，以及 4000X 需要的目前 Amplitude/Offset。
未知／延伸 Waveform Readback 退回適用 Model/Load Envelope；4000X High-Z Amplitude/Offset Interaction Guard 仍適用，以儀器為準。
因此規劃接受的值仍可能因目前 Function/Load/4000X 對應值而被 Live 拒絕。
軟體只對明確 High-Z（`one-meg`）套 Interaction Protection，不推測 50 Ω Threshold。
Aggregate `wgen-query` 個別查每欄並保留 Raw；未知／延伸 Function 回 `function: null`，保留 `function_raw`。

2000X/3000X 用 `:WGEN`，4000X 用 Generator 1 的 `:WGEN1`。
不開放 Generator Selection、Extended Function、Waveform-specific Range Table、Modulation、Arbitrary 或 Output Synchronization。
Worker Query 精確要求 `{"query": true}`，Aggregate/Focused 都拒絕 `{}`。
Configure 精確要求各自標準 Value Field，只有明確 `{"enabled": true}` 才開 WGEN Output。

讀取 Serial Bus 狀態：

```powershell
.\.venv\Scripts\scopes-tool.exe serial-status --bus 1 --simulate --json
```

```text
Bus 1
Protocol   UART
Display    ON
RX         CH1
TX         OFF
Baud       115200
Bits       8
Parity     None
Polarity   Idle High
```
`serial-status` 要求 `--bus`。Mode 為 UART/I2C/SPI/CAN 時也查 Protocol Decode Setting；其他 Mode 只回 Mode/Display，Protocol/Config 為 null。
Status 不包含 Trigger，請使用下述 Trigger Show。

`serial-mode` 選 Bus Protocol；`serial-enable`、`serial-disable` 獨立控制 Decode Display：

```powershell
.\.venv\Scripts\scopes-tool.exe serial-mode --bus 1 --mode uart --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-enable --bus 1 --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-disable --bus 1 --simulate --json
```
設定 Serial Protocol：

```powershell
.\.venv\Scripts\scopes-tool.exe serial-uart-set --bus 1 --rx-source channel1 --baud-rate 115200 --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-i2c-set --bus 1 --clock-source channel1 --data-source channel2 --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-spi-set --bus 1 --framing chip-select --word-width 8 --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-can-set --bus 1 --source channel1 --signal-definition difl --sample-point 75 --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-uart-show --bus 1 --simulate --json
```
各 Set 要求 `--bus` 與至少一個 Configure 選項。Source 為 Profile 類比範圍內的 `channelN` 或 `external`。
I2C 送 `IIC`；CAN 標準 Signal 為 `canh`、`canl`、`rx`、`tx`、`difl`、`difh`。
Show 先讀 `MODE?`，保留 Raw Protocol Readback。可用性依 Capability/License；此 Protocol Configure 不包含 Serial Search 或進階 Protocol Parameter。

設定 UART Serial Trigger：

```powershell
.\.venv\Scripts\scopes-tool.exe serial-trigger-uart-set `
    --bus 1 `
    --type rx-data `
    --data 85 `
    --qualifier equal

.\.venv\Scripts\scopes-tool.exe serial-trigger-uart-set `
    --bus 1 `
    --type rx-start

.\.venv\Scripts\scopes-tool.exe serial-trigger-uart-show --bus 1
```
標準 Type 為 `rx-start`、`rx-stop`、`rx-data`、`tx-start`、`tx-stop`、`tx-data`、`parity-error`。
Data Trigger 要求 `equal`、`not-equal`、`greater-than`、`less-than`，以及 0–255 的 8-bit Unsigned `--data`。
Bus 非 UART 時在寫 Criteria 前拒絕，不改 Decode、Serial Display、Bus Mode。
成功後選對應 Serial Bus 為 Global Trigger Mode，不 Run/Single/Wait/Capture。
不含 Burst、Idle、9-bit Alert/Data Comparison、Pattern Sequence 或其他 UART Extension。

I2C/SPI/CAN Trigger Configure 都先確認目標 Bus Protocol，不切換 Bus Mode、Display 或 Decode。
先寫入所有 Criteria，再設定 Global Trigger Mode；不執行 Acquisition Action，不加入 4000X I2C 擴充或 CAN FD。

```powershell
.\.venv\Scripts\scopes-tool.exe serial-trigger-i2c-set --bus 1 --type read-eeprom --address 0x50 --data 0x10 --qualifier equal
.\.venv\Scripts\scopes-tool.exe serial-trigger-spi-set --bus 1 --type mosi --width 8 --data 1010XX01
.\.venv\Scripts\scopes-tool.exe serial-trigger-can-set --bus 1 --type id-and-data --id 0x1 --id-mode standard --data 1010XX01 --data-length 1
```
I2C Address/Data 為 Unsigned Integer 或 Hex；SPI/CAN Pattern 接受文件規定的 Binary 或 `0x` Hex，含 `X` Don't-care。
Query 只回目前 Type 使用欄位並保留 Raw。Dry-run 因不知道 Live Bus Mode/Trigger Type，只列 `:SBUS<n>:MODE?`、`:TRIGger:MODE?`。

SPI Framing 標準值為 `chip-select`、`no-chip-select`、`timeout`。
前兩者不能搭配 `--clock-timeout`；Timeout Framing 要求同一 Configure 明確給 `--framing timeout`：

```powershell
.\.venv\Scripts\scopes-tool.exe serial-spi-set `
    --bus 2 `
    --framing chip-select `
    --word-width 8
```

```powershell
.\.venv\Scripts\scopes-tool.exe serial-spi-set `
    --bus 2 `
    --framing timeout `
    --clock-timeout 1e-6 `
    --word-width 8
```
若另一個 Bus 可能占用來源，先查詢兩個 Bus：

```powershell
.\.venv\Scripts\scopes-tool.exe serial-status --bus 1 --json
.\.venv\Scripts\scopes-tool.exe serial-status --bus 2 --json
```
Serial Lister 提供 Global Display/Reference Query 與 Host CSV Export，不啟用 Decode/SBUS Display、不擷取新 Traffic、不解析 CSV Row。
Decode 必須已設定且儀器已有 Lister Data。
`serial-data` 查 `:LISTer:DATA?` 並將 Payload 寫 Host，不是儀器端 `:SAVE:LISTer`。
Display 為 `off`、`bus1`、`bus2`、`all`；2000X 不支援選 bus2，3000X/4000X 支援。

```powershell
.\.venv\Scripts\scopes-tool.exe serial-lister-status --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-lister-display --selection bus1 --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-lister-display --query --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-lister-reference --reference previous --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-data --simulate --json
.\.venv\Scripts\scopes-tool.exe serial-data --output data\lister.csv --simulate --json
```
`--output` 選填；省略時為 `data/<UTC+8 timestamp>-lister.csv`。

保留 CSV Bytes 與換行，不另行解析 Protocol。來源衝突時查詢兩個 Bus。

```powershell
.\.venv\Scripts\scopes-tool.exe serial-status --bus 1 --json
.\.venv\Scripts\scopes-tool.exe serial-status --bus 2 --json
```
管理 Reference Waveform：

```powershell
.\.venv\Scripts\scopes-tool.exe reference-save --slot 1 --source-channel 1 --simulate --json
.\.venv\Scripts\scopes-tool.exe reference-display --slot 1 --state on --simulate --json
.\.venv\Scripts\scopes-tool.exe reference-label --slot 1 --text BASELINE --simulate --json
.\.venv\Scripts\scopes-tool.exe reference-query --slot 1 --simulate --json
.\.venv\Scripts\scopes-tool.exe reference-clear --slot 1 --simulate --json
```
Reference 支援 Slot 1/2。`reference-save` 只接受類比 Source；`reference-display` 設／查 Display；`reference-label` 設／查 1–10 個可列印 ASCII（無雙引號）；`reference-query` 讀 Display/Label 並保留 JSON Raw。
不支援 File-based `:SAVE:WMEMory`/`:RECall:WMEMory` 或 Reference Skew/Offset/Range/Scale。
啟用一個 Slot 可能關另一個，是儀器互動而非失敗；Simulator 獨立記錄，不模擬此互動。

管理 Search：

```powershell
.\.venv\Scripts\scopes-tool.exe search-state --enabled true --simulate --json
.\.venv\Scripts\scopes-tool.exe search-state --query --simulate --json
.\.venv\Scripts\scopes-tool.exe search-mode --mode serial1 --simulate --json --model keysight-dsox2004a
.\.venv\Scripts\scopes-tool.exe search-mode --mode edge --simulate --json --model keysight-dsox3024a
.\.venv\Scripts\scopes-tool.exe search-mode --mode peak --simulate --json --model keysight-dsox4034a
.\.venv\Scripts\scopes-tool.exe search-mode --query --simulate --json
.\.venv\Scripts\scopes-tool.exe search-count --query --simulate --json
.\.venv\Scripts\scopes-tool.exe search-event --event 1 --simulate --json --model keysight-dsox4034a
.\.venv\Scripts\scopes-tool.exe search-event --query --simulate --json --model keysight-dsox4034a
```
`search-state` 精確選 `--query`/`--enabled true|false`；`search-mode` 精確選 `--query`/小寫標準 Mode。
設定 Mode 先送 `:SEARch:STATe 1` 再送 `:SEARch:MODE <mode>`。
`search-count` 僅 Query，要求 `--query`；`search-event` 要求 `--query` 或正整數 `--event`，限 4000X。
未選 Event 或無 Hit 時 Query 可回 0。

Capability Guard：2000X 只 `serial1`；3000X 為 `edge`、`glitch`、`runt`、`transition`、`serial1`、`serial2`；4000X 另含 `peak`。
`ser1`、`ser2`、`glit`、`tran`、`off` 等 Alias 拒絕；不支援 Mode 在 Search SCPI 前拒絕。
Serial Search 有 `serial-search-uart`、`serial-search-i2c`、`serial-search-spi`、`serial-search-can`。
先用相符 `serial-uart-set`、`serial-i2c-set`、`serial-spi-set`、`serial-can-set` 設 Bus；Search 不改／重新驗證 Bus。
SPI Width 以 Byte 計，Pattern 精確含 `width * 2` 個 Hex/Wildcard Digit。
CAN `id-data` 僅 ID；要搜尋 ID/Data/DLC 使用 `data`。
同給 `--id`/`--id-mode` 時，Standard ID 為 `0x000`–`0x7FF`，Extended ID 為 `0x00000000`–`0x1FFFFFFF`。

查詢或設定儀器 Save 選項與儲存：

```powershell
.\.venv\Scripts\scopes-tool.exe save-pwd --path "\usb" --simulate --json
.\.venv\Scripts\scopes-tool.exe save-pwd --query --simulate --json
.\.venv\Scripts\scopes-tool.exe save-filename --name scope_01 --simulate --json
.\.venv\Scripts\scopes-tool.exe save-image-format --format png --simulate --json
.\.venv\Scripts\scopes-tool.exe save-image-palette --palette color --simulate --json
.\.venv\Scripts\scopes-tool.exe save-image-ink-saver --enabled false --simulate --json
.\.venv\Scripts\scopes-tool.exe save-image-factors --enabled true --simulate --json
.\.venv\Scripts\scopes-tool.exe save-image --filename "\usb\screen.png" --simulate --json
.\.venv\Scripts\scopes-tool.exe save-waveform-format --format csv --simulate --json
.\.venv\Scripts\scopes-tool.exe save-waveform-length --points 1000 --simulate --json
.\.venv\Scripts\scopes-tool.exe save-waveform-length-max --query --simulate --json
.\.venv\Scripts\scopes-tool.exe save-waveform --filename "\usb\wave.csv" --simulate --json
```
可 Query 的命令精確要求 `--query` 或 Setting。
Image 為 `png`、`bmp`、`bmp8`、`bmp24`，Palette 為 `color`/`grayscale`，Waveform 為 `ascii-xy`/`csv`/`binary`。
選了另一 File-format Family 時，Query 可能回 Sentinel `NONE`，正規化為 `none`。
Boolean 明確用 `true|false`；Waveform Length 為至少 100 的整數，上限依儀器／Model。
`save-waveform-length-max` 僅 Query。

引號 SAVE String 必須可列印 ASCII，不含雙引號、Control、CR/LF、分號。
`save-filename --name` 只接受 Basename，拒絕 Path/Drive Separator。
儀器 Path 與明確 Image/Waveform File Specification 可含 `/`、`\`、`:`，不 Trim/Sanitize/Escape 或自動加副檔名。
`save-image`、`save-waveform` 要求明確 Filename，啟動 Save 後等待 `*OPC?`。
`save-image` 暫用有界 15 秒 Completion Timeout 後還原；`save-waveform` 在 Keysight 保留目前 Timeout，Tek 暫用 15 秒並在 finally 還原。

`save-waveform --filename ... [--source-channel N]` 在 Keysight 保留 Filename-only 行為。
TBS2074 要求 `--source-channel` 在 1..4，保留 `csv` Format Control。
TDS2024B/TBS1052B 不開放 Setup、Reference Memory、Instrument File Save、Current Directory 或 Storage-only Setting。
使用可用儀器 Storage 與有效 Filename（TBS2000 為 8.3）。
TBS2074 `screenshot` 取原生黑背景 PNG，無 Appearance Control；TDS2024B 保留 USBTMC `--format bmp`；TBS1052B 以 USBTMC 明確用 `--format jpeg`，Host 為原生 `.jpeg`，不需 USB Flash Drive。
TBS1052B 的 BMP 因手冊適用範圍矛盾而仍不支援。

這些 SAVE 操作寫入儀器儲存，不在 Host 檢查或建立目錄；capture-batch/screenshots 則儲存在電腦。
不加入 Results、Lister、Mask、Multi、Power、Arbitrary、Compliance、Segmented、Setup Change 或 WMEMory Export。

讀取一個量測值：

```powershell
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item vpp --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item frequency --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item period --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item vavg --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item vrms --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item ac_rms --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item minimum --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item maximum --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item x_at_max --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item x_at_min --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item rise_time --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item fall_time --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item amplitude --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item top --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item base --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item overshoot --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item preshoot --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item positive_width --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item negative_width --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item duty_cycle --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item negative_duty_cycle --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item area --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item positive_edges --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item negative_edges --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item positive_pulses --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item negative_pulses --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item y_at_x --time 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item time_at_edge --slope positive --occurrence 1 --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item time_at_value --level 0.5 --slope positive --occurrence 1 --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --reference-channel 2 --item phase --log-scpi
.\.venv\Scripts\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --reference-channel 2 --item delay --log-scpi
```
讀取已安裝量測的結果：

```powershell
.\.venv\Scripts\scopes-tool.exe measure-results --resource "$env:SCOPES_TOOL_RESOURCE" --json --log-scpi
```
`measure-results` 唯讀，Identity Detection 後只送 `:MEASure:RESults?`，保留 Raw。
一般 Label/Value 交錯回應填入 `items`，Statistics 的 `label,current,min,max,mean,stddev,count` 可填入 `statistics_items`；無效 Statistics Sentinel 為 null，不視為一般值。
不清／安裝量測、不改 Source/Statistics Mode。只支援 3000X/4000X，2000X 使用個別 `measure`。
此 Parser 與 Counter 或 `measure-counter` 無關。

獨立的 `measure` 命令只查詢一個值，不安裝或變更前面板量測清單。要新增真正的前面板量測，請使用 `measure-install`。

量測命令只接受標準 Item 名稱：`vpp`、`frequency`、`period`、`vavg`、`vrms`、`ac_rms`、`minimum`、`maximum`、`x_at_max`、`x_at_min`、`rise_time`、`fall_time`、`amplitude`、`top`、`base`、`overshoot`、`preshoot`、`positive_width`、`negative_width`、`duty_cycle`、`negative_duty_cycle`、`area`（3000X/4000X）、`positive_edges`、`negative_edges`、`positive_pulses`、`negative_pulses`、`y_at_x`、`time_at_edge`、`time_at_value`、`phase`，以及只在 4000X 開放的安全 `delay`。
`y_at_x` 要求 `--time`；`time_at_value` 要求 `--level`；`time_at_edge` 與 `time_at_value` 接受 `--slope positive|negative` 及 `--occurrence N`，預設為 positive、第 1 次。雙 Channel Item 要求 `--channel` 與 `--reference-channel`；單 Channel Item 拒絕 `--reference-channel`。
命令先查 `*IDN?`、驗證類比 Channel 或 Channel Pair，送出一個唯讀 Query（例如 `:MEASure:VPP? CHANnel1`），再做一次 `:SYSTem:ERRor?` 命令後檢查。其他 Item Query 為 `:MEASure:VRMS? DISPlay,AC,CHANnelN`、`:MEASure:XMAX? CHANnelN`、`:MEASure:XMIN? CHANnelN`、`:MEASure:VAMPlitude? CHANnelN`、`:MEASure:VTOP? CHANnelN`、`:MEASure:VBASe? CHANnelN`、`:MEASure:OVERshoot? CHANnelN`、`:MEASure:PREShoot? CHANnelN`、`:MEASure:PWIDth? CHANnelN`、`:MEASure:NWIDth? CHANnelN`、`:MEASure:DUTYcycle? CHANnelN`、`:MEASure:NDUTy? CHANnelN`、`:MEASure:AREA? CHANnelN`（3000X/4000X）、`:MEASure:PEDGes? CHANnelN`、`:MEASure:NEDGes? CHANnelN`、`:MEASure:PPULses? CHANnelN`、`:MEASure:NPULses? CHANnelN`、`:MEASure:VTIMe? <time>,CHANnelN`、`:MEASure:TEDGe? +/-<occurrence>,CHANnelN`、`:MEASure:TVALue? <level>,+/-<occurrence>,CHANnelN`、`:MEASure:PHASe? CHANnel<src>,CHANnel<ref>`、`:MEASure:DELay? AUTO,CHANnel<src>,CHANnel<ref>`。
`delay` 刻意限制在 4000X，因為 2000X/3000X 的 Delay Query 依賴 `:MEASure:DEFine` 狀態。此操作不變更 Acquisition Mode、Trigger 設定、Measurement Source/Window、Display、VISA Timeout 或 Return-to-local 行為。
`9.9E+37` 等無效 Sentinel 顯示為 `Value: unavailable` 與 `Valid: false`，並保留 Raw Response；CLI 以非零結束，避免自動化將不可用值當成有效資料。

取得唯讀診斷快照：

```powershell
.\.venv\Scripts\scopes-tool.exe doctor --resource "$env:SCOPES_TOOL_RESOURCE" --json --log-scpi
```
`doctor` 查詢 `*IDN?`、Backend/Timeout Metadata、Acquisition Type/Count、每個類比 Channel 的 Display/Scale/Offset/Coupling/Probe Ratio/Bandwidth Limit、Horizontal Scale/Position 與類比 Edge Trigger 的 Source/Level/Slope。
最後做一次 `:SYSTem:ERRor?` 檢查，不清空整個 Error Queue。

跨 Channel 掃描常用量測：

```powershell
.\.venv\Scripts\scopes-tool.exe measure-sweep --resource "$env:SCOPES_TOOL_RESOURCE" --channel all --items vpp,frequency,period,vrms --json --log-scpi
.\.venv\Scripts\scopes-tool.exe measure-sweep --resource "$env:SCOPES_TOOL_RESOURCE" --channel all --items vpp,frequency,period,vrms,rise_time,fall_time --pair 1:2 --pair-items phase,delay --json --log-scpi
```
`measure-sweep` 預設 `--channel all` 與 `--items vpp,frequency,period,vrms`。可重複 `--channel` 指定 Channel，或使用 `--pair SRC:REF` 與 `--pair-items phase,delay` 量測 Channel Pair。
每筆 Record 保留 Validity、Value、Unit、Raw Response、Reason、SCPI Command 與 System Error Result。無效 Sentinel 或單項 Query Error 不會中止掃描；全部完成後若存在無效或錯誤 Record，命令以非零結束。

記錄有限批次的量測：

```powershell
.\.venv\Scripts\scopes-tool.exe measure-log --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --items vpp,frequency --count 10 --interval-seconds 1 --log-scpi
.\.venv\Scripts\scopes-tool.exe measure-log --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --items vpp,frequency --pair 1:2 --pair-items phase --count 5 --output-dir data\measure_logs\ch1_ch2 --log-scpi
```
`measure-log` 是有限、唯讀的量測記錄器，必須提供 `--count` 或 `--duration-seconds`，避免意外啟動無限記錄。
預設 `--channel all`、`--items vpp,frequency`、`--pair-items phase,delay`、`--interval-seconds 1.0`；只有提供 `--pair SRC:REF` 才量測 Pair。
命令開啟一個 Session、查詢 `*IDN?`、驗證 Channel/Item，再將 `measurements.csv`、`manifest.json`、`scpi.log` 寫入 `data/measure_logs/YYYY-MM-DD-HH-mm-ss`，或 `--output-dir` 指定位置。Output Directory 必須不存在或為空。

每個 CSV Row 包含 `timestamp_iso`、`elapsed_seconds`、每個要求量測的欄位；無效 Sentinel 或單項 Query Failure 寫為 `NaN`。
每個 Row 後讀一次 `:SYSTem:ERRor?` 並記錄到 Manifest。`--stop-on-error` 會在回報 Instrument Error 的 Row 完成後停止，保留既有檔案並以非零結束。
不送 `*RST`、不改 Acquisition Mode、不等待 Trigger、不改 Timeout Default、不使用 Background Thread，也不執行 Return-to-local。
`Ctrl+C` 保留已完成 Row，不提交部分 Row，寫入 Manifest Status `interrupted`，回傳 `130`。

持續量測一個值直到符合條件：

```powershell
.\.venv\Scripts\scopes-tool.exe measure-until --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item vpp --operator gt --threshold 3.3 --timeout-seconds 600 --interval-seconds 1
```
`measure-until` 查詢既有、非參數化的單 Channel 量測，不控制 Acquisition 或 Trigger 狀態。
每次成功 Query 後執行一次 System Error Check，在回報前持久化。無效 Sentinel 寫為 `NaN`，不符合條件。
符合條件且已提交的 Sample 成功結束；逾時未符合時以 Exit Code `1` 與 `condition_timeout` 結束。
直接 CLI 的 Artifact 預設在 `data/measure_until/<timestamp>`。Dry-run 只顯示一個代表性 Measurement Query 與一次 `:SYSTem:ERRor?`，不開 VISA、不寫檔。參閱 [Core Integration](../core/integration.md#measure-until-condition-v1)。

儲存符合一個波形條件的確切 Acquisition：

```powershell
.\.venv\Scripts\scopes-tool.exe capture-until --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --condition-channel 1 --points 1000 --format byte --metric max --operator gt --threshold 1.5 --count 3 --timeout-seconds 60 --interval-seconds 0
```
`capture-until` 從已取得的波形評估一個選定的類比 Condition Channel。條件由一個 Metric 與 Comparison 組成；符合時以正常 Waveform CSV/Metadata 格式儲存同一次 Acquisition 的所有選定 Channel，不會符合後再擷取一次。
不符合時不建立 Waveform 或 Metadata Artifact，也不保留為 Waveform History。

`--count` 是要儲存的符合條件 Acquisition 數，預設 `1`，接受 `1..255`，這是 Scopes Tool 產品限制。
一個正有限 Timeout 涵蓋整個 Workflow，不因符合條件而重設。部分完成的 `condition_timeout` 保留先前 `match_NNN.csv`、`match_NNN_meta.json`，以 Exit Code `1` 結束並回報 Match/Total Capture Count。
直接 CLI 預設輸出 `data/capture_until/<timestamp>`，另含 `manifest.json`、`scpi.log`。沿用目前 Waveform Retrieval，不設定或等待 Trigger。Dry-run 只顯示一個代表性 Capture。參閱 [Core Integration](../core/integration.md#capture-until-v1)。

監看有限的重複擷取 Session：

```powershell
.\.venv\Scripts\scopes-tool.exe capture-monitor --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --points 1000 --format byte --count 2000 --interval-seconds 0 --retention-points 250000
```
`capture-monitor` 每個 Channel 在 RAM 最多保留 `--retention-points` 個 Sample，預設 `250000`；此值必須至少容納一次 Capture，且為 `--points` 的整數倍。
溢出時丟棄最舊的完整 Capture Chunk。Maximum、Minimum、Peak-to-peak、Absolute-maximum 統計仍涵蓋所有已觀察 Sample，包括已丟棄 Chunk。

重複 Capture 是獨立 Acquisition。每個 Chunk 的 `time_s` 是區域時間，Chunk 間可能有 Acquisition/Communication Gap；Global Sample Index 代表順序，不是連續時間。
啟用儲存時只將最後保留 Window 寫入 `retained_waveforms.csv`，另附 `manifest.json`、`scpi.log`；丟棄的 History 不持久化。
CSV 保留 Capture Boundary、Global/Local Sample Index、Local Time 與每個 Channel 的值欄位。`--no-save` 不建立 Workflow Result Artifact。
啟用儲存且至少 Capture 一次後取消時，會寫入停止時的保留 Window，Status 仍為 cancelled/interrupted；首次 Capture 前取消不建立空 Waveform CSV。參閱 [Core Integration](../core/integration.md#capture-monitor-v1)。

執行有限的 Triggered Measurement Loop：

```powershell
.\.venv\Scripts\scopes-tool.exe triggered-measure-loop --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --items vpp,frequency --pair 1:2 --pair-items phase --count 100 --trigger-timeout-seconds 5 --interval-seconds 0
```
每個 Cycle 送 `Single`，透過既有 Trigger-wait 路徑等待 Acquisition 完成、查詢選定量測、檢查一次 Instrument Error Queue，並在回報 Progress 前持久化完整 Cycle。
無效 Sentinel 寫為 `NaN`；Query、Transport、Parsing、System Error 或 Trigger Timeout 立即停止。
預設將 `measurements.csv`、`manifest.json`、`scpi.log` 寫入 `data/triggered_measure_loops/<timestamp>`，直接 CLI 可指定 `--output-dir`。
`--dry-run` 顯示一個代表性 Cycle，不開 VISA、不寫 Runtime Artifact。參閱 [Core Integration](../core/integration.md#triggered-measurement-loop-v1)。

執行有限的 Triggered Waveform Capture Series：

```powershell
.\.venv\Scripts\scopes-tool.exe triggered-capture-series --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --format byte --count 10 --trigger-timeout-seconds 5 --interval-seconds 0
```
每個 Cycle 送 `Single`，透過既有 Trigger-wait 路徑等待目前 Acquisition 完成、擷取指定 Waveform Channel、寫入 CSV/Metadata、檢查一次 Instrument Error Queue、提交 Manifest，最後回報 Progress。
使用示波器既有 Trigger 設定，不設定或強制 Trigger。直接 CLI 預設 `data/triggered_capture_series/<timestamp>`；Dry-run 顯示一個代表性 Cycle，不開 VISA、不寫 Artifact。參閱 [Core Integration](../core/integration.md#triggered-capture-series-v1)。

執行 Generic Sequence v1 文件：

```powershell
.\.venv\Scripts\scopes-tool.exe sequence --dry-run --json --file workflow.json
.\.venv\Scripts\scopes-tool.exe sequence --simulate --file workflow.json --output-dir data\sequence-run
.\.venv\Scripts\scopes-tool.exe sequence --resource "$env:SCOPES_TOOL_RESOURCE" --file workflow.json
```
`sequence` 接受嚴格 JSON version 1，以正有限 `loop_count` 依序執行 `steps`。
Action 為 `wait`、`single`、`wait-trigger`、`measure`、`capture`、`screenshot`、`cleanup`。
文件接受 `1..255` 個 Step、`loop_count` `1..255`，最多 65,025 次 Step Execution；每個 Loop 合計最多 10 個 `capture`/`screenshot` Step，255 個 Loop 最多 2,550 次這類操作。這些是 Scopes Tool 產品限制，不是儀器硬體限制。
`wait-trigger` 等待前一個 `single` 已啟動的 Acquisition，不另 Arm 或 Force Trigger。執行為單執行緒、遇錯立即停止，取消不自動執行 Cleanup。
預設啟用儲存，每次 Runtime Run 寫入 `manifest.json`、`scpi.log`；Capture/Screenshot 使用固定 Loop/Step Path。
使用 `--no-save`（`save_results=false`）不建立 Host Run Directory、Manifest 或 `scpi.log`，`files` 為空；文件含 `capture` 或 `screenshot` 時不能使用此模式。
`--log-scpi` 仍只向 stderr 輸出診斷，停用儲存時不建立 Log File。Dry-run 驗證完整文件，不開 VISA、不寫 Runtime Artifact。完整公開 Schema/語義見 [Core Integration](../core/integration.md#generic-sequence-v1)。

執行可安全擷取的 Smoke Check：

```powershell
.\.venv\Scripts\scopes-tool.exe smoke --resource "$env:SCOPES_TOOL_RESOURCE" --json --log-scpi
```
`smoke` 將 `report.json`、`scpi.log`、`capture.csv`、`capture_meta.json`、`screen.png` 寫入 `data/hardware_smoke/YYYY-MM-DD-HH-mm-ss`；預設目錄已存在時附加 `-2`、`-3` 等。
可用 `--output-dir DIR` 指定不存在或為空的目錄。預設流程取得 Doctor Snapshot、查 CH1 `vpp`/`vrms`、擷取 CH1 的 1000-point BYTE Waveform、擷取黑背景 Screenshot，最後做 System Error Check。
Smoke Report 使用 Schema Version `2`；Capture CSV、Metadata 與巢狀 Capture Summary 保留選定 `vertical_unit`。
Keysight 的無效量測 Sentinel 視為 Warning；Tektronix Smoke 的無效量測則失敗。
Measurement Warning 540–549 只有在值有效且有限、完整 Status Cohort 僅含這些 Warning、且除了 Execution Bit 4 沒有其他 SESR Error Bit 時才接受；保留 Native Diagnostics。
Capture、Screenshot、Backend、Output 或 System Error 失敗均以非零結束。

擷取 Waveform：

```powershell
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 10000 --csv data\ch1.csv --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --csv data\ch1.csv --plot data\ch1.png --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --format word --csv data\ch1_word.csv --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --points 1000 --csv data\ch1_ch2.csv --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --points 1000 --csv data\ch1_ch2.csv --allow-time-axis-tolerance --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel all --points 1000 --csv data\all_channels.csv --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --wait-trigger --trigger-timeout-ms 5000 --trigger-poll-interval-ms 100 --log-scpi
.\.venv\Scripts\scopes-tool.exe capture --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --wait-trigger --trigger-timeout-ms 5000 --force-trigger-on-timeout --log-scpi
```
Capture 支援 BYTE/WORD 與要求 1000、5000、10000 Points，預設 BYTE。
WORD 在讀取前設定 `:WAVeform:BYTeorder MSBFirst`、`:WAVeform:UNSigned ON`。Capability Flag 描述 Runtime 支援且有 Guard 的功能範圍。
可重複 `--channel` 在同一 Session 依序擷取多個類比 Channel；`--channel all` 擷取偵測 Model Capability 的所有類比 Channel，不查詢或依 Display 過濾。
多 Channel CSV 使用第一個 Channel 的 `time_s`，垂直欄位依要求順序，例如 `time_s,ch1_v,ch2_a`。Volt 後綴 `_v`，Amp 後綴 `_a`，同一 CSV 可混合垂直單位。
`--channel all` 不能與明確 Channel Number 混用。重複或超出偵測 Capability 的 Channel 在 Waveform SCPI 前拒絕。
各 Channel Time Axis 或 Sample Count 不符時會失敗，不寫入誤導的對齊 CSV。
僅 `capture` 的 `--allow-time-axis-tolerance` 可容許少量跨 Channel Time-axis Drift，Sample Count 仍須相同；包含 CH1 時，每個非標準 Channel 在每個點與 CH1 的差距不得超過 CH1 Sample Interval 的一半。
CSV 仍只寫標準 `time_s`，不內插、不重採樣。啟用此選項時 Metadata/`--json` 包含標準 Channel、允許最大差距與各 Channel 實測最大差距。
省略 `--csv` 時使用 `UTC+8`，輸出 `data/YYYY-MM-DD-HH-mm-ss.csv`；提供 `--csv PATH` 時精確寫入該 Path。Metadata 預設在 CSV 旁以同 Stem 加 `_meta.json`。
單 Channel Metadata 保留頂層 `channel`、`actual_points`，`vertical_unit` 為 `"V"` 或 `"A"`。
多 Channel Metadata 頂層包含 IDN、Resource、Model、Series、Format、Requested Points；排序的 `channels` 含 Channel Number、`vertical_unit`、Actual Points、Preamble 及適用的 WORD Byte-order 欄位。
Host 不做 Voltage/Current Conversion；Preamble Scaling 以選定 Channel Unit 解讀。
命令做一次 `:SYSTem:ERRor?` 檢查，不改 VISA Timeout、Acquisition Mode、Waveform Point Mode 或 Return-to-local。
CSV/Metadata 因其他程式開啟或目錄不可寫而無法寫入時，CLI 回報清楚的 `error:`，不顯示 Python Traceback。

`capture --wait-trigger` 是明確改變狀態的 Triggered Capture：送 `:SINGle`，只輪詢 `:OPERegister:CONDition?` 後再讀 Waveform。
`--wait-trigger` 必須搭配 `--trigger-timeout-ms`。`--trigger-poll-interval-ms` 預設 100 ms，必須不大於 Timeout。
`--force-trigger-on-timeout` 只可搭配 `--wait-trigger`；首次有限等待逾時後送 `:TRIGger:FORCe`，再使用相同有限 Poll Window 後擷取。
不使用 `:TRIGger:STATus?` 或 `*OPC?`。
DSO-X 2000X/3000X/4000X 依 Operation Status Condition 的 Run Bit 分類：Set 為 Acquisition 進行中，Clear 為完成。
其他 Series 未分類的 Operation Condition 不允許 Waveform Capture。

Triggered Capture JSON 新增 `result.trigger`，Outcome 為 `natural`、`forced`、`timeout`、`unknown`。
只有 `natural`/`forced` 寫入 Waveform Artifact。Timeout、不支援 Poll Query、Parse Failure 或未分類 Operation Condition 均以非零結束，不寫 Capture Artifact，並在 `raw_values`、`condition_values` 保留 Raw Poll Value；可行時仍做一次 `:SYSTem:ERRor?`。
不支援的 Live Operation-condition Value 保持未分類，不允許 Capture。

擷取有限批次的 Waveform：

```powershell
.\.venv\Scripts\scopes-tool.exe capture-batch --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --points 1000 --format byte --count 3 --interval-seconds 1 --log-scpi
.\.venv\Scripts\scopes-tool.exe capture-batch --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --channel 2 --points 1000 --format word --count 2 --output-dir data\captures\ch1_ch2_batch --log-scpi
.\.venv\Scripts\scopes-tool.exe capture-batch --resource "$env:SCOPES_TOOL_RESOURCE" --channel all --points 1000 --count 2
```
Periodic Capture 是產品顯示的 Workflow 名稱，CLI 機器介面仍為 `capture-batch`。完整 v1 語義見 [Core Integration](../core/integration.md#periodic-capture-v1)。

`capture-batch` 是保守的有限批次 Capture。`--count` 必填且為正整數；`--interval-seconds` 預設 `0`，必須有限且非負。
非零時，前一次 Capture Artifact/Manifest 持久化且回報完成後才開始等待，不是絕對 Wall-clock Cadence。
命令開一個 VISA Session、查 `*IDN?`、驗證偵測 Capability、Channel、Points、Format，再重複既有 Waveform Capture API 指定次數。每次 Capture 後做一次 `:SYSTem:ERRor?`。

省略 `--output-dir` 時以 `UTC+8` 輸出至 `data/captures/YYYY-MM-DD-HH-mm-ss`；預設目錄存在時附加 `-2`、`-3` 等以免覆寫。
提供 `--output-dir DIR` 時 DIR 必須不存在或為空，避免新 Capture 混入舊檔。

每次 Capture 寫入 `waveform_0001.csv`、`waveform_0001_meta.json` 等，序號至少四位。
Run Directory 另含 `manifest.json`（Run Parameter、IDN、Capture Path、Actual Points、System Error Result）與 `scpi.log`。
`capture-batch` 一定寫 `scpi.log`；`--log-scpi` 另將相同 Package SCPI Debug Log 輸出到 stderr，供明確的 Live Check 使用。

Capture 後若有 System Error，保留已寫入的檔案與 Manifest、停止後續 Capture，並以非零結束。
Python Control Flow 中斷時盡力寫入 Status `interrupted` 的 Manifest，回傳 `130`。

其他 DSO-X 4024A 控制：

```powershell
.\.venv\Scripts\scopes-tool.exe cursor --resource "$env:SCOPES_TOOL_RESOURCE" --query --log-scpi
.\.venv\Scripts\scopes-tool.exe cursor --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --x1 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe cursor --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --y2 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe cursor --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --x1 0 --x2 1e-3 --y1 0 --y2 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --resource "$env:SCOPES_TOOL_RESOURCE" --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe trigger-holdoff --resource "$env:SCOPES_TOOL_RESOURCE" --seconds 1e-6 --log-scpi
.\.venv\Scripts\scopes-tool.exe measure-stats --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --items vpp,frequency --mode all --reset --log-scpi
.\.venv\Scripts\scopes-tool.exe autoscale --resource "$env:SCOPES_TOOL_RESOURCE" --source-channel 1 --source-channel 2 --log-scpi
.\.venv\Scripts\scopes-tool.exe setup-save --resource "$env:SCOPES_TOOL_RESOURCE" --slot 1 --log-scpi
.\.venv\Scripts\scopes-tool.exe setup-recall --resource "$env:SCOPES_TOOL_RESOURCE" --file "\usb\setup.scp" --log-scpi
.\.venv\Scripts\scopes-tool.exe fft --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --source-channel 1 --units decibel --window hanning --center-hz 1000 --span-hz 10000 --display on --log-scpi
.\.venv\Scripts\scopes-tool.exe fft --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --source-channel 1 --display off --log-scpi
.\.venv\Scripts\scopes-tool.exe fft --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --log-scpi
.\.venv\Scripts\scopes-tool.exe fft --resource "$env:SCOPES_TOOL_RESOURCE" --function 2 --source-channel 1 --fft-operation fft-phase --start-hz 100 --stop-hz 1000000 --gate zoom --phase-reference display --detection-type average --detection-points 4096 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-display --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --on --log-scpi
.\.venv\Scripts\scopes-tool.exe math-display --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-vertical --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --scale 2 --offset 0.5 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-vertical --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --range 8 --offset 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-vertical --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-operator --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation subtract --source1 channel1 --source2 channel2 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-operator --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-composite-source --resource "$env:SCOPES_TOOL_RESOURCE" --operation subtract --source1 channel1 --source2 channel2 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-composite-source --resource "$env:SCOPES_TOOL_RESOURCE" --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-transform --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation integrate --source channel1 --input-offset 0 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-transform --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation linear --source channel1 --gain 2 --linear-offset -1 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-transform --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-filter --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation low-pass --source channel1 --cutoff-hz 1000000 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-filter --resource "$env:SCOPES_TOOL_RESOURCE" --function 2 --operation average --source math1 --average-count 64 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-filter --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-visualization --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation magnify --source composite --log-scpi
.\.venv\Scripts\scopes-tool.exe math-visualization --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --operation trend --source channel1 --source2 channel2 --measurement vratio --log-scpi
.\.venv\Scripts\scopes-tool.exe math-visualization --resource "$env:SCOPES_TOOL_RESOURCE" --function 2 --operation max-hold --source math1 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-visualization --resource "$env:SCOPES_TOOL_RESOURCE" --function 2 --operation trend --measurement-slot 3 --log-scpi
.\.venv\Scripts\scopes-tool.exe math-visualization --resource "$env:SCOPES_TOOL_RESOURCE" --function 2 --query --json --log-scpi
.\.venv\Scripts\scopes-tool.exe math-clear --resource "$env:SCOPES_TOOL_RESOURCE" --function 1 --log-scpi
```
`measure-stats --max-count` 接受 2–2000 的整數，使用儀器 `:MEASure:STATistics:MCOUnt` 設定。
CLI 維持既有重建再查詢的流程；WebUI 提供獨立的儀器 Statistics 設定，不清除已安裝量測。

`fft`、`math-display`、`math-vertical`、`math-operator`、`math-transform`、`math-filter`、`math-visualization`、`math-clear` 使用 Model 的儀器端 Math Function Layout。
2000X/3000X 只有一個未編號的 `:FUNCtion` 子系統，要求 `--function 1`；4000X 使用 `:FUNCtion1`–`:FUNCtion4`，接受 `--function 1..4`。
Global `math-composite-source` 只適用 2000X/3000X，不接受 `--function`。

`fft` 保留 2000X/3000X 的基本 Magnitude 行為，預設 `--fft-operation fft`；4000X 可用 `--fft-operation fft-phase` 選 FFT Phase。
4000X 選填控制為 `--start-hz`、`--stop-hz`、`--gate`、`--phase-reference`、`--detection-type`、`--detection-points`。
同一次 Configure 不能混用 Center/Span 與 Start/Stop；Phase Reference 只可用於 FFT Phase。
`--units` 只適用 Magnitude FFT，FFT Phase 必須省略。
4000X 的 `fft --query` 另回報 `start_hz`、`stop_hz`、`gate`、`detection_type`、`detection_points`、`bin_size_hz`、`sample_rate_hz`、`resolution_bandwidth_hz` 與可為 null 的 `phase_reference`。
不自動開啟 Math Display、不設定 Zoom/Timebase、不 Autoscale、不改 Acquisition State。
衍生 Query 欄位來自儀器 Readback，不是 Host FFT 計算結果。

各 Series 的 Math Operation Matrix 見 `../core/supported-models.md`。Math 只在儀器端執行；因未開放 MSO/Digital Channel，不支援 Bus Timing/Bus State。所有 Math 命令都不計算 Host Waveform。

`math-display` 必須精確選一個 `--on`、`--off`、`--query`。
`math-vertical` Query 不能含 Setter；Configure 至少需要 `--scale`、`--range`、`--offset` 之一，Scale/Range 互斥，任一可與 Offset 合用。
Vertical Configure 不自動開 Display，也不 Autoscale。韌體可能在 Math Display 從 OFF 切 ON 時重算 Scaling；要保留明確設定，先執行 `math-display --function N --on`，再設定 `math-vertical` Scale/Range/Offset。
啟用一個 4000X Slot 不主動停用其他 Slot；單一可見 Slot 行為由儀器管理。
Display/Vertical 不設定 Math Operation/Source、不探測 License、不做 Host Math。

`math-operator` 設定或查詢一個儀器端雙來源 Math Operator。Configure 要求 `--operation`、`--source1`、`--source2`，Query 不能包含這些選項。
Operation 接受 `add`、`subtract`、`multiply`、`divide`；兩個 Source 都必須是 Model 支援的標準類比 `channel1`–`channel4`。
不自動開 Display、不改 Vertical、不 Autoscale、不計算 Host Waveform、不探測 License。
不支援其他 Math Operation，以及 Reference/Math/Bus/Digital/External/Expression Source。License 可用性仍依 Live Instrument Error Queue。

`math-transform` 設定或查詢一個儀器端單來源 Transform。Operation 為 `differentiate`、`integrate`、`sqrt`、`absolute`、`square`、`ln`、`log10`、`exp`、`exp10`、`linear`。
Configure 要求 `--operation`、`--source`；Source 可用 Model Channel 數範圍內的標準 `channel1`–`channel4`。
2000X/3000X 另接受 `composite`；4000X 只接受比目的 Function 編號低的 `math1`–`math3`。
`--input-offset` 只在 `integrate` 選填；`--gain`、`--linear-offset` 只在 `linear` 選填，省略則保留目前值。
Query 不能含 Configure 選項；先識別目前 Operation，再按需讀 Integrate/Linear Parameter。若目前不是支援的 Transform，回報錯誤且不改狀態。

`math-composite-source` 設定或查詢 2000X/3000X 的 Global `g(t)` Source。
Configure 要求 `--operation`、`--source1`、`--source2`；Operation 為 `add`、`subtract`、`multiply`，兩個 Source 都是支援的類比 Channel，不接受 `divide`。
Query 與 Configure 選項互斥。標準 `composite` 可用於 `math-transform`、`math-filter` 與支援的 `math-visualization` Operation；不能用於 `math-operator` 或 Source2。
4000X 公開介面不開放 GOFT。

`math-filter` 設定或查詢儀器端單來源 Filter。
2000X/3000X/4000X 支援 `low-pass`、`high-pass`，選填正有限 `--cutoff-hz`。
4000X 另支援 `average`（選填 2–65536 的 2 次方 `--average-count`）、`smooth`（選填至少 3 的奇數 `--smooth-points`）、`envelope`（無額外參數）。
Source 沿用單來源契約：各 Series 的類比 Channel、2000X/3000X 的 `composite`、4000X 的較低編號 Math Function。
Query 先讀 Operation/Source，再只讀目前 Filter 適用的 Parameter。無法安全序列化的過大整數以 Parameter Error 拒絕。
`math-clear --function N` 僅 4000X，直接清除指定 Math Accumulation，不查 Operation、不等完成。

`math-visualization` 設定或查詢儀器端 Visualization Waveform。
註冊的 Keysight Series 支援 `magnify`、`trend`；4000X 另有 `maximum`、`minimum`、`peak`、`max-hold`、`min-hold`。
非 Trend 需要一個 Source，沿用單來源規則：各 Series 類比 Channel、2000X/3000X `composite`、4000X 較低編號 Math Function。
2000X/3000X Trend 要求類比 `--source` 與一個標準 `--measurement`，只有 `vratio` 另需類比 `--source2`。
4000X Trend 改要求 `--measurement-slot 1..10`，拒絕 Source 選項，假設該 Slot 已安裝相容量測。
Query 保留 Raw Operation/Source/Measurement Readback，4000X Trend 不查 Source。

`math-clear` 適用於 4000X 的 `average`、`max-hold`、`min-hold` Accumulation；送出編號 Clear 命令前不檢查目前 Operation。

這些 Math 命令不自動開 Display、不改 Vertical、不 Autoscale、不安裝或修改量測、不改 Acquisition、不探測 License、不計算 Host Waveform、不匯出 Waveform。
Reference Waveform、Bus、Digital Source 仍不支援；License 可用性依 Live Instrument Error Queue。

這些命令都是明確使用者操作，`doctor`、`smoke`、`acquisition-check` 不會呼叫。
部分會改前面板狀態，例如 Cursor、Holdoff、Autoscale、Setup、FFT、Math Display/Vertical 與前面板 Measurement Statistics。

`capture-batch` 刻意不改 Acquisition Mode、不等 Trigger、不輪詢 Acquisition Completion、不改 VISA Timeout Default、不 Return-to-local、不啟動 Background Thread 或無限記錄。

將目前儀器畫面擷取為影像：

```powershell
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --output data\screen.png --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --background white --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --format png --output data\screen.png --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --format bmp --output data\screen.bmp --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --format bmp8bit --ink-saver false --palette grayscale --layout landscape --output data\screen-8bit.bmp --log-scpi
.\.venv\Scripts\scopes-tool.exe screenshot --resource "$env:SCOPES_TOOL_RESOURCE" --query-hardcopy --json --log-scpi
```
`screenshot` 先查 `*IDN?`，依要求背景設定 `:HARDcopy:INKSaver`，以 `:DISPlay:DATA? PNG, COLor` 讀目前畫面，還原 Ink Saver，最後做一次 `:SYSTem:ERRor?`。
預設黑背景，符合示波器畫面；`--background white` 啟用反白 Hardcopy。
省略 `--output` 時以 `UTC+8` 輸出 `data/YYYY-MM-DD-HH-mm-ss.png`。命令驗證 PNG Signature。
影像較一般 Query 大，傳輸時暫設 VISA Timeout 10000 ms，完成後還原。
不改 Acquisition、Trigger、Display、Default Timeout 或 Return-to-local。

4000X 的 `--format png|bmp|bmp8bit` 使用 `:HCOPY:SDUMp:DATA? <format>`，驗證 PNG/BMP Signature。
PNG 使用 `.png`，BMP/BMP8bit 使用 `.bmp`；明確 Path 的副檔名不符時，在開 Backend 前拒絕。
`--ink-saver true|false`、`--palette color|grayscale|none`、`--layout landscape|portrait` 在影像 Query 前寫入相應設定，這些明確設定會保留在儀器。
省略 `--ink-saver` 時保留原有依背景暫改再還原的行為。

`--query-hardcopy` 僅 Query，回傳標準 Area/Ink Saver/Palette/Layout/Format 與 Raw Readback，不擷取影像、不建 Artifact，不能與 Capture/Setting 選項合用。
2000X/3000X 不開放 Screenshot Format 選項，維持原有 PNG。
Printer Job、Hardcopy Area 選擇、Network Printer 不在此範圍。
儀器端 Image Save 是獨立流程，不改 Screenshot 的 PC-side Byte Retrieval。

<a id="tests"></a>

## 測試

一般測試不需要硬體：

```powershell
New-Item -ItemType Directory -Force .tmp_tests | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --basetemp .tmp_tests\full
```
此命令執行 Repository 的 Hardware-free Tests，包含 `tests/core`、`tests/cli`、`tests/webui`、`tests/tooling`。

要篩選 Hardware-free Test，可直接指定區域：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/cli -q --basetemp .tmp_tests\cli
```
請一律提供 Repository-local `--basetemp`；Windows 使用者預設 Temp 可能遇到共用暫存權限衝突。

實機檢查是手動操作。先使用 `--dry-run --json`，再 `--simulate --json`；只有操作人員選定儀器後，才使用明確 `--resource <RESOURCE>` 或 `SCOPES_TOOL_RESOURCE`。
Live Worker 啟動要求 `--live --resource`。Live Check 應先確認 USB 通訊，再執行改狀態或寫 Artifact 的命令。

<a id="real-instrument-checks"></a>

## 實機檢查

公開測試基準是 Hardware-free pytest。實機檢查須明確選擇，應涵蓋目標 Model/Transport 的代表性 Workflow：

- `identify`、`check-error`：通訊與 Error Queue。
- 設定前先執行唯讀 Measurement/Diagnostic。
- 僅在允許改儀器狀態時執行 Channel、Acquisition、Timebase、Trigger、Setup、Autoscale。
- Waveform、Screenshot、Smoke、Batch Capture、Measurement Logging 使用明確 Output Path。

不要在啟用中的 Live Workflow 掃描或輪換 Resource；整個 Workflow 使用操作人員選定的一個明確 Resource。

維護中的 Live Validation Script 在未指定 `-Backend` 時使用 System VISA；可明確傳 `-Backend "@py"` 以 PyVISA-py 執行相同驗證：

```powershell
# System VISA (default)
.\scripts\live-cli-check.ps1 -Target keysight-dsox4034a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE

# pyvisa-py
.\scripts\live-cli-check.ps1 -Target keysight-dsox4034a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE -Backend "@py"
```
每次 Live Validation 都需分別選擇 System VISA 或 PyVISA-py Backend。

六個 Live Validation Runner 預設採最少 Artifact。一般 CLI stdout/stderr 與每次 Invocation JSON 在記憶體中驗證，不寫磁碟。
必要 Waveform、Screenshot、Workflow Test File 只為驗證建立，檢查後清除。
完成的 Run 無論 PASS/FAIL，只保留 `shareable/report.json`、`shareable/summary.md`；這些去識別化報告保留 Case Result、Execution Metadata 與 Failure Diagnostic。
`-DebugArtifacts` 另保留既有 Private Raw Output、stdout/stderr、CLI JSON、Workflow、Preflight 與 Shareable Debug Artifact。
任一模式若 Shareable Report 產生失敗，Run 失敗且只保留有界、去識別化的 `private/error-summary.md`，不保留 Raw Diagnostic File。
強制終止或 Ctrl+C 仍可能留下必要暫存檔。獨立 `preflight-cli.ps1` 也預設最少模式，需要完整 Preflight 資料時才用 `-DebugArtifacts`。

```powershell
# Default: minimal artifacts
.\scripts\live-cli-check.ps1 -Target keysight-dsox4034a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE

# Retain detailed artifacts
.\scripts\live-cli-check.ps1 -Target keysight-dsox4034a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE -DebugArtifacts
```
相同保留選項也適用於 `live-workflow-check.ps1`、`live-dvm-check.ps1`、`live-serial-check.ps1`、`live-segmented-check.ps1`、`live-autoscale-check.ps1`，各自使用既有參數。
Run Directory 命名與 `-OutputRoot` 行為不變。

<a id="tektronix-live-acceptance"></a>

### Tektronix 實機驗收

TBS2074 的 `cursor` 可選填 `--function`，五個值對應第一代 Tektronix TBS2000 Cursor Function：`off`、`screen`、`waveform`、`vbars`、`hbars`。
明確 Function 優先；省略時依要求 Axis 沿用既有映射：僅 X 為 `vbars`、僅 Y 為 `hbars`、X+Y 為 `screen`。
`off`/`waveform` 只切 Function，不要求 Source Channel 或 Position。
`vbars` 只接受 X Position，`hbars` 只接受 Y Position；其他組合在寫儀器前拒絕。

Auto 實機驗證獨立執行，使用下述 `live-autoscale-check.ps1`。
`live-cli-check.ps1` 不執行 Auto，也不接受 `-IncludeAutoscale`。

`live-cli-check.ps1` 使用精確註冊的 Tektronix Target 與操作人員選定的 VISA Resource。
接受 `tektronix-tbs2074`、`tektronix-tds2024b`、`tektronix-tbs1052b`，Connection Type 為 `usb`/`tcpip`，Resource 必須相符。
預設 System VISA；需要時明確選 PyVISA-py：

```powershell
.\scripts\live-cli-check.ps1 -Target tektronix-tbs2074 -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE
.\scripts\live-cli-check.ps1 -Target tektronix-tds2024b -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE -Backend "@py"
```
Hardware-free Core Profile Check 與 Simulated Identify 後，Runner 比對偵測的 Physical Identity 與 Target，不符時在改狀態 Case 前停止。
標準 Case 查詢支援的狀態／設定，並在公開 CLI 有安全路徑時回寫目前值，不需其他 Action Switch。
三個 Model 都執行 `run`、`stop-acquisition`、`single`、`force-trigger` 與 Natural/Timeout-force `single-wait`。
Cleanup 要求 Stop 並檢查 Native Command Status，不獨立讀 Running/Stopped，也不還原原狀態。

量測檢查在已顯示 CH1 上執行 Core `measurement_items` 每項，要求有效有限值與 Unit。
Signal 導致的無效值以 CLI Reason 報 FAIL，其餘 Item 繼續。
BYTE Capture 最多要求 1000 Points，檢查 CSV/JSON Count、有限 Waveform Value 與嚴格遞增 Time Axis。
這些 Host Transfer 也適用於未開放儀器端 Storage 的 Legacy Model。

依各 Model 支援子集執行 Cursor Set、Cursor Off、Measurement Install/Clear。
不還原先前 Cursor/Measurement 設定；成功後 Cursor 關閉、量測清空。
TBS2074 查驗 X、實體電壓 Y、組合 SCREEN 及五個 Cursor Function（`off`、`screen`、`waveform`、`vbars`、`hbars`）的 Query/Readback。
Cursor Source Selection 可能經 Core 顯示 Channel 或重啟 Acquisition，這些效果不還原。
Horizontal Position 只用公開 `timebase-position` Query/Set/Readback，不切 Delay Mode ON/OFF。

Screenshot：TBS2074 用原生 PNG，TDS2024B 以 USBTMC 明確用 BMP，TBS1052B 以 USBTMC 明確用 JPEG。
Core 還原暫時設定與 Timeout，適用時嘗試刪除儀器暫存檔。
TBS2074 Storage Case Save/Recall Setup Slot 1、Save/Display/Query Reference Slot 1；兩個 Slot 都可能覆寫，不保留原內容。
Image 與 CH1 CSV Waveform Save 在目前儀器目錄使用產生的 8.3 Filename，做 OPC Completion Check 並還原 Timeout；檔案留在儀器。
TDS2024B/TBS1052B 排除全部 Setup、Reference、File-save、Storage-only Setting，仍保留 Host Capture。

通過操作人員確認前，顯示適合且穩定的 CH1 Signal（例如 Probe Comp/Demo），為 TBS2074 Timebase Position 檢查啟用 Horizontal Delay Mode，並提供可寫 Storage，Waveform Save Format 設為 CSV/SPREADSheet。
INTERNAL 不在公開 Format Setter 子集，Runner 不修改。
AutoSet 獨立驗證；TDS2024B/TBS1052B 在 AutoSet 與其後 SESR Read 暫用 10000 ms Timeout，在 `finally` 還原。
一般操作保留 Session Timeout；Keysight Auto Scale Fallback 與 TBS2074 AutoSet 行為不變。

結果使用共用 CLI Report/Artifact Privacy 處理，存於 `.tmp_tests/live_cli_check/` 的 Timestamp Run 與去識別化 `shareable/` 報告。
`-DebugArtifacts` 另保留 `private/` 與詳細 Shareable Artifact。Runner 存在不代表已做硬體驗證。
PASS 要求實際執行且驗證成功；FAIL 表示執行或驗證失敗；N/A 是不支援操作或特定不適用狀態；NOT TESTED 是未執行或因前置失敗而阻擋的直接檢查，獨立計數。
指定真實 Resource 的 PASS Case 只證明該 Case；N/A/NOT TESTED 仍未驗證。整體 PASS 代表適用 Case 全通過，不代表每個 Core/WebUI 操作都有 One-shot CLI 實機結果。
Runner 先用 `trigger-mode --query`，再驗證相同 Mode 的 Write/Readback，之後才測 Edge Setter。
Edge Same-value 要求目前 Edge Mode；Combined Edge 另要求類比 Source。Runt/TV Setter 要求目前相應 Mode，且設定在公開 Setter 子集；否則 N/A，不切 Trigger Mode。
支援的唯讀 Trigger Query 仍可用。其他 N/A 代表 Model 不支援，或目前設定無法安全使用公開 Setter。
Edge Numeric Readback 採 `max(1e-12, abs(expected) * 1e-3)`，與 Keysight 相同；其他 Tektronix Numeric Comparison 保留既有 Tolerance。
Edge 不符時回報 Before、After、Difference、Tolerance。

<a id="live-cli-validation"></a>

### CLI 實機驗證

公開 Runner 接受四個註冊 Keysight InfiniiVision Target 與上述三個 Tektronix Target，在實機檢查前選擇適用 Case。
Keysight 基準需提供預期 Model Target、Transport 與明確 VISA Resource：

```powershell
.\scripts\live-cli-check.ps1 -Target keysight-dsox4034a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE
```
將 CH1 Probe 接到前面板 Probe Demo/Probe Comp，確認穩定 Waveform，並先設為 MAIN（正常 Horizontal）Timebase。
完整 Validator 不使用 XY/Roll。Hardware-free Preflight 後，Runner 顯示偵測 Instrument/Resource，等待 Enter 才開始改狀態驗證；可在此用 Ctrl+C 取消。

Runner 暫改 Acquisition、CH1 Display/Coupling、Timebase、Edge Trigger 與 Waveform Transfer。
承諾還原 Acquisition Type 與適用 Average Count、CH1 Display/Coupling、Timebase Scale/Position/Reference、Edge Source/Slope、CH1 Edge Level。
Acquisition Action 會改 Run/Stop，CLI 基準不快照或還原原 Running/Stopped。

不還原原 Generic Trigger Mode，儀器可能留在 Edge。
Waveform Source/Format/Points 是 Transfer-session Setting，沒有既有公開還原路徑，因此不還原，Format 可能留在 WORD。
這些已記載限制不讓 Cleanup 失敗，但承諾還原的任何失敗會。
最終 System Error Queue 必須乾淨，否則 Run 報 FAIL。

Hardware-free Preflight 與自動測試不是實機驗證；需在準備好的儀器上執行 Script 才能宣稱 Live PASS。

<a id="workflow-live-validation"></a>

#### Workflow 實機驗證

在註冊 Keysight Target 或三個 Tektronix Target 上，以 `live-workflow-check.ps1` 執行既有 Workflow Suite：

```powershell
# Default: minimal artifacts
.\scripts\live-workflow-check.ps1 -Target tektronix-tds2024b -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE

# Retain detailed artifacts
.\scripts\live-workflow-check.ps1 -Target tektronix-tds2024b -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE -DebugArtifacts
```
Runner 執行 Hardware-free Preflight、驗證偵測 Model，再等待 Enter 才執行 Acquisition Action。
準備可見、穩定 CH1 Probe Comp Waveform 與可靠既有 Trigger。
TBS1052B/TDS2024B 按 Enter 前另確認 Trigger View OFF、Display YT 而非 XY，且不在 Scan Mode；AUTO Trigger 使用快於 100 ms/div 的 Timebase 避免 Scan。
涵蓋 `measure-sweep`、`measure-log`、`measure-until`（Match 與預期 Timeout）、`capture-batch`、`capture-until`、`capture-monitor`、`triggered-measure-loop`、`triggered-capture-series`、`sequence`。
Sweep Item 依 Core Capability，所以 TDS2024B 省略 `vrms`，保留其餘 Case。

Keysight 還原原 Running/Stopped 並驗證 Readback。
Tektronix 不快照原 Acquisition State：Suite 前送 `run`，Cleanup 送 `stop-acquisition`，啟動或 Workflow 失敗後也一樣。
Tek Cleanup PASS 代表 Stop 命令成功且 Native Status 乾淨，不代表獨立讀回 STOPPED 或還原原狀態。
Report 將 Original-state Snapshot 與 Normalized Error-queue Check 標 N/A。

Tek Workflow Case 驗證 Core Native SESR/Event Status，包含預期 Timeout。
Runner 不在 Workflow 後增加會消耗狀態的 Read，也不以 Keysight Error Queue 替代。
Stale Event 由 Core Workflow Preflight 處理；最初 `run` 回報 Error 會讓驗證失敗，但仍執行 Stop Cleanup。

Report/Artifact 使用 `.tmp_tests/live_workflow_check/` 與上述共用保留政策。
DVM、Serial、Segmented Memory Live Runner 不接受 Tektronix Target。
獨立 `preflight-cli.ps1` Target List 與 `all` 仍只涵蓋四個 Keysight Target；Tek Preflight 在 CLI/Workflow Runner 內選擇。

<a id="dvm-live-validation"></a>

#### DVM 實機驗證

依 License 可用的選配 DVM 驗證與基準分開執行：

```powershell
# Default: minimal artifacts
.\scripts\live-dvm-check.ps1 -Target keysight-dsox4024a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE

# Retain detailed artifacts
.\scripts\live-dvm-check.ps1 -Target keysight-dsox4024a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE -DebugArtifacts
```
將 CH1 Probe 接到 Probe Demo/Probe Comp，確認穩定 Waveform，且 CH1 目前不是 Trigger Source，再通過操作人員確認。
Runner 暫改 DVM，DVM Auto Range 也可能調整 CH1 Vertical Scale/Offset；會透過既有公開 CLI 嘗試還原原 DVM 與 CH1 Scale/Offset。

DVM 依 Instrument Option/License。
唯讀 Availability Probe 回報特定 Missing-hardware（功能不可用／未授權）時，報 `SKIP / NOT AVAILABLE` 而非 Failure，不執行改狀態 DVM Test。
Transport Failure、Timeout、Malformed Response 或其他 Instrument Error 仍是 Failure。

Hardware-free Preflight 只檢查必要 CLI 路徑，不是實機驗證。

<a id="segmented-memory-live-validation"></a>

#### Segmented Memory 實機驗證

依 License 可用的選配 Segmented Memory 驗證分開執行：

```powershell
# Default: minimal artifacts
.\scripts\live-segmented-check.ps1 -Target keysight-dsox4034a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE

# Retain detailed artifacts
.\scripts\live-segmented-check.ps1 -Target keysight-dsox4034a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE -DebugArtifacts
```
CH1 Probe 接 Probe Demo/Probe Comp，確認穩定可見 Waveform 與可靠 Trigger。
開始前 Acquisition Mode 必須為 `realtime`。
Runner Identify 並唯讀檢查此前置條件後，等待 Enter 才變更 Segmented Memory。

Runner 暫進 Segmented Memory Mode、執行有限的兩 Segment BYTE Capture，將 Live Artifact 寫於 Run Directory。
Cleanup 回到 `realtime`；Cleanup 失敗或最終 System Error Queue 非空都使驗證失敗。

Segmented Memory 可能依 Option/License。
首次 Enable 若回特定 Missing-hardware 且其餘 Error Queue 乾淨，報 `SKIP / NOT AVAILABLE`，不繼續 Capture。
Transport Failure、Timeout、Malformed Response 或其他 Instrument Error 仍是 Failure。

Hardware-free Preflight 只檢查必要 CLI 路徑，不產生 Simulated Capture Artifact，不是實機驗證。

<a id="serial-live-validation"></a>

#### Serial 實機驗證

依 License 可用的選配 Serial 驗證分開執行：

```powershell
# Default: minimal artifacts
.\scripts\live-serial-check.ps1 -Target keysight-dsox4034a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE

# Retain detailed artifacts
.\scripts\live-serial-check.ps1 -Target keysight-dsox4034a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE -DebugArtifacts
```
維護中的 Runner 使用 UART 作代表，不重複完整 UART/I2C/SPI/CAN Matrix。
Serial Bus 1 準備外部 UART TX 接 CH1：115200 Baud、8 Data Bits、No Parity、Idle High、LSB First，持續重複 `0x01`。
CH2 選為 UART TX Decode Source，但代表性 RX/Lister Case 不要求 CH2 Live Traffic。

開始前 Search 必須 OFF；ON 視為前置失敗，不修改。
唯讀 Availability、Search、Lister、Edge Trigger 檢查通過後才顯示操作人員確認。
Lister Export 需要真正可 Decode 的 UART Traffic；`+109 No Data For Operation` 表示未 Decode，為 Failure，不是 Skip。
另一個已設定 Serial Bus 可能保留 CH1/CH2 或衝突 Protocol Resource，造成 `-221 Settings conflict`；也是 Failure，不是 `NOT AVAILABLE`，Runner 不自動修改 Serial2。

Serial Search/Trigger 只驗證 UART Configure/Query Readback，不 Run/Single/Force/Wait/Acquire Waveform。
Cleanup 關閉 Runner 啟用的 Search、還原 Lister Display/Reference，將 Global Trigger Mode 回 Edge，還原 Edge Source/Slope 與適用 Analog Level。
公開 CLI 無法恢復任意原 Trigger Mode，因此 Cleanup 承諾 Edge，而非原 Generic Mode。
Serial1 刻意不還原；UART Configure 成功後留在所載 UART Test Baseline，若部分改動後失敗，可能留部分 Test Setting。

獨立結構化 `-241` Missing-option，且 Error Drain 正常結束、其餘乾淨時，報 `SKIP / NOT AVAILABLE`。
Profile/Parameter Rejection、`-221`、`+109`、Transport Failure、Timeout、Malformed Response、Mixed Error Queue 或其他 Instrument Error 仍是 Failure。
Hardware-free Preflight 不是實機驗證，需在準備好的儀器上執行 Script 才可宣稱 Live PASS。

<a id="standalone-auto-scale-autoset-live-validation"></a>

### 獨立 Auto Scale / AutoSet 實機驗證

`scripts/live-autoscale-check.ps1` 要求一個精確註冊 Target、明確 VISA Resource，且有操作人員在儀器旁。
USB 驗證接受 `keysight-dsox2004a`、`keysight-dsox3024a`、`keysight-dsox4024a`、`keysight-dsox4034a`、`tektronix-tbs2074`、`tektronix-tds2024b`、`tektronix-tbs1052b`。
各註冊 Target 的驗證可選 USB/TCPIP 與相符 Resource。預設 System VISA；`-Backend "@py"` 選 PyVISA-py。

```powershell
.\scripts\live-autoscale-check.ps1 -Target keysight-dsox4034a -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE
.\scripts\live-autoscale-check.ps1 -Target tektronix-tbs2074 -Connection usb -Resource $env:SCOPES_TOOL_RESOURCE -Backend "@py"
```
Runner 在硬體存取前解析 Resource Syntax，檢查 Simulated Identity 與 Dry-run/Simulate Basic Auto。
接著驗證 Physical Identity 並顯示 Model-specific 英文警語。只有空白 Enter 確認；其他輸入在 Clear Status、Snapshot Query、Auto 前取消。
準備合適穩定 CH1 Signal、匹配 Probe Attenuation，並移除所有輸入的未知／敏感 DUT Signal。
Auto 可能誤認低頻、微弱、窄脈衝或不穩定訊號，並改變 Channel Display、Vertical、Horizontal、Trigger、Acquisition 及其他依 Model 而定的前面板狀態。

Keysight 用公開 `autoscale --source-channel 1`。
`auto-basic` 與 `auto-ch1` 分開：乾淨回退至裸 `:AUToscale` 可讓 Basic Auto 通過，但 CH1 Selection 為 N/A、未驗證。
Basic Check 不測 Acquisition-mode 或 Channel-selection Auto Option。
Tektronix 用裸 `autoscale`，驗證 `AUTOSet EXECute` 與 Native Status，不送不支援的選填 Auto Control。
PASS 證明命令執行與狀態檢查，不保證最佳 Waveform Scaling 或 Signal Recognition。

Keysight 快照所有類比 Channel 的 Display/Coupling/Probe Ratio/Scale/Offset、Timebase Scale/Reference/Position、Acquisition Type/Active Average Count、Trigger Mode/Holdoff；原 Mode 為 Edge 時另記 Edge Source/Slope 與 Analog Channel Level。
Auto 嘗試後即使失敗也還原，使用公開 CLI Setter/Readback，獨立 Restore 失敗後仍繼續其他項。
Restore PASS 只涵蓋已快照設定。
其他 Channel Setting、Inactive Average Count、非 Edge Trigger Parameter、Trigger Filtering/Sweep、Cursor、Measurement、Math、Reference、Zoom、Save To、Run/Stop 都不還原。
Tektronix 不自動還原；操作人員須檢查並手動恢復未涵蓋設定。
Error/Event Read 與 Baseline Drain/Clear 會消耗 Diagnostic State，無法還原。
DSO-X 4034A Auto 可能讓 Save To 留在 `Please Select`；需要時重選 USB Destination。直接在前面板 Auto Scale 也可能如此，不代表 Scopes Tool SAVE 失敗。

Console Result 包含實際 Auto Command、Fallback、Restore Result、限制與 PASS/FAIL/N/A 總數。
獨立隱私保護報告存於 `.tmp_tests/live_autoscale_check/run_*/shareable/`；預設只保留 `report.json`、`summary.md`，`-DebugArtifacts` 另留 Private Raw 與詳細 Shareable Artifact。
Private Artifact 必須保密。Hardware-free Check 不提供實機證據；即使整體通過，N/A CH1 仍不證明 Source Selection。
