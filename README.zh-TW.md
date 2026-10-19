[English](README.md)

# Scopes Tool

Scopes Tool 是採廠商中立架構的示波器工具，目前支援
[支援型號](docs/core/supported-models.zh-TW.md)文件中已註冊的 Keysight
InfiniiVision 與 Tektronix 型號。專案提供單一 Python 發行套件 `scopes-tool`，
並保留獨立的 `scopes_tool_core`、`scopes_tool_cli` 與 `scopes_tool_webui`
import package。CLI、Worker、瀏覽器 WebUI 與 Electron Desktop 共用相同的 Core 行為。

實機身分來自儀器實際的 `*IDN?` 回應。未知、未註冊或不符的廠商、型號、
設定檔或驅動程式均會遭到拒絕；規劃用型號不會覆寫偵測到的實機身分。

**VISA 後端：** 預設使用 System VISA，需另外安裝 Keysight IO Libraries、NI-VISA
等 IVI 執行環境。Scopes Tool 不隨附這些執行環境，也不會自動改用 `@py`。
Python 安裝與 Windows 套件已包含 PyVISA、`pyvisa-py`、`psutil` 與 `zeroconf`。
後兩者分別支援跨網路介面的 TCPIP/VXI-11 探索與 HiSLIP mDNS 探索；
是否能找到儀器仍取決於儀器與網路環境。

產品的實機操作支援僅限[支援型號](docs/core/supported-models.zh-TW.md)列出的精確型號、
傳輸方式與後端組合。PyVISA-py（`@py`）的產品操作僅開放 DSOX4024A、DSOX4034A
及 TBS2074 的 TCPIP/LAN 連線。透過 `@py` 使用 USB 尚未開放產品支援；
所需的 PyUSB、libusb 與驅動程式亦未隨附。Bluetooth（`@bt`）與明確指定的自訂後端
尚未開放產品支援。連線診斷成功不代表產品操作已獲授權。
Simulation 與支援的 dry-run 操作不會開啟真實儀器連線。

## 功能特性

- 透過 CLI、Common v2 Worker、僅限本機的瀏覽器 WebUI 或 Electron Desktop 操作。
- 在文件規定的範圍內支援已註冊的 Keysight DSOX2004A、DSOX3024A、DSOX4024A、
  DSOX4034A，以及 Tektronix TBS2074、TDS2024B、TBS1052B。
- 設定擷取、類比通道、時基與顯示；擷取波形及螢幕截圖；查詢量測與統計資料。
- 依型號使用 DVM、Math、FFT、WGEN、Reference、Trigger、Search、Serial
  與分段記憶體操作。
- 執行有限次量測、記錄、週期及觸發擷取工作流程，以及 capture-until、
  capture-monitor 與 Generic Sequence v1。
- 在支援的操作中使用無硬體模擬與 Core dry-run 規劃，並產生供自動化使用的
  JSON、JSONL、CSV 與主機端擷取產物。
- WebUI/Desktop 可切換英文與繁體中文、選擇 System、Light 或 Dark 外觀，
  並開啟內建離線說明。
- Windows onedir 套件中的 CLI、Launcher 與私有 Host 共用一份 Python 執行環境目錄，
  並與具備獨立 Electron/Chromium 執行環境的 Electron Desktop 一起提供。

功能是否可用取決於型號、能力設定檔及儀器已安裝的選配。
命令與工作流程限制請參閱[支援型號](docs/core/supported-models.zh-TW.md)及
[CLI README](docs/cli/README.zh-TW.md)。Generic Sequence 組合既有的 Core 操作，
不提供任意 SCPI 巨集功能。

## 專案結構

根目錄 `pyproject.toml` 定義單一發行套件及 Python 套件版本；
`desktop/package.json` 的應用程式版本必須相同。
Build 範例中的 `<version>` 代表 `[project].version`。

```text
src/
  scopes_tool_core/
  scopes_tool_cli/
  scopes_tool_webui/
desktop/
examples/
tests/
  core/
  cli/
  packaging/
  webui/
  tooling/
docs/
  core/
  cli/
  webui/
  contracts/
  architecture/
  help/
scripts/
```

## 安裝

Python 原始碼開發需要 Python `>=3.10`。在 PowerShell 進入專案根目錄，建立環境：

```powershell
cd path\to\scopes-tool
py -m pip install --user uv
uv venv .venv
uv sync --all-extras --locked --link-mode=copy
```

如需指定相容的 Python 版本，建立環境時可使用 `uv venv .venv --python 3.12`。
已提交的 `uv.lock` 定義開發與 CI 相依套件。若僅需要瀏覽器 WebUI 相依套件，
可改用 `uv sync --extra webui --link-mode=copy`，不需再執行 all-extras 同步。

安裝會建立 `scopes-tool`、`scopes-tool-webui` 與 `scopes-tool-webui-launcher`
命令。若既有 Windows 環境已完成同步，但命令包裝檔遺失或過期，可僅重新安裝專案套件：

```powershell
uv sync --all-extras --link-mode=copy --reinstall-package scopes-tool
```

使用預先建置的 Windows x64 ZIP 時，請完整解壓縮應用程式目錄，並保留所有檔案的
相對位置。執行 `Scopes Tool.exe` 開啟 Desktop，或執行
`scopes-tool-webui-launcher.exe` 開啟瀏覽器介面。Onedir 套件已包含 Python、
Electron 與 Python 相依套件，不需另外安裝 Python 或 Node.js。
實機使用 System VISA 時仍需外部 VISA 執行環境。

## 快速開始

不連接硬體即可執行安全的 CLI 模擬檢查：

```powershell
.\.venv\Scripts\scopes-tool.exe identify --simulate --json
```

啟動本機瀏覽器 WebUI：

```powershell
.\.venv\Scripts\scopes-tool-webui-launcher.exe
```

WebUI 僅允許本機存取。直接啟動伺服器時預設位址為 `127.0.0.1:8025`。
未指定連接埠時，Launcher 會針對連接埠占用或權限不足問題，最多嘗試 100 個連接埠，
之後提供手動選擇。也可透過 `.\.venv\Scripts\scopes-tool-webui.exe` 直接啟動伺服器。

以原始碼啟動 Electron Desktop 時，請先安裝 Node.js 22.12 以上版本與 npm，
完成上述 Python 環境設定後執行：

```powershell
Set-Location .\desktop
npm ci
npm start
```

Desktop 呈現既有 WebUI，結束時會等待 Host 清理完成。
語言與外觀控制可選擇英文／繁體中文及 System／Light／Dark 主題。
裝置、Resource、工作與產物行為請參閱 [WebUI README](docs/webui/README.zh-TW.md)。

實機存取必須明確指定：單次實機命令需要 `--resource` 或 `SCOPES_TOOL_RESOURCE`；
實機 Worker 同時需要 `--live` 與 `--resource`。請勿從模擬範例推測 VISA Resource。

## 內建說明

開啟內建離線 CLI 使用指南：

```powershell
.\.venv\Scripts\scopes-tool.exe user-guide
.\.venv\Scripts\scopes-tool.exe user-guide --lang zh-TW
```

WebUI/Desktop 的 **Help** 按鈕會依所選語言開啟離線使用指南。
指南包含支援型號參考，不需網際網路連線。
建置套件前請參閱[說明文件維護](docs/help/README.md)。

## 建置

使用開發環境建置 wheel 與 sdist：

```powershell
.\.venv\Scripts\python.exe -m build
```

Windows 打包需要 `.venv` 中的 Windows x64 Python、PyInstaller 及可用的
Tkinter/Tcl/Tk；Desktop 另需 Node.js 22.12 以上版本與 npm。
可選擇建置 Python Bundle 或完整 Electron 目錄：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows_bundle.ps1
# 或建置 Desktop（已包含 Python Bundle 建置）：
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_desktop.ps1
```

Bundle 位於 `dist\scopes-tool\`；完整 Desktop 位於
`dist\desktop\win-unpacked\`：

```text
Scopes Tool.exe
scopes-tool.exe
scopes-tool-webui-launcher.exe
scopes-tool-webui-host.exe
_internal\
resources\
... Electron runtime files
```

三個 Python 執行檔共用根目錄唯一的 `_internal`。Electron Desktop 與這些執行檔
位於同一個應用程式目錄，具有自己的 Electron/Chromium 執行環境，並透過私有
Desktop Host 使用共用的 Python Backend。私有 Host 並非公開 CLI 入口。
建置會取代既有的 Bundle/Desktop 輸出目錄。可使用
`.\dist\scopes-tool\scopes-tool.exe identify --simulate --json` 進行無硬體 CLI 檢查。

建置版本化發行產物：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

```text
release/<version>/
  scopes-tool-<version>-windows-x64.zip
  scopes_tool-<version>-py3-none-any.whl
  scopes_tool-<version>.tar.gz
  checksums.txt
```

腳本讀取專案版本，要求 Electron 版本一致，建置一次 Python 發行套件及 Desktop，
再將合併後的 Desktop 包裝成僅含 `scopes-tool-<version>/` 根目錄的 ZIP。
SHA-256 校驗碼涵蓋三個發行產物。若版本目錄已存在，腳本會拒絕覆寫；
再次建置時可指定專案內新的 `-ReleaseRoot`。腳本不會發布產物。

在乾淨且所有變更均已提交至 HEAD 的工作樹中，執行無硬體驗收：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\release-acceptance.ps1
```

驗收會檢查工具、lock 一致性與應用程式版本，呼叫一次 Release Build，驗證產物名稱、
metadata、校驗碼及解壓後的 Desktop 配置，再將 wheel 與 sdist 分別安裝至乾淨環境。
接著檢查 import、CLI help、模擬及雙語離線說明，執行既有的無硬體 CLI preflight，
並確認 HEAD 與來源工作樹未改變。各步驟結果、失敗原因、退出碼、耗時與命令輸出
會寫入 `.tmp_tests/release_acceptance/` 下的獨立執行目錄。
自訂 `-OutputRoot` 必須位於專案 `.tmp_tests` 內；建置中間產物沿用既有的
`build/` 與 `dist/`。驗收不會探索或開啟真實 Resource，也不會提交、標記或發布。

條件式打包 CI 在每個 job 中僅建置一次 Desktop 或 Release 配置，並執行打包後
CLI 檢查；這不代表已驗證 GUI 互動或真實儀器。完整驗收仍是手動發行關卡。

## 測試

請從專案根目錄執行定向檢查，並將驗證產物放在 `.tmp_tests/`：

```powershell
New-Item -ItemType Directory -Force .tmp_tests | Out-Null
.\.venv\Scripts\python.exe -m pytest tests\packaging -q --basetemp .tmp_tests\packaging
.\.venv\Scripts\python.exe -m ruff check src tests
```

其他修改請選擇相關的 Core、CLI、WebUI 或 tooling 測試。
CI 職責與無硬體驗證規範請參閱[測試準則](docs/testing-guidelines.md)。
Mock、模擬及打包測試不代表實機支援驗證；實機驗證須明確授權，並由使用者提供
VISA Resource。

## 文件

- [Core README](docs/core/README.zh-TW.md)
- [支援型號](docs/core/supported-models.zh-TW.md)
- [CLI 使用指南](docs/cli/USER_GUIDE.zh-TW.md)
- [CLI README](docs/cli/README.zh-TW.md)
- [WebUI README](docs/webui/README.zh-TW.md)
- [WebUI／Desktop 使用指南](docs/webui/USER_GUIDE.zh-TW.md)
- [Core 整合](docs/core/integration.md)
- [CLI 整合](docs/cli/cli-integration.md)
- [公開合約](docs/contracts/)
- [Scopes CLI JSONL 合約](docs/contracts/scopes-cli-jsonl-contract.md)
- [Scopes Worker 合約](docs/contracts/scopes-worker-contract.md)
- [工作流程協調](docs/contracts/scopes-orchestrator-workflows.md)
- [專案結構](docs/architecture/monorepo-layout.md)
- [WebUI 修改規範](docs/webui/web-ui-change-rules.md)
- [說明文件維護](docs/help/README.md)

## 參與貢獻

變更行為前請先閱讀 [Agent Instructions](AGENTS.md) 與
[測試準則](docs/testing-guidelines.md)。保持 Core 不依賴 CLI/WebUI、保留公開合約，
並預設使用模擬器或假儀器驗證。儀器操作與實機支援變更須經適用的安全審查，
且驗證須獲得明確授權。請勿將暫時性的驗證產物加入追蹤中的公開文件。

## 授權與免責聲明

本專案採用 MIT License，詳見 [LICENSE](LICENSE)。

Scopes Tool 應用程式圖示使用 ChatGPT 中的 OpenAI 圖像生成功能產生，
並經專案維護者審閱及選定。

本專案為獨立、非官方專案，與儀器製造商並無關聯，亦未獲其背書、贊助或官方認可。

所有廠商名稱、型號、產品名稱及商標的權利均歸各原權利人所有。

使用者應遵守適用的廠商軟體、驅動程式、儀器與文件授權條款。
