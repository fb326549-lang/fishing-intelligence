# C1 出釣安全決策（第一階段）
本目錄建立官方警特報到六區風險判斷的獨立安全閘門。此引擎不計算魚情或中魚率。

## 官方資料來源盤點
- CWA OpenData W-C0033-001：各別縣市地區目前天氣警特報。
- CWA OpenData W-C0033-002：警特報內容、影響區域與有效期間。
- CWA OpenData W-C0033-003：豪大雨特報。
- CWA OpenData W-C0033-006：陸上強風特報；只作岸際保守提示，不冒充海上風力警報。
- CWA OpenData W-C0034-001：颱風警報（CAP 格式；須辨識 Issue/Update/Cancel、有效期間及影響區域）。
- CWA OpenData O-B0069-001：大潮監測資料；每小時更新、回看過去 8 小時，提供各測站最大潮高、注意值與暴潮警戒高度。只有超過暴潮警戒高度才列高風險，超過大潮注意值列警示；不可把一般高低潮直接等同危險。
- CWA OpenData O-B0070-001：長浪監測資料；每小時更新、回看過去 8 小時。長浪警戒條件為週期至少 8 秒且浪高至少 1.5 公尺；巨浪警戒為浪高大於 6 公尺。須保留測站位置與觀測時間，不能把單站狀態直接當成整區實測。
- CWA 海象環境資訊平台：海象警示燈號、暴潮警戒與沿海遊憩風險；未確認穩定公開介面前，不可假稱已自動介接。

官方參考：
- https://opendata.cwa.gov.tw/dist/opendata-swagger.html
- https://ocean.cwa.gov.tw/V2/warning_light
- https://ocean.cwa.gov.tw/V2/rogue_waves
- https://ocean.cwa.gov.tw/V2/safe_see

## 六區與安全規則
六區為本專案規劃區，非官方海域警報邊界。行政區到六區的映射必須明確維護；無法映射的影響範圍不可丟棄，需使該區資料狀態降為資訊不足。
- high_risk：有效颱風警報影響區域。
- warning：其他有效官方警特報影響區域。
- no_active_alerts_reported：本版本要求來源均成功且新鮮，沒有有效警報。**不代表安全或可出釣。**
- insufficient_data：來源缺漏、逾時、解析失敗或影響範圍無法映射。
任何狀態的 safety_clearance 永遠為 false。現場浪況、岸際公告、港區/保護區管制與個人裝備仍須獨立確認。

## C1.2 海象觀測資料
- CWA OpenData O-B0075-001：48 小時浮標站與潮位站海況監測資料。
- CWA OpenData O-B0075-002：30 天浮標站與潮位站海況監測資料。
- 使用 P1/stations/east_region_station_mapping.csv 的明確 station_id → region_id 對照，只納入 station_status=1 的測站。
- 輸出 tide-history/data/latest_marine_conditions.json，按六區保留測站、最新觀測時間、48 小時筆數及 30 天筆數。
- 單站資料不外推到其他區域；缺測不等於平靜或安全。
- 最新觀測超過 180 分鐘標記 stale；資料欄位原樣保留，不猜測波浪欄位名稱或單位。
- 此資料是「觀測」不是「預報」，目前不計算魚活性、中魚率或安全許可。

官方參考：
- https://opendata.cwa.gov.tw/dataset/all/O-B0075-001
- https://opendata.cwa.gov.tw/dataset/all/O-B0075-002
- https://www.cwa.gov.tw/Data/data_catalog/4-1-1.pdf

C1.1 已建立官方安全來源自動蒐集及六區警特報判斷；C1.2 新增海象觀測自動蒐集與六區彙整。兩者由 GitHub Actions 每 15 分鐘執行，並發布至 tide-history 分支。海象觀測需待本次 CI 與真實資料輸出驗證後，才算正式完成。