# Scopes Tool WebUI 與 Desktop 使用指南

[English](USER_GUIDE.md)

瀏覽器 WebUI 與 Electron Desktop 共用相同控制介面及本指南，使用 Core 的型號、
能力與安全規則。確切支援的型號／Backend／Transport 組合及選配功能限制，
請查閱[支援型號](../core/supported-models.zh-TW.md)。

## 啟動與關閉應用程式

Windows 目錄封裝請保留所有解壓縮檔案，包括唯一共用的 `_internal` 目錄。
Desktop 啟動 `Scopes Tool.exe`；瀏覽器 Launcher 啟動
`scopes-tool-webui-launcher.exe`。已安裝的 Python 應用程式提供
`scopes-tool-webui-launcher` 命令。

瀏覽器 Launcher 啟動 Localhost Server，確認服務身分與就緒後開啟瀏覽器。
未明確指定連接埠時，從 8025 開始最多嘗試 100 個連接埠；必要時可在 Launcher
手動輸入。明確指定且已占用的連接埠會直接失敗，不自動改用其他連接埠。
直接執行 `scopes-tool-webui` 的 Server 預設為 `127.0.0.1:8025`，不提供 Launcher 視窗。

關閉 Launcher 才會停止其 Server；只關閉瀏覽器分頁不會停止服務。
關閉 Desktop 視窗會要求 Host 關閉；兩者都會等待工作與 Session 清理。
若顯示 **Shutdown incomplete** 或清理警告，請保留應用程式，待操作完成後重試關閉。
阻塞中的 VISA I/O 不會被強制中斷，關閉時也不會隱含執行 Safe Cleanup。

## 語言、主題與離線 Help

使用頁首切換 English／繁體中文，以及 System／Light／Dark 主題。
語言保存在瀏覽器 Local Storage，主題使用既有本地 Cookie。
Launcher 本身僅提供英文。Command ID、Model ID、SCPI、VISA Resource、JSON Key
與原始診斷保持原文。

**Help** 依目前介面語言開啟已封裝的指南，並傳遞目前主題偏好。
瀏覽器 WebUI 開啟新分頁；Desktop 使用系統預設瀏覽器開啟相同的本地 WebUI Help，
閱讀時請保持 Desktop 執行。沒有獨立的 Desktop Help Bundle。
Help 不需要網際網路，但由 WebUI 提供的頁面需要本地 Server 持續執行。
CLI Help 也可透過 `scopes-tool user-guide --lang zh-TW` 獨立開啟。

## 選擇模式與裝置

先使用 **Simulate** 在無硬體環境練習。選擇已註冊的規劃型號，Core 模擬器會提供
其身分及能力；啟用儲存時，模擬輸出仍會寫入檔案。
**Dry-run** 只規劃已有 Core Planner 的命令，許多設定及流程在此模式不可用，
也不會開啟儀器 Session。

使用 **Live** 時：

1. 確認探棒、輸入額定值、DUT、擷取及觸發條件。
2. 在 Device / Resource 設定選擇 System VISA 或 PyVISA-py。
   System VISA 需要另外安裝 Keysight IO Libraries 或 NI-VISA，絕不自動改用 `@py`。
3. 輸入確切 VISA Resource，或明確執行搜尋。搜尋使用 Live-only Discovery，
   可能開啟列出的 Resource 並查詢 `*IDN?`。不要猜測儀器位址或將範例佔位符當成裝置。
4. 選擇目標 Resource 並等待識別。偵測到的 `*IDN?` 型號具權威性，規劃型號不可覆蓋。
5. 使用 Supported Devices 與命令可用性說明，確認連線已開放 Product Live 後再操作。

七個註冊型號皆開放 System VISA USB。System VISA TCPIP 與 `@py` TCPIP
只開放 DSOX4024A、DSOX4034A、TBS2074。`@py` USB 未開放 Product Live。
Bluetooth、GPIB、ASRL、自訂 Backend 不會因此取得支援。
識別與搜尋是診斷，不代表授權其他操作。WebUI 不可啟用貢獻者 Validation Mode。

變更模式、Resource 或規劃型號會改變結果情境，不可將前一情境的數值當成目前儀器狀態。
選擇支援的裝置後可能自動讀取一次 Live Data Snapshot；Live Data 不會持續輪詢或串流波形。

## 命令與設定

透過 Command Browser 選擇命令，必要時篩選或顯示 Advanced 命令。
不支援的命令保持停用並提供原因。選擇命令或瀏覽編輯器不會執行儀器 I/O。

設定操作請先 **Read current settings**，修改所需欄位後 **Apply**，再檢查回讀結果。
尚未套用的編輯會保留，不會被後續讀取覆蓋。
一般資訊與診斷使用明確的 Read 或 Run 動作。
同一時間只能執行一個前景操作，裝置管理動作也共用此限制。

Basic Controls 提供 Run、Stop、Single、Force Trigger 及黑底／白底截圖捷徑。
Acquisition Control 另有 Single + Wait，預設逾時 5 秒，逾時強制觸發預設關閉。
Autoscale、擷取控制、Setup 與輸出設定可改變儀器狀態，請先確認影響。
Autoscale 可能改變通道、時基、觸發、游標、Math、量測及 Reference 顯示，沒有自動還原。
Command Browser 不提供 Setup Recall 或任意 SCPI。

Channel、Timebase、Trigger、Measurement、Reference Memory、Cursor、Annotation、
WGEN、DEMO、Serial、Search、Segmented Memory 工作區依 Core 能力資料提供。
可回讀不代表所有 Setter 或選項都支援；Profile 也不能證明硬體選配授權已安裝。
TBS2074 Time Offset 要求 Horizontal Delay Mode 已為 ON，工具不會自動切換。
TBS2074 游標來源選擇可能重設擷取。請遵守支援型號中的個別限制。

## 輸出資料夾與儲存資料

在 Basic Controls 設定共用 **PC output folder**；空白代表 `data`。
**Select Folder** 使用 Windows 資料夾選擇器，取消不改變原值。
**Open Folder** 必要時建立有效目錄，並透過 Windows Shell 開啟。
此設定屬於瀏覽器 Session，提交工作時會保留該次使用值。

截圖與波形擷取將電腦端檔案寫到此根目錄，工作流程使用各自子目錄。
Serial Lister Export 必須輸入檔名，且不覆寫既有檔案。
輸出失敗會回報錯誤，不會默默改用其他資料夾。
沒有電腦端產物的工作不建立或驗證資料夾；Dry-run 只規劃路徑。

Save Image、Save Waveform、Save Setup 使用儀器端儲存空間，不產生電腦下載，
也不繼承 PC output folder。圖片及波形儲存必須各自指定檔名；Setup 使用槽位或儀器端檔案。
TDS2024B 與 TBS1052B 不提供 Setup、Reference Memory 或儀器端儲存。
TBS2074 支援原生黑底 PNG 截圖；TDS2024B BMP 與 TBS1052B JPEG 各有其限制。
Tektronix 波形擷取使用已顯示通道、BYTE，最多要求 1000 點，不會自動開啟隱藏通道。

## 工作流程與 Generic Sequence

在支援型號上，為量測記錄、條件監控、週期擷取、觸發量測／擷取及分段擷取選擇
有限次數、觸發逾時、保留上限與儲存選項。
Capture Monitor 顯示有界限的滾動波形視窗及整個 Session 統計；連續擷取屬於獨立記錄，
中間可能有空隙，並非連續即時波形串流。支援的流程可停用儲存；獨立擷取一定產生檔案。

Generic Sequence 與 CLI 使用相同 Core 驗證。七個動作為 `wait`、`single`、
`wait-trigger`、`measure`、`capture`、`screenshot`、`cleanup`，並受型號能力限制。
設定 1–255 個步驟、1–255 次迴圈、最多 65,025 次步驟執行，每個迴圈最多
10 個 capture/screenshot 步驟合計。在本地編輯後以 Run 提交為一個工作。
無效文件會在執行前回報驗證錯誤。Sequence 不接受任意 SCPI Macro。

## 工作、結果與停止

Result History 顯示進度及 `queued`、`running`、`completed`、`failed`、`cancelled`。
Workspace Result 顯示該命令及執行情境最近的成功結果，後續失敗不會清除它。
完整結構化內容與原始診斷請查看 Result Detail，檔案請使用 Open Folder。
介面不另外提供產物下載連結。

Cancel 立即取消尚在佇列的工作；執行中的工作接受合作式停止要求，直到 Core 執行與
清理完成前仍維持 Running。已完成部分可能保留在產物內；取消不會自動還原所有設定，
也不執行 Safe Cleanup。不要將停止要求誤認為關閉完成。
Segmented Capture 保留實際 Core 終態，包括較晚收到取消要求前已完成的結果。

Doctor 在唯讀 Snapshot 前檢查既有狀態，最後再檢查一次；讀取狀態可能消耗錯誤項目。
Smoke 會量測、傳輸波形與截圖，並做最後狀態檢查。
WebUI 的 **Save diagnostic artifacts** 預設關閉；啟用時使用共用 PC 輸出根目錄。
請考量影響後明確執行診斷。

## 疑難排解與限制

| 現象 | 處理方式 |
| --- | --- |
| Launcher 無法啟動 | 檢查所選本地連接埠，提供手動備援時可改用手動連接埠。 |
| Resource 出現但命令停用 | 檢查偵測身分、Backend、Transport、執行模式及支援原因。 |
| System VISA 失敗 | 安裝或修復外部 IVI Runtime；`@py` 只適用於其已開放連線。 |
| 設定顯示舊值 | 確認執行情境、明確 Read，Apply 前檢查未套用編輯。 |
| 擷取或截圖失敗 | 檢查已顯示通道、型號格式／點數限制、儀器儲存與電腦權限。 |
| Help 無法載入 | 保持本地 Server／Desktop 執行，並確認解壓縮安裝完整。 |
| 無法完成關閉 | 等待 VISA I/O 與清理完成，閱讀警告後重試關閉。 |

WebUI 僅限 Localhost，沒有遠端存取、身分驗證、多儀器 Session、WebSockets/SSE、
一般波形串流或自動 Live Data 輪詢。FFT 與 Advanced Math 使用 Metadata 驅動表單，
並非每項 Core 功能都有專用編輯器。介面刻意未提供的操作請使用 CLI 或已記載的整合 API。
分享日誌或儲存檔案前，請移除私人 Resource 位址與序號。
