<a id="supported-models"></a>

# 支援型號

[English](supported-models.md)

本指南說明 Scopes Tool 使用者可操作的型號、連線、功能及限制。
Capability Profile 僅描述可用功能，不代表儀器已安裝對應選配或授權；
實際不可用時仍以儀器回報的錯誤為準。

<a id="contents"></a>

## 目錄

- [標準實體型號身分](#canonical-physical-model-identity)
- [VISA Backend 邊界](#visa-backend-boundary)
- [能力摘要](#capability-summary)
- [Tektronix 型號支援](#tektronix-model-support)
  - [擷取、時基與通道](#acquisition-timebase-and-channels)
  - [顯示、游標、Math 與量測](#display-cursors-math-and-measurements)
  - [觸發操作](#trigger-operations)
  - [波形、截圖、Reference Memory 與儲存](#waveforms-screenshots-reference-memory-and-storage)
  - [系統、診斷、工作流程與主機功能](#system-diagnostics-workflows-and-host-functions)
  - [其他不支援的功能](#other-unsupported-feature-families)
- [Keysight InfiniiVision 型號支援](#keysight-infiniivision-model-support)
  - [儀器端 Math 矩陣](#instrument-side-math-matrix)

<a id="canonical-physical-model-identity"></a>

## 標準實體型號身分

Scopes Tool 支援以下已註冊的示波器型號。Simulate／Dry-run 可使用表列 Model ID；
Live 操作以連接儀器的識別結果為準。

| 標準實體 Model ID | 製造商 | Model | Series |
| --- | --- | --- | --- |
| `keysight-dsox2004a` | Keysight Technologies | DSOX2004A | 2000X |
| `keysight-dsox3024a` | Keysight Technologies | DSOX3024A | 3000X |
| `keysight-dsox4024a` | Keysight Technologies | DSOX4024A | 4000X |
| `keysight-dsox4034a` | Keysight Technologies | DSOX4034A | 4000X |
| `tektronix-tbs2074` | Tektronix | TBS2074 | TBS2000 |
| `tektronix-tds2024b` | Tektronix | TDS2024B | TDS2000B |
| `tektronix-tbs1052b` | Tektronix | TBS1052B | TBS1000B |

預期型號不可覆蓋實際連接儀器的識別結果；未知或不相符的型號會被拒絕。

<a id="visa-backend-boundary"></a>

## VISA Backend 邊界

Product Live 支援精確取決於偵測到的實體型號、VISA Transport 與 Backend。
連接儀器的 `*IDN?` 身分具權威性；規劃 Profile 或 Backend 選擇器不會授予型號或功能支援。
下列連線已開放支援的 Core Product 操作：

| 標準實體 Model ID | System VISA USB | System VISA TCPIP | `@py` TCPIP |
| --- | --- | --- | --- |
| `keysight-dsox2004a` | 開放 | 未開放 | 未開放 |
| `keysight-dsox3024a` | 開放 | 未開放 | 未開放 |
| `keysight-dsox4024a` | 開放 | 開放 | 開放 |
| `keysight-dsox4034a` | 開放 | 開放 | 開放 |
| `tektronix-tbs2074` | 開放 | 開放 | 開放 |
| `tektronix-tds2024b` | 開放 | 未開放 | 未開放 |
| `tektronix-tbs1052b` | 開放 | 未開放 | 未開放 |

所有型號的 `@py` USB 均未開放 Product Live。只有上表核准的型號／Transport／Backend
組合已開放；GPIB、ASRL、Bluetooth（`@bt`）及明確自訂 VISA Backend 均未開放。
預設或 `system_visa` 選擇器明確載入並驗證已安裝的 IVI VISA Runtime，不會退回 `@py`。
明確指定 `@ivi` 歸類為自訂 Backend，請改用預設 System VISA 選擇器。

能力、參數限制、已安裝選配與儀器原生狀態仍決定已開放連線內可用的操作。
連線開放不會自動啟用依賴選配或其他不支援的命令。模擬與 Dry-run 不開啟實際 VISA Session。

<a id="capability-summary"></a>

## 能力摘要

Tektronix Profile 僅允許下方型號支援章節記載的既有操作子集。三者皆支援 BYTE 波形擷取、
型號專屬單來源量測、通道電壓 Offset、原生狀態工作流程、依能力限制的擷取檢查與清理，
以及型號專屬 Sequence 子集。TBS2074 支援原生黑底 PNG 截圖、Smoke 流程及儀器端
Setup／Reference／檔案儲存；TDS2024B 支援明確 BMP 截圖，TBS1052B 支援透過
USBTMC 的明確 JPEG 截圖。TDS2024B 與 TBS1052B 不提供 Setup、Reference Memory
或儀器端儲存公開操作。三者均不支援正規化的 `check-error`。
Tek 工作流程狀態與 Keysight 正規化 System Error Queue 分開。

模擬不能證明實機支援；這些型號也不提供訊號 Preset 或 System Error Queue 注入。

<a id="tektronix-model-support"></a>

## Tektronix 型號支援

已註冊的 Tektronix 型號使用既有 Scopes Tool 公開契約；本節記載個別型號的硬體邊界。
Driver 方法、模擬器回應、Capability Flag 或 WebUI 顯示設定均不能證明實機支援。

支援用語具有規範性：

- **SUPPORTED**：操作與明確列出的既有選項子集滿足公開契約，包括必要回讀與完成條件。
  未列選項仍不支援，子集不會建立 Tektronix 專屬公開 Enum。
- **PARTIAL AGGREGATE**：只適用於契約已允許不可用欄位的既有唯讀投影。
  不支援的原子查詢會跳過，不會先嘗試再捕捉錯誤。Nullable 欄位不授權部分 Setter、
  產物、量測或工作流程；Raw／來源欄位仍描述實際執行的操作。
- **UNSUPPORTED**：無法提供必要語義或結果。必要回讀絕不以回傳 Setter 參數、
  虛構值或空字串冒充硬體狀態。

公開驗證與手冊硬體限制均適用。支援的動作仍可能回報儀器錯誤、無可用波形、缺少儲存或逾時。
TBS2074 的權威手冊為 Tektronix
[TBS2000 Series Programmer Manual, 077-1149-02 Rev A](https://download.tek.com/manual/TBS2000-Series-Programmer-Manual-077-1149-02-Rev-A.pdf)；
TDS2024B 與 TBS1052B 則為
[TBS1000/B/EDU, TDS2000/B/C and related Series Programmer Manual, 077-0444-03 Rev B](https://download.tek.com/manual/TBS1000-B-EDU-TDS2000-B-C-TDS1000-B-C-EDU-TDS200-TPS2000-B-Programmer-077044403_RevB.pdf)。
僅針對舊 TDS200 型號或 TDS2MM 模組記載的條件不適用於這些註冊型號。

Raw 欄位保留契約所需操作的實際儀器回應，回讀必須描述正在查詢的設定，而非相關設定。
未識別或超出子集的儀器狀態不會正規化為支援值。
允許的選項子集只適用於已接受並執行該選項的既有公開介面。
產物編碼、檔名與 Adapter 行為仍屬既有公開契約。

除非標示彙總、工作流程或主機功能，下表涵蓋原子動作及其既有 Query／Set 形式。
僅呈現用途的編輯器繼承其組成操作：`acquisition-control`、`channel-scale-range`、
`external-trigger-range-level`、`front-panel-measurements`、`reference-waveform`、
`reference-labels`、`system-information`、`diagnostics`、`serial-decode`、
`serial-trigger`、`serial-lister`。編輯器可顯示不可用欄位，但不啟用不支援動作；
Adapter Alias 不會新增硬體功能。

<a id="acquisition-timebase-and-channels"></a>

### 擷取、時基與通道

| 既有操作 | TBS2074 | TDS2024B | TBS1052B | 邊界 |
| --- | --- | --- | --- | --- |
| `identify` | SUPPORTED | SUPPORTED | SUPPORTED | `*IDN?`；以偵測身分與已註冊型號的拒絕規則為準。 |
| `run`, `stop-acquisition` | SUPPORTED | SUPPORTED | SUPPORTED | 連續執行使用 `STOPAfter RUNSTOP` 加 `STATE RUN`；停止使用 `STATE STOP`。 |
| `single` | SUPPORTED | SUPPORTED | SUPPORTED | `STOPAfter SEQuence` 後接 `STATE RUN`；啟動一次擷取，但不保證觸發完成。 |
| `single-wait` | SUPPORTED | SUPPORTED | SUPPORTED | 單次擷取加有限 `BUSY?` 輪詢；可選的逾時強制觸發後再進行有界限輪詢。取消與逾時仍有界限。 |
| `force-trigger` | SUPPORTED | SUPPORTED | SUPPORTED | `TRIGger FORCe`；要求儀器已 Arm，本身不是完成等待。 |
| `acquisition` | SUPPORTED | SUPPORTED | SUPPORTED | 三者皆支援 normal/sample、peak、average；TBS2074 不支援 high-resolution。平均次數：TBS2074 為 2–512 的 2 次方；TDS2024B/TBS1052B 為 4/16/64/128。 |
| `autoscale` | SUPPORTED | SUPPORTED | SUPPORTED | 僅無參數 `AUTOSet`；不支援通道清單、擷取模式或通道選擇政策選項。TDS2024B/TBS1052B 對 AutoSet 及其後 SESR 查詢暫用 10000 ms，各操作後還原原逾時；TBS2074 保留 Session 逾時。 |
| `sample-rate` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074 可回讀目前／最大取樣率；B1 波形 X Increment 的倒數不是硬體取樣率回讀。 |
| `acquisition-points`, `record-length` | SUPPORTED | SUPPORTED | SUPPORTED | 唯讀擷取大小；TDS2024B/TBS1052B 固定 2500 點，不新增 Record Length Setter。 |
| `timebase-scale` | SUPPORTED | SUPPORTED | SUPPORTED | 秒／格讀寫。 |
| `timebase-position` | SUPPORTED | SUPPORTED | SUPPORTED | TDS2024B/TBS1052B 使用原生秒值。TBS2074 先讀 Horizontal Delay Mode，只有 ON 才使用原生 `HORizontal:MAIn:DELay:TIMe` 秒值；OFF 時 Query/Set 失敗，不改模式，也不將百分比換算秒。TBS2000 第 157–160 頁。 |
| `timebase-reference` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 無獨立 Left/Center/Right 設定／回讀；水平百分比改變的是位置。 |
| `channel-display`, `channel-scale`, `channel-coupling` | SUPPORTED | SUPPORTED | SUPPORTED | 類比通道；公開 Coupling 子集仍為 AC/DC。Tek 顯示變更可能重新啟動擷取。 |
| `channel-offset` | SUPPORTED | SUPPORTED | SUPPORTED | TBS2074 使用原生伏特。TDS2024B/TBS1052B 以 `-POSITION * SCALE` 換算公開中心電壓，設定電壓寫入 `POSITION = -volts / SCALE`；後續 Scale 變更不必保留電壓。B1 第 2-55 頁。 |
| `channel-probe` | SUPPORTED | SUPPORTED | SUPPORTED | TBS2074 從 Probe Gain 推導衰減，限制依探棒而定；B1 比例為 1、10、20、50、100、500、1000。 |
| `channel-bandwidth-limit`, `channel-invert` | SUPPORTED | SUPPORTED | SUPPORTED | Bandwidth 是手冊定義的 20 MHz 限制器，不是數值頻寬設定；三者皆有原生 Invert。 |
| `channel-label`, `channel-probe-skew` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074 標籤上限 30 字元，Probe Skew 使用公開 -100 至 +100 ns 子集；B1 無可寫標籤／Deskew。 |
| `channel-units` | SUPPORTED | SUPPORTED | SUPPORTED | 公開 volts/amps 對應 V/A。TBS2074 支援 CH1–CH4；B1 適用於各型號所有類比通道。 |
| `channel-range` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 伏特／格與軌跡位置不足以提供公開 Full-scale Acquisition Range 語義。 |
| `channel-impedance`, `channel-vernier` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 固定阻抗不是可選設定／回讀，也無 Fine-scale Enable 契約。 |
| `channel-summary` | PARTIAL AGGREGATE | PARTIAL AGGREGATE | PARTIAL AGGREGATE | 投影定義如下；不可用欄位不授權不支援的原子查詢。 |

<a id="display-cursors-math-and-measurements"></a>

### 顯示、游標、Math 與量測

| 既有操作 | TBS2074 | TDS2024B | TBS1052B | 邊界 |
| --- | --- | --- | --- | --- |
| `display-persistence` | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 支援 off、infinite 及確切 1/2/5 s；不新增 AUTO。 |
| `display-vectors` | UNSUPPORTED | SUPPORTED | SUPPORTED | B1 可啟用／查詢 Vectors；既有 Setter 不新增 dots/OFF。 |
| `display-label`, `display-clear`, `display-intensity` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 無對應的全域標籤顯示、波形顯示清除或波形亮度契約。 |
| `cursor-off`（`cursor` off 動作） | SUPPORTED | SUPPORTED | SUPPORTED | 使用 Cursor Function OFF，不停用教師控制的游標功能。 |
| `cursor-query`（`cursor` query 動作） | PARTIAL AGGREGATE | PARTIAL AGGREGATE | PARTIAL AGGREGATE | 只投影已確認啟用模式且有實體秒／伏特單位的軸，詳見下文。 |
| `cursor-set` | SUPPORTED | SUPPORTED | SUPPORTED | TBS2074 提供第一代五種游標功能，Selected Waveform 選擇或顯示改變可能重設擷取。B1 使用獨立來源選擇，X-only VBARS 或 Y-only HBARS；支援 X auto-timebase，三者皆不支援 auto-vertical。詳見下文。 |
| `math-display`, `math-operator`, `query_math_operation` | SUPPORTED | SUPPORTED | SUPPORTED | 僅 Function 1；確切表達式如下，不含除法或額外 Function。 |
| `math-vertical` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek Scale 加 Position 無法滿足 Scale/Full-range/Voltage-offset 契約。 |
| `fft` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 未建立必要 Frequency Center/Full-span 語義，不可假設顯示格數合成 Hz。 |
| `math-transform`, `math-filter`, `math-visualization`, `math-composite-source`, `math-clear` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 無等價公開 Transform/Filter/Cascade/Visualization 或 Accumulator-clear 語義；TBS1052B Trend Plot 不是 Math Trend。 |
| `measure`, `measure-sweep` | SUPPORTED | SUPPORTED | SUPPORTED | 單來源 Immediate 項目使用下方型號子集。即使查詢失敗也還原 Immediate TYPE/SOURCE；不支援 Pair／參數化項目。 |
| `measure-install` | SUPPORTED | SUPPORTED | SUPPORTED | Periodic Measurement 槽位：TBS2074 為 6、TDS2024B 為 5、TBS1052B 為 6。重用相符或未使用槽位；滿載不可默默取代其他量測。 |
| `measure-clear` | SUPPORTED | SUPPORTED | SUPPORTED | 以原生逐槽位機制清除已安裝週期量測，不是清除 Snapshot／擷取資料。 |
| `measure-results` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 既有契約要求單一原生 Results 回應及原始來源；不可將多次 TYPE/SOURCE/UNITS/VALUE 查詢串接成合成結果。 |
| `measure-source`, `measure-menu`, `measure-show`, `measure-window`, `measurement-statistics`, `measure-stats` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Immediate／逐槽位來源不是全域預設；Tek Gating 不是 MAIN/ZOOM/AUTO/GATE；彙總範例不構成公開 Statistics 或 Marker 顯示控制。 |
| `annotation`, `annotation-on`, `annotation-off`, `annotation-set`, `annotation-clear`, `annotation-query` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 通道標籤無法提供 Annotation Slot 的文字／顏色／背景／位置／啟用語義。 |

`math-operator` 在 TBS2074 與 TDS2024B 允許 CH1+CH2、CH1-CH2、CH2-CH1、CH1*CH2、
CH3+CH4、CH3-CH4、CH4-CH3、CH3*CH4；TBS1052B 僅 CH1/CH2。
回讀解析到既有 Operation/Source 欄位，保留來源順序。
不支援任意交叉配對、自我配對、Cascade Source、除法或未列出的反向順序。

允許的單來源量測項目如下：

| 既有項目群組 | TBS2074 | TDS2024B | TBS1052B | 原生對應／限制 |
| --- | --- | --- | --- | --- |
| vpp, frequency, period, minimum, maximum, rise_time, fall_time, positive_width, negative_width | SUPPORTED | SUPPORTED | SUPPORTED | PK2Pk, FREQuency, PERIod, MINImum, MAXimum, RISe, FALL, PWIdth, NWIdth。 |
| vavg | SUPPORTED | SUPPORTED | SUPPORTED | MEAN：整個波形算術平均，不是 CMEAN。 |
| vrms | SUPPORTED | UNSUPPORTED | SUPPORTED | RMS；TDS2024B Cycle RMS/CURSORRMS 不符合顯示波形 RMS 語義。 |
| amplitude, top, base, overshoot, preshoot | SUPPORTED | UNSUPPORTED | SUPPORTED | AMPlitude, HIGH, LOW, POVERshoot, NOVERshoot。 |
| duty_cycle, negative_duty_cycle | SUPPORTED | UNSUPPORTED | SUPPORTED | PDUty/NDUty；即使語法較廣，適用性文字仍排除 TDS2000B。 |
| area, positive_edges, negative_edges, positive_pulses, negative_pulses | SUPPORTED | UNSUPPORTED | SUPPORTED | AREA、邊緣計數與脈衝計數週期類型；不新增 Gate 控制。 |
| ac_rms, x_at_max, x_at_min | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 無對應 AC-only RMS 或極值時間週期類型。 |

既有單通道安裝操作仍不支援參數化 y_at_x/time_at_edge/time_at_value 與 phase/delay
配對項目。安裝週期量測不會啟用原生結果傾印或全域量測來源。

<a id="trigger-operations"></a>

### 觸發操作

| 既有操作 | TBS2074 | TDS2024B | TBS1052B | 邊界 |
| --- | --- | --- | --- | --- |
| `trigger-mode` | SUPPORTED | SUPPORTED | SUPPORTED | 指觸發類型，不是 Sweep。TBS2074 允許 edge/glitch/runt，B1 允許 edge/glitch/tv；類型選擇不等於完整設定操作。 |
| `trigger-sweep` | SUPPORTED | SUPPORTED | SUPPORTED | 僅 auto/normal。 |
| `trigger-edge-source` | SUPPORTED | SUPPORTED | SUPPORTED | 三者皆允許類比通道與 line；B1 另允許 external。不得假設 TBS2074 AUX 等於公開 external。 |
| `trigger-edge-slope` | SUPPORTED | SUPPORTED | SUPPORTED | 僅 positive/negative，無 either/alternate。 |
| `trigger-edge-coupling` | SUPPORTED | SUPPORTED | SUPPORTED | TBS2074：dc/lf-reject；B1：ac/dc/lf-reject。HF/Noise Rejection 不新增公開 Coupling 值。 |
| `trigger-edge` | SUPPORTED | SUPPORTED | SUPPORTED | 組合設定先選 EDGE，再設類比 Source/Level/Slope，僅 positive/negative。B1 組合設定可能在 MAIN:LEVEL 前選來源；此組合契約排除 line/external。 |
| `trigger-edge-level` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074 可依通道存取 Level；B1 MAIN:LEVEL 是所選來源狀態，不改來源就無法滿足獨立指定通道操作。 |
| `trigger-holdoff` | SUPPORTED | SUPPORTED | SUPPORTED | TBS2074：20 ns–8 s；B1：500 ns–10 s。 |
| `trigger-pulse-width` | SUPPORTED | SUPPORTED | SUPPORTED | 僅類比 positive/negative、less-than/greater-than；只提供有效 Threshold，非有效／範圍 Threshold 為 null，min+max/range 要求在寫入前拒絕。 |
| `trigger-runt` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074 CH1–CH4、positive/negative、occurs/less-than/greater-than；無 either 極性。 |
| `trigger-tv` | UNSUPPORTED | SUPPORTED | SUPPORTED | B1：NTSC/PAL、類比來源、positive/negative、field1/field2/all-fields/all-lines；不支援 Line-field 變體、SECAM 或其他標準。 |
| `trigger-noise-reject`, `trigger-hf-reject`, `trigger-edge-reject` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 單一互斥 Tek Coupling 選擇器無法提供獨立 Reject 控制／回讀。 |
| `external-trigger-range`, `external-trigger-probe`, `external-trigger-units`, `trigger-edge-external-level`, `external-trigger-settings` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Source 選擇或所選來源 Level 不構成獨立 External Range/Probe/Units/Level 語義，也無有用的彙總投影。 |
| `trigger-transition`, `trigger-delay`, `trigger-setup-hold`, `trigger-edge-burst`, `trigger-pattern`, `trigger-or` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 無符合的公開 Threshold/Timing/Count/Pattern/Readback 契約；水平延遲不是事件延遲觸發。 |

TBS2074 Runt 允許的拼字以記載的 `TRIGger:A:RUNT:*` 命令項目為準。
有衝突的範例不會引入 `PULSE:RUNT`、新值或更大的數值範圍。

<a id="waveforms-screenshots-reference-memory-and-storage"></a>

### 波形、截圖、Reference Memory 與儲存

| 既有操作 | TBS2074 | TDS2024B | TBS1052B | 邊界 |
| --- | --- | --- | --- | --- |
| `capture` | SUPPORTED | SUPPORTED | SUPPORTED | 僅 BYTE、已顯示類比通道、安全上限 1000 要求點數；隱藏通道失敗且不改顯示。多通道為依序傳輸；`all` 包含隱藏通道，會失敗而非過濾。無 WORD、擷取重設或重取樣。 |
| `screenshot` 明確 BMP 電腦端產物 | UNSUPPORTED | SUPPORTED | UNSUPPORTED | TDS2024B 透過 USBTMC 使用原生 `HARDCopy START`，保留 BMP 位元組與 `.bmp` 產物語義；TBS2074 使用另一原生 PNG 路徑。TBS1052B BMP 適用性有歧義，不支援。 |
| `screenshot` 明確 JPEG 電腦端產物 | UNSUPPORTED | UNSUPPORTED | SUPPORTED | TBS1052B 透過 USBTMC 使用 `HARDCopy:FORMat JPEG`、`HARDCopy:PORT USB`、`HARDCopy START`；保留原生 JPEG 與 `.jpeg` 語義，要求起迄標記。B1 第 2-96 至 2-102 頁。 |
| `capture_screenshot`；CLI 預設／明確 PNG | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074 暫存原生 PNG、等待 OPC、讀檔、驗證 PNG 並嘗試清理；要求可寫儀器儲存，只支援黑底。 |
| `screenshot --query-hardcopy`; `query_hardcopy_state` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 無法提供完整 Hardcopy Area/Ink-saver/Palette/Layout/Format 必要回讀。 |
| `reference-save`, `reference-display`, `reference-query` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | 僅兩槽；Save 有 OPC 完成，Query 回傳實際顯示，label/raw_label 因無對應 Tek 回讀而為 null。 |
| `reference-label`, `reference-clear` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 無可寫 Reference Label 或明確 Memory-clear；隱藏不是清除。 |
| `save-pwd` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | 原生檔案系統目前目錄 Set/Query，受公開與型號檔案系統驗證限制。 |
| `save-image` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | 儀器端檔案動作，無電腦產物；以暫時 15 秒逾時等待 OPC 成功，在 `finally` 還原逾時。儀器目前編碼不新增公開 Format Enum。 |
| `save-image-format` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074 PNG/BMP Setter 與回讀；B1 `SAVE:IMAGE:FILEFORMAT` 無已確認對應查詢，`HARDCopy:FORMat?` 是不同設定，不能替代。 |
| `save-image-ink-saver` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 無公開儀器儲存 Ink-saver 設定；舊 Hardcopy 截圖仍管理其暫時 Ink-saver 狀態。 |
| `save-image-palette`, `save-image-factors`, `save-filename` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | 無獨立對應狀態／回讀。 |
| `save-waveform-format` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | TBS2074 公開子集為 CSV/SPREADSheet 並有回讀；B1 CSV 匯出無獨立 Format Setter/Readback。 |
| `save-waveform` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek 要求既有可選 `source_channel`，限型號類比通道；等待 OPC 完成並還原暫時 15 秒逾時。 |
| `save-waveform-length`, `save-waveform-length-max` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Record Length 與 Transfer Start/Stop 不是匯出點數／最大長度設定。 |
| `setup-save`, `setup-recall` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | 僅槽位 1–9；不支援檔案目標，Tek Setup 格式不滿足既有 `.scp` 契約。 |

TDS2024B BMP 與 TBS1052B JPEG 擷取讀到 VISA End-of-message，驗證原生格式並保留
`.bmp`／`.jpeg` 產物語義。JPEG 要求起迄標記，使用後方 USB Device 連接埠，無須 USB 隨身碟。
暫時 10 秒逾時、Hardcopy Format、Port 及要求的 Ink-saver／背景設定即使失敗也還原。
明確 Landscape/Portrait 與 Ink-saver 控制僅對應手冊 B1 控制，不虛構 Palette。

TBS2074 PNG 擷取使用符合 TBS2000 8.3 規則的儀器暫存檔名，讀到 VISA End-of-message，
在 `finally` 還原圖片格式與暫時 10 秒逾時，並嘗試刪除暫存檔。不改工作目錄或擷取狀態。
16-bit 傳輸中填補的 8-bit 資料，以及較大的原生 Record Length，均不授權 WORD 擷取或
要求 5000/10000 點擷取。

<a id="system-diagnostics-workflows-and-host-functions"></a>

### 系統、診斷、工作流程與主機功能

| 既有操作 | TBS2074 | TDS2024B | TBS1052B | 邊界 |
| --- | --- | --- | --- | --- |
| `live-data-snapshot` | PARTIAL AGGREGATE | PARTIAL AGGREGATE | PARTIAL AGGREGATE | 部分欄位不可用，且不會修改不支援的設定。 |
| `system-information-snapshot` | SUPPORTED | PARTIAL AGGREGATE | PARTIAL AGGREGATE | TBS2074 含 Sample Rate；其餘兩款可能不提供此欄位。 |
| `system-status-byte`, `system-clear-status`, `system-opc`, `system-standard-event` | SUPPORTED | SUPPORTED | SUPPORTED | 原生 `*STB?`、`*CLS`、`*OPC?`、`*ESR?`；消耗式讀取保留原生語義。 |
| `system-operation-status`, `system-options` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek 擷取／狀態不符合既有 Operation Condition 位元契約；型號假設不是已安裝選配回讀。 |
| `check-error`, `query_system_error`, `drain_system_errors` | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | Tek Event Queue/SESR 不等於正規化 System Error Queue/Drain/Clean-state 契約。 |
| `doctor` | SUPPORTED | SUPPORTED | SUPPORTED | 原生狀態前置檢查若有既存錯誤，在唯讀 Snapshot 前失敗；不可用的非 Edge／非類比觸發細節為 Nullable，不改 Source/Type。 |
| `smoke` | SUPPORTED | UNSUPPORTED | UNSUPPORTED | 要求原生前置檢查、BYTE 擷取及黑底原生 PNG；停用儲存不移除這些儀器操作。 |
| `acquisition-check` | SUPPORTED | SUPPORTED | SUPPORTED | 僅測試 Profile 支援模式／次數，跳過不支援模式。Check-only 為唯讀；要求還原時以原生狀態及實際回讀驗證。 |
| `cleanup` | SUPPORTED | SUPPORTED | SUPPORTED | 依能力執行 CLS/OPC/原生狀態序列；跳過不可用輔助／顯示步驟，`final_error_queue_clean` 為 null。 |
| `capture-batch`, `capture-until`, `capture-monitor` | SUPPORTED | SUPPORTED | SUPPORTED | BYTE/1000 點類比子集、原生狀態檢查點與有界限主機流程。 |
| `measure-log`, `measure-until` | SUPPORTED | SUPPORTED | SUPPORTED | 型號專屬單來源 Immediate 子集，還原 TYPE/SOURCE 並檢查原生狀態。 |
| `triggered-measure-loop`, `triggered-capture-series` | SUPPORTED | SUPPORTED | SUPPORTED | 每迭代恰好一次 Single，等待目前完成，不重新 Arm。 |
| `sequence` | SUPPORTED | SUPPORTED | SUPPORTED | 三者皆有 wait、single、wait-trigger、measure、capture、cleanup；screenshot 僅 TBS2074 PNG/黑底。所有步驟／選項在寫入前驗證。 |
| `list-resources`, `capabilities`, `manifest`, `hardware-report` | SUPPORTED | SUPPORTED | SUPPORTED | 主機 VISA 列舉／Profile／報告操作；離線報告與模擬不是硬體證明。 |
| `worker`, `status`, `wait-ready`, `send-command`, `stop` | SUPPORTED | SUPPORTED | SUPPORTED | 使用既有生命週期／受理規則；`send-command` 不是任意 SCPI，Worker Stop 與 Acquisition Stop 不同。 |

主機 Planner、Schema、身分／能力解析、產物寫入、進度／取消、Session 開關及可中斷等待
屬於基礎設施，不是額外硬體功能。Core Plan/Run 配對繼承工作流程表的規則。
Dry-run 與模擬器輸出不代表 Live 支援。

<a id="other-unsupported-feature-families"></a>

### 其他不支援的功能

下列既有功能在 TBS2074、TDS2024B、TBS1052B 均為 UNSUPPORTED。
沒有該功能設定／結果時，Query 形式 API 也不是部分彙總。

| 既有操作／Adapter Alias | 共用邊界 |
| --- | --- |
| `dvm-enable`, `dvm-source`, `dvm-mode`, `dvm-auto-range`, `dvm-current`, `dvm-query` | 無整合 DVM 狀態／讀值契約；週期 RMS 不是 DVM。 |
| `wgen-output`, `wgen-function`, `wgen-frequency`, `wgen-voltage`, `wgen-offset`, `wgen-load`, `wgen-query` | 無產生器 Output/Function/Frequency/Amplitude/Offset/Load 命令組。 |
| `demo-output`, `demo-function`, `demo-phase`, `demo-query` | 無可程式化 Demo Output/Function/Phase；探棒補償不是此功能。 |
| `serial-mode`, `serial-display` (`serial-enable`, `serial-disable`), `serial-query` (`serial-status`) | 無 Bus Slot Decode Mode/Display/State；RS-232 介面不是波形序列解碼。 |
| `serial-uart` (`serial-uart-set`, `serial-uart-show`), `serial-i2c` (`serial-i2c-set`, `serial-i2c-show`), `serial-spi` (`serial-spi-set`, `serial-spi-show`), `serial-can` (`serial-can-set`, `serial-can-show`) | 無協定 Signal/Threshold/Framing/Address/Rate 解碼設定／回讀。 |
| `serial-trigger-uart` (`serial-trigger-uart-set`, `serial-trigger-uart-show`), `serial-trigger-i2c` (`serial-trigger-i2c-set`, `serial-trigger-i2c-show`), `serial-trigger-spi` (`serial-trigger-spi-set`, `serial-trigger-spi-show`), `serial-trigger-can` (`serial-trigger-can-set`, `serial-trigger-can-show`) | 無協定／資料／位址／錯誤觸發選擇器／回讀，Edge/Pulse 不可替代。 |
| `serial-lister-display`, `serial-lister-reference`, `serial-lister-query` (`serial-lister-status`), `serial-lister-export` (`serial-data`) | 無解碼事件 Lister 顯示／Reference／Data／Count／Export 來源。 |
| `search-state`, `search-mode`, `search-count`, `search-event` | 無 Search Enable/Type/Count/Navigation 契約；Zoom/Cursor 不是事件導覽。 |
| `serial-search-uart`, `serial-search-i2c`, `serial-search-spi`, `serial-search-can` | 無協定限定 Search 設定／結果。 |
| `segmented-memory`, `segmented-capture` | 無 Segmented Count/Selection/Time-tag/All-segment Waveform 契約；重複擷取／Reference Slot 不可替代。 |

<a id="keysight-infiniivision-model-support"></a>

## Keysight InfiniiVision 型號支援

<a id="acquisition"></a>

### 擷取

2000X、3000X、4000X Profile 支援 `normal`、`peak`、`average`、`high_resolution`。
平均次數為包含 2 與 65536 的所有整數，依各系列 Programmer's Guide 的
`:ACQuire:COUNt` 與 `:ACQuire:TYPE`：
[2000 X-Series](https://www.keysight.com/ca/en/assets/9018-06893/programming-guides/9018-06893.pdf)、
[3000 X-Series](https://www.keysight.com/us/en/assets/9018-06894/programming-guides/9018-06894.pdf)、
[4000 X-Series](https://www.keysight.com/us/en/assets/9023-40025/miscellaneous/4k_X-Series_prog_guide.pdf)。
不含已棄用的 1。這些是可程式化次數，不只前面板的 2 次方選項。
既有 `average_counts` Tuple 與 JSON Array 列出完整範圍。
Profile 描述型號支援；Segmented Acquisition 等組合仍由目前擷取設定與儀器錯誤決定。

<a id="instrument-side-math-matrix"></a>

### 儀器端 Math 矩陣

Math 僅在儀器端執行，標準 Operation 與 Source 名稱獨立於原始 SCPI 回讀。

| 介面 | 2000X | 3000X | 4000X |
| --- | --- | --- | --- |
| Math Function 槽位與語法 | 1；無編號 `:FUNCtion` | 1；無編號 `:FUNCtion` | 4；索引 `:FUNCtion<n>` |
| Operator | `add`, `subtract`, `multiply`, `divide` | 相同 | 相同 |
| Transform | `differentiate`, `integrate`, `sqrt`, `absolute`, `square`, `ln`, `log10`, `exp`, `exp10`, `linear` | 相同 | 相同 |
| Filter | `low-pass`, `high-pass` | 相同 | `low-pass`, `high-pass`, `average`, `smooth`, `envelope` |
| Visualization | `magnify`, `trend` | 相同 | `magnify`, `trend`, `maximum`, `minimum`, `peak`, `max-hold`, `min-hold` |
| FFT | 基本幅值 FFT | 基本幅值 FFT | 幅值 FFT、FFT Phase 與進階控制 |
| Composite / GOFT Source | 全域類比通道 Composite | 相同 | 不支援 |
| Math Cascade Source | 不支援 | 不支援 | 僅較小編號 Math Function |
| Accumulation Clear | 不支援 | 不支援 | `average`, `max-hold`, `min-hold` |

Display、Vertical 設定、Query 與適用 Clear 行為使用相同 Function-slot 語法。
2000X/3000X 拒絕 Math-function Cascade Source；4000X 拒絕 Composite/GOFT，
並在 Backend 存取前拒絕自我參考或向前參考。既有 `fft` CLI 與 Worker 命令維持跨 Profile 相容。

因無必要 MSO／數位通道基礎，不支援 Bus Timing 與 Bus State；它們不在已啟用能力操作、
CLI 選項、Worker 命令、Core Builder 或模擬器行為內。

- BYTE 與 WORD 波形擷取，保守安全上限 10,000 點。
- 唯讀量測 Helper 與截圖擷取。
- 量測控制可清除量測、啟用／查詢 Measurement Marker、選擇類比來源及 MAIN/ZOOM/AUTO/GATE
  視窗。ZOOM 要求已顯示 Zoomed Timebase，未知時 AUTO 較安全。僅寫 source1 時，回讀可保留 source2。
- 進階量測統計限 3000X/4000X。Core 查詢儀器累積的 Current/Minimum/Maximum/Mean/
  Standard-deviation/Count，並控制 Statistics Mode、LCD Display、Maximum Count、
  Relative Standard Deviation、Reset、Manual Increment；2000X 不宣告此能力。
- Reference Waveform Helper 管理槽位 1、2；啟用一槽時儀器可能關閉另一槽顯示。
- DVM 支援 Enable、類比來源、`dc`/`dc-rms`/`ac-rms` 電壓模式、Auto Range、目前電壓與彙總查詢。
  DVM 可能需要選配／授權；不支援 DVM Frequency、獨立 `:COUNter` 或 `:MEASure:COUNter`。
- DEMO 輸出彙總及個別 Output/Function/Phase Helper。DEMO 依選配／硬體；Profile 在開 Session
  前限制手冊 Function 名稱，缺少選配／硬體仍以實機錯誤為準。
- WGEN Output/Function/Frequency/Amplitude/Offset/Load 與彙總查詢。
  2000X/3000X 用 `:WGEN`，4000X 僅 Generator 1 的 `:WGEN1`。
  可設 Function：`sine`、`square`、`ramp`、`pulse`、`noise`、`dc`。
- Serial Bus 彙總 Query、Mode、Display 與 UART/I2C/SPI/CAN 基本協定設定。
  Profile 限制 Bus 數與可設模式。Decode 可能需授權，Core 不偵測授權，保留選配／硬體不可用錯誤。
- Serial Trigger 在相同 Profile 提供手冊共用 I2C/SPI/CAN 子集，不新增 Capability 欄位；
  Profile 仍限制 Bus 數與協定可用性。
- Waveform Search State/Count Query 與 Profile 限制的 Mode 設定；不支援模式在送 Search SCPI 前拒絕。
- 儀器端 SAVE 提供目前目錄／Base Name、Image 設定／啟動、Waveform 設定／啟動。
  三種 Profile 皆有唯讀 Maximum-length Mode。設定波形長度最少 100 點，實際最大值依儀器／型號。
- 類比通道標籤、Display Label、Display Annotation。
- Core/CLI/Simulator/Worker 支援已記載單次觸發命令，包括 `trigger-tv` 基本 TV/Video Set/Query。
- DSO-X 2000X/3000X/4000X 依 Operation Status Condition Run Bit 判定觸發擷取等待。

系列差異：

| 系列 | DEMO 輸出 Function | Serial Bus 數 | Serial 可設 Mode | Waveform Search Mode | 截圖格式 |
| --- | --- | ---: | --- | --- | --- |
| 2000X | 共用 Core 集合 | 1 | `can`, `i2c`, `lin`, `spi`, `uart` | `serial1` | 無明確格式選擇；既有 PNG 擷取仍支援 |
| 3000X | 共用集合加 `i2s`, `can-lin`, `flexray`, `arinc`, `mil`, `mil2` | 2 | `a429`, `flexray`, `can`, `i2s`, `i2c`, `lin`, `m1553`, `spi`, `uart` | `edge`, `glitch`, `runt`, `transition`, `serial1`, `serial2` | 無明確格式選擇；既有 PNG 擷取仍支援 |
| 4000X | 與 3000X 相同手冊集合 | 2 | `a429`, `flexray`, `can`, `cxpi`, `i2s`, `i2c`, `lin`, `m1553`, `manchester`, `nrz`, `sent`, `spi`, `uart`, `usb`, `usb-pd` | `edge`, `glitch`, `runt`, `transition`, `serial1`, `serial2`, `peak` | PNG、BMP、BMP8bit、外觀控制與狀態查詢 |

共用 Core DEMO 集合：`sine`、`noisy`、`phase`、`lf-sine`、`am`、`rf-burst`、`fm-burst`、
`harmonics`、`coupling`、`ringing`、`single`、`clock`、`runt`、`transition`、`setup-hold`、
`mso`、`burst`、`glitch`、`edge-then-edge`、`i2c`、`uart`、`spi`、`can`、`lin`。
記載的 DEMO Function 集合不含額外 4000X 專屬功能，不含 WGEN 行為，也不新增 WebUI Runtime 行為。

明確截圖格式僅開放 4000X，因其格式傳輸使用手冊的 `:HCOPY:SDUMp` 命令族。

三種 Profile 皆支援 `search-state` 與唯讀 `search-count`。
`search-mode` 先啟用 Search 再設 Mode；4000X 可用 `search-event` 導覽事件。
Serial Search 提供 UART/I2C/SPI/CAN 專屬搜尋控制；2000X 支援 Bus 1，3000X/4000X 支援 Bus 1、2。
必須先用對應 Serial 命令設定所選 Bus。

- 2000X/3000X Channel Label 最多 10 個可列印 ASCII 字元。
- 4000X Channel Label 最多 32 個可列印 ASCII 字元。
- 2000X/3000X Annotation 為單一無索引槽位，不支援 X/Y 位置。
- 4000X Annotation 支援索引槽位 1–10 與 X/Y 位置。
- 4000X 支援受限制的 `delay` 配對量測；2000X/3000X 因 Delay Query 依賴量測定義狀態，不公開此 Helper。

Raw Waveform Points Mode 維持停用。已註冊 2000X/3000X/4000X Profile 可查詢 Segmented Memory、
明確設定模式／次數，並執行有限次單通道 `segmented-capture`。
手冊次數範圍：2000X 為 2–250，3000X/4000X 為 2–1000，實際最大值可能因記憶體深度更低。
Segmented Memory 可能需要 SGM 選配／授權；Capability Flag 允許此手冊命令族路徑，
不表示選配已安裝。Segmented Capture 不連續擷取、不還原狀態、不停用 Segmented Mode、
不強制觸發、不合併 CSV，也不做儀器端 Save/Export。
Serial Decode 能力代表命令族可用，不代表已安裝授權。

Serial 彙總回應保留 Raw。協定設定僅提供基本 UART/I2C/SPI/CAN Source/Decode。
Serial Lister 新增全域 Display/Reference 控制，透過 `:LISTer:DATA?` 匯出電腦端 Raw CSV；
不解析協定專屬 CSV，也不支援儀器端 `:SAVE:LISTer`。
Serial Search 在設定相符 Bus 後提供 UART/I2C/SPI/CAN 專屬搜尋控制。
Lister `bus2` 在 2000X 不可用，3000X/4000X 可用；2000X 的 `all` 仍有效。
