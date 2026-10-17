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
Sample Callback；不引入非同步 Runtime、Scheduler、Persistence Layer 或 Event Bus。

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
