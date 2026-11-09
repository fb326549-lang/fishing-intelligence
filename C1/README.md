# C1 出釣安全決策（第一階段）
本目錄建立官方警特報到六區風險判斷的獨立安全閘門。此引擎不計算魚情或中魚率。

## 官方資料來源盤點
- CWA OpenData W-C0033-001：各別縣市地區目前天氣警特報。
- CWA OpenData W-C0033-002：警特報內容、影響區域與有效期間。
- CWA OpenData W-C0033-003：豪大雨特報。
- CWA OpenData W-C0033-006：陸上強風特報；只作岸際保守提示，不冒充海上風力警報。
- CWA OpenData W-C0034-001：颱風警報。
- CWA 海象環境資訊平台：海象警示燈號、長浪/巨浪、暴潮與沿海遊憩風險。網頁產品尚未確認穩定公開 API，未介接前必須標示來源未整合。

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

本階段交付資料契約、六區安全引擎與單元測試；尚未宣稱官方警報已完成即時抓取。