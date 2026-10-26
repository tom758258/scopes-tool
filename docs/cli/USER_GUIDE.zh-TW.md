# Scopes Tool CLI 使用指南

[English](USER_GUIDE.md)

本指南適用於已安裝的 `scopes-tool` 命令或 Windows CLI 執行檔的一般操作。
功能取決於[支援型號](../core/supported-models.zh-TW.md)所列的確切型號、
Backend、Transport 及儀器已安裝選配。個別命令的參數請使用
`scopes-tool <command> --help` 查詢。

## 啟動與開啟 Help

在解壓縮後的應用程式目錄開啟 PowerShell。執行檔與共用 `_internal`
目錄必須放在一起，不可只複製執行檔。

```powershell
.\scopes-tool.exe --help
.\scopes-tool.exe user-guide
.\scopes-tool.exe user-guide --lang en
.\scopes-tool.exe user-guide --lang zh-TW
```

Python 安裝請將 `.\scopes-tool.exe` 換成 `scopes-tool`。
`user-guide` 預設英文，使用系統瀏覽器開啟已封裝的本地 HTML；不需要網際網路或
執行中的 WebUI，也不會開啟儀器 Session。缺少 Help 或瀏覽器啟動失敗時，
stderr 會顯示錯誤並回傳 Exit Code `1`；無效參數回傳 `2`。
從 CLI 開啟的 Help 跟隨系統色彩主題。

## 選擇執行模式

- `--simulate` 使用 Core 模擬器，不連接硬體；會儲存產物的命令仍會在電腦寫入模擬檔案。
- `--dry-run` 驗證並規劃支援的操作，不開啟儀器 Session，也不建立輸出檔案。
  是否可用依命令而定。
- 單次 Live 命令需要明確提供 `--resource` 或 `SCOPES_TOOL_RESOURCE`。
  `--model` 不可取代偵測到的 Live 身分；模擬及規劃時則選擇已註冊的標準 Model ID。

先在無硬體環境操作：

```powershell
.\scopes-tool.exe identify --simulate --json
.\scopes-tool.exe capabilities --model tektronix-tbs2074 --json
.\scopes-tool.exe measure --channel 1 --item vpp --simulate --json
.\scopes-tool.exe capture --channel 1 --points 1000 --csv data\waveform.csv --simulate --json
.\scopes-tool.exe capture --channel 1 --points 1000 --dry-run --json
```

每次儲存請使用新的輸出檔名。模擬結果不代表實機支援。
獨立命令的模擬設定只存在於該次呼叫；Worker 模擬會在同一個 Worker Session
保留成功操作後的狀態。

## 連接儀器

System VISA 是預設 Backend，需要另外安裝 Keysight IO Libraries 或 NI-VISA。
Scopes Tool 不封裝該 Runtime，也不會自動改用 PyVISA-py。
內含的 `@py` Backend 可透過 `--visa-library @py` 明確選擇。

七個註冊型號皆開放 System VISA USB Product Live。
System VISA 或 `@py` 的 TCPIP/LAN 僅開放 DSOX4024A、DSOX4034A、TBS2074。
`@py` USB、Bluetooth、GPIB、ASRL 及自訂 Backend 未開放 Product Live。
明確指定 `@ivi` 會歸類為自訂 Backend；使用 System VISA 時請不指定選擇器。

1. 連接前確認探棒、輸入額定值、DUT、觸發及擷取條件。依操作不同，查詢可能消耗
   狀態或暫時改變儀器設定。
2. 使用 `list-resources` 列出 Backend 回報的 Resource。
   只有明確希望開啟列出的 Resource 並查詢 `*IDN?` 時，才使用
   `list-resources --live-only`。
3. 完整複製預定使用的 Resource，不要從範例猜測。
   `USB0::...::INSTR` 與 `TCPIP0::<HOST>::inst0::INSTR` 僅為格式示意。
4. 設定 Resource，先識別儀器，再執行 Product 命令：

```powershell
$env:SCOPES_TOOL_RESOURCE = "<RESOURCE>"
.\scopes-tool.exe identify --resource "$env:SCOPES_TOOL_RESOURCE" --json
.\scopes-tool.exe measure --resource "$env:SCOPES_TOOL_RESOURCE" --channel 1 --item vpp --json
```

使用已開放的 PyVISA-py LAN 連線時，請在各適用命令加上 `--visa-library @py`。
搜尋結果受驅動及網路環境影響；列出 Resource 或 Identify 成功不代表允許 Product 操作。
未知或不相符的型號會被拒絕。

## 讀取與變更設定

變更設定前先明確查詢，例如：

```powershell
.\scopes-tool.exe acquisition --query --simulate --json
.\scopes-tool.exe channel-scale --channel 1 --query --simulate --json
.\scopes-tool.exe timebase-scale --query --simulate --json
.\scopes-tool.exe trigger-edge --query --simulate --json
```

Run、Stop、Single、Force Trigger、Autoscale、Setup Recall、輸出控制與設定命令
可能改變前面板狀態。Autoscale 可改變通道、時基、觸發及顯示中的分析功能。
確認可接受影響後再操作。一般清理不會自動執行 Reset、Preset、Autoscale、
Setup Recall 或 Return-to-local。

`single` 啟動單次擷取等待；`single-wait` 另外提供有界限的觸發等待。
`capture` 預設傳輸目前波形，只有明確指定才等待觸發。
觸發逾時不會強制觸發，除非明確啟用對應的 force-on-timeout 選項。
不要假設每個命令都會將擷取狀態恢復為原本的執行狀態。

## 量測、擷取與檔案

`measure` 與 `measure-sweep` 讀取支援的量測。
`measure-install`、`measure-clear`、`measure-stats` 可變更前面板量測設定。
請檢查無效量測 Sentinel 與儀器錯誤；原始數值看似正常並不足以證明量測有效。

`capture` 儲存電腦端 CSV、Metadata，並可選擇繪圖。
Tektronix 擷取使用 BYTE、已顯示的類比通道，最多要求 1000 點；`all` 包含隱藏通道，
可能直接失敗，不會自動開啟通道。Tektronix 截圖格式依型號而異：TBS2074 為黑底 PNG、
TDS2024B 為 BMP、TBS1052B 為透過 USBTMC 的 JPEG。
選擇格式或選配功能前請查閱支援型號。

`screenshot` 與 `capture` 將檔案取回電腦；`save-image`、`save-waveform`、
`setup-save` 寫入儀器端儲存空間，不是電腦。
Reference Memory、DVM、WGEN、Math、FFT、Serial、Search 與 Segmented Memory
仍受型號及必要選配限制。

有限次工作流程包括適用型號上的 `measure-log`、`measure-until`、`capture-batch`、
`capture-until`、`capture-monitor`、`triggered-measure-loop`、
`triggered-capture-series`、`segmented-capture`、`sequence`。
請選擇有限次數、逾時及輸出位置。部分流程提供 `--no-save`；獨立 `capture` 一定產生檔案。

Generic Sequence 支援 `wait`、`single`、`wait-trigger`、`measure`、`capture`、
`screenshot`、`cleanup`，並受型號能力限制。
限制為 1–255 個步驟、1–255 次迴圈、總計 65,025 次步驟執行，每個迴圈最多
10 個 capture/screenshot 步驟合計。不接受任意 SCPI。
取消採合作式機制，阻塞中的 VISA I/O 可能延後完成；取消不會自動執行 Safe Cleanup。

## Worker 操作

Worker 提供本地佇列命令服務供自動化使用，與瀏覽器 WebUI 分開。
在一個終端機啟動模擬 Worker：

```powershell
.\scopes-tool.exe worker --simulate --model keysight-dsox4024a --port 8765 --format jsonl
```

在另一個終端機操作：

```powershell
.\scopes-tool.exe wait-ready --port 8765 --json
.\scopes-tool.exe send-command --port 8765 --command identify --json
.\scopes-tool.exe status --port 8765 --json
.\scopes-tool.exe stop --port 8765 --json
```

Live Worker 必須同時提供 `--live --resource <RESOURCE>` 及正確的預期標準 `--model`。
模式、型號與 Resource 在啟動時固定。命令被接受只代表已排入佇列，不代表完成；
請觀察 `job_finished` 或終態 `last_job`。會輸出的 Worker 工作需要明確輸出位置。
Stop 取消佇列工作並要求執行中的工作合作式取消；請等待清理及最後 Summary，
才視為關閉完成。不要將 Worker 或 WebUI 連接埠暴露至不受信任的網路。

## 錯誤與疑難排解

| 現象 | 處理方式 |
| --- | --- |
| System VISA 無法載入 | 安裝或修復外部 IVI Runtime；Scopes Tool 不會自動切換 Backend。 |
| 找不到 LAN Resource | 檢查儀器 LAN 設定與網路搜尋；使用您已知的明確 Resource。 |
| Product 操作被拒絕 | 檢查確切型號／Backend／Transport 矩陣及命令能力；Identify 成功並不足夠。 |
| 擷取或截圖失敗 | 檢查顯示通道、點數／格式限制、儲存空間、目的地權限與原始診斷。 |
| 命令選項被拒絕 | 使用 `<command> --help`；支援範圍與 Dry-run 可用性依命令不同。 |
| Help 無法開啟 | 閱讀 stderr，手動開啟回報的 HTML；缺少檔案時修復安裝。 |
| Stop 需要時間 | VISA I/O 不會被強制中斷；等待操作逾時及 Session 清理完成。 |

支援的命令可加上 `--json`。機器模式 stdout 僅含結構化 JSON/JSONL；
`--log-scpi` 將診斷寫到 stderr。請檢查程式結束碼、`ok` 與命令專屬狀態。
單次儀器錯誤通常回傳 `1`；Parser 使用錯誤回傳 `2`；單次 JSON 身分不符回傳 `3`。
Worker Client 的驗證失敗回傳 `2`，執行、連線與受理失敗回傳 `3`。
不要從受理結果推論工作成功。`user-guide` 是本地文字模式工具，不接受 `--json`。

`doctor` 在 Snapshot 前讀取狀態，可能消耗一筆錯誤；`smoke` 會進行量測、擷取、
截圖及狀態檢查，也可能寫入產物。讀取 Error Queue 會消耗項目。
請考量儀器狀態後明確執行診斷；分享日誌或產物前移除私人 Resource 與序號。
