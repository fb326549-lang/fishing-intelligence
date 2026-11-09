# P2 資料契約（P2.1 + P2.2）

本階段只建立標準資料結構與品質驗證，不產生魚種門檻、活動分數或中魚機率。

## P2.1 逐時環境資料
每筆紀錄代表單一區域、單一有效小時。使用 `schema/hourly_environment_record.schema.json`。
- `valid_time`：資料描述的有效時間；`collected_at`：系統取得資料的時間。
- `data_type` 區分 forecast / observation / hindcast / derived。
- `source_records` 保留資料來源與資料集。
- `completeness` 記錄欄位完整度；`quality` 記錄品質與可信度。
- 潮位 `tide_height_m`、潮汐階段 `tide_phase`、轉折 `tide_turning`、潮流 `tidal_current_velocity_ms` 與方向分開。不得用潮位推算潮流速度。
- 海流 `ocean_current_velocity_ms` 與潮流分開保存；不可混用。
- 缺測值使用 null，不可用其他區域補值。

環境欄位包含浪高/週期/方向、海溫、海平面高度、海流速度/方向、風速/風向、潮位/潮汐階段/轉折/潮流、降雨/雷雨風險、日出/日落。

## P2.2 魚種反應參數
使用 `species/species_response_parameters_template.csv`。一筆資料只描述一個有證據支持的反應參數。
- 參數代碼：temperature_range、depth_range、habitat、wave_preference、current_preference、tide_response、wind_sensitivity、activity_period、salinity_preference。
- 每筆必須連結既有 candidate_id、evidence_id、來源 URL、可信度、適用生命階段與地理/棲地範圍。
- 未知或無可靠證據的參數不建立紀錄，不得填入推測門檻。
- 參數的數值與單位應依來源原意保存；不將定性敘述轉成看似精確數字。

## 驗證
`python P2/validate_p2_data.py --environment-jsonl records.jsonl --species-csv parameters.csv`
`python -m unittest discover -s P2 -p 'test_*.py' -v`

目前 P2.1/P2.2 為資料契約與 validator。尚未整合逐時資料來源，也未完成環境適合度或魚情模型。


## P2.1 逐時資料轉換器（第一版）

使用 `P2/collector/build_hourly_environment_records.py` 將現有 Open-Meteo 原始逐時 CSV 轉成標準 JSONL。可選擇加入 tide-history 分支的 CWA 48 小時觀測 JSONL：

```bash
python P2/collector/build_hourly_environment_records.py \
  --forecast-csv output/open_meteo/RUN_ID/environmental_forecast.csv \
  --forecast-dir output/open_meteo/RUN_ID \
  --cwa-observations-jsonl path/to/regional_marine_observations_48h.jsonl \
  --out output/p2/hourly_environment.jsonl
```

若不提供 CWA 檔案，則只產生 Open-Meteo forecast records。輸出每筆為單一區域、單一有效小時；forecast 與 observation 使用不同 record，不合併成同一筆。

Open-Meteo 天氣收集新增 hourly `showers`、`weather_code`，以及 daily `sunrise`、`sunset`。WMO weather code 95/96/99 標記為雷雨風險 high；其他有效 WMO code 標記 none；缺碼為 unknown。降雨機率與陣雨量分開保存。

CWA 觀測只使用同一區域/有效時間最新 collected_at revision。CWA current_speed_ms 對應一般 ocean current，不推定為 tidal current。潮位只寫入 tide_height_m。F-A0021-001 高低潮事件是離散事件，不在本轉換器內插成逐時潮位或潮流；潮汐 phase/turning/current 欄位未有直接證據時保持缺值。

執行：
```bash
python -m unittest discover -s P2 -p 'test_*.py' -v
python P2/validate_p2_data.py --environment-jsonl output/p2/hourly_environment.jsonl
```

此版尚未將潮汐事件轉成逐時 phase，也未將 P2 JSONL 接入 PWA；不得將缺值解讀為零。


## P2.2 既有生態證據遷移

`P2/species/migrate_p1_ecology_parameters.py` 將 P1 的 122 筆生態參數逐筆遷移到 `P2/species/species_response_parameters.csv`，並以 evidence_id 對應 P1 證據登錄表的 source_url。

遷移採無損保留：
- 原 parameter_code、parameter_value、unit、geographic_scope、confidence、model_use_status 不轉換。
- 來源限制與 source_type 保留在 notes。
- P1 未分別記載 life_stage 與 habitat_scope，因此明確填入 not_specified / not_separately_specified，不推測生命階段或微棲地。
- 每筆必須能連回同一 candidate_id 的 evidence_id 及 HTTP(S) source_url；缺少或衝突時遷移失敗。
- 保留 context_only、candidate_feature_only 等既有用途限制；不能把物種棲息深度當成釣棚建議，也不能把季節性或一般生態描述當成即時活動預測。

重新產生資料：
```bash
python P2/species/migrate_p1_ecology_parameters.py \
  --ecology-csv P1/species/species_ecology_parameters.csv \
  --evidence-csv P1/species/species_evidence_register.csv \
  --out P2/species/species_response_parameters.csv
python P2/validate_p2_data.py --species-csv P2/species/species_response_parameters.csv
```

目前匯入的是有來源的既有生態背景參數，不代表已經具備溫度、浪況、海流、潮汐等完整物種反應曲線。這些參數仍須逐項取得直接證據後才可新增；不會以通用生態敘述填補空白。


## P2.1.1 逐時歷史資料保存

新增 `P2/collector/archive_hourly_environment.py`，將已通過 P2 validator 的 JSONL 寫入專用 `p2-history` 分支，依有效日期分區：

`data/hourly_environment/YYYY/MM/YYYY-MM-DD.jsonl`

保存原則：
- 每筆紀錄保留自己的 valid_time、collected_at、region_id、data_type 及 source_records。
- 預報每次蒐集的 vintage 保留；同一有效小時的不同 collected_at 不會互相覆蓋。
- CWA 實測的不同 revision 保留；forecast / observation 不會合併。
- 以完整標準化 JSON 的 SHA-256 去重；完全相同的紀錄重跑時不會重複追加。
- 寫檔採暫存檔後原子替換；既有歷史列不更新、不刪除。
- 依 valid_time 的當地日期分區，保留時區資訊。

執行：
```bash
python P2/collector/archive_hourly_environment.py \
  --input output/p2/hourly_environment.jsonl \
  --archive-root p2-history-data/data
```

Open-Meteo 工作流程每 4 小時排程執行，也可手動觸發；驗證通過後才追加歷史資料。使用 workflow concurrency 避免同時寫入造成競爭。GitHub Actions 使用 repository contents write 權限提交至 `p2-history`。

資料路徑範例：
`https://github.com/fb326549-lang/fishing-intelligence/tree/p2-history/data/hourly_environment`

此為 Git 歷史資料保存，不等於資料庫服務；目前不會自動清理或覆寫舊資料。後續如需查詢 API、統計或大量歷史運算，再建立索引/快取層。


## P2.1.2 歷史資料索引目錄

新增 `P2/collector/build_hourly_history_catalog.py`。每次完成歷史追加後，workflow 會重建 `data/hourly_environment/catalog.json`，提供：
- 每日分區檔案路徑、SHA-256、檔案大小。
- 每日紀錄筆數、區域清單、資料類型分布。
- 各區域/資料類型的實際紀錄數、唯一有效小時數、蒐集版本數。
- valid_time 與 collected_at 覆蓋範圍。

紀錄筆數與唯一有效小時數刻意分開：同一小時可能有多個預報 vintage 或觀測 revision。索引是可重建的衍生資料，底層 JSONL 仍維持 append-only。索引不會推定缺測時數、不會補零，也不會跨區補值。

執行：
```bash
python P2/collector/build_hourly_history_catalog.py \
  --archive-root p2-history-data/data
```


## P2.2.1 優先魚種環境反應證據缺口矩陣

`P2/species/species_response_evidence_gaps.csv` 是研究排程與證據缺口登錄，不是模型參數表。初版包含 8 個優先候選：瓜子鱲（黑毛）、白毛（舵魚屬）、臭肚、黑鯛、條紋豆娘魚、孟加拉豆娘魚、瑪拉巴石斑及點帶石斑；每種檢視 7 個反應面向：水溫、浪況、一般海流、潮汐、風、活動時段、鹽度。P2.2.4 已另增南方舵魚與天竺舵魚兩個獨立物種候選，目前共 10 個候選、70 列。

矩陣會顯示既有生態參數代碼、證據編號及來源 URL，但不把棲地、報告深度、食性等背景描述冒充為環境反應曲線。白毛維持舵魚屬集合，必須有物種級鑑定才可建立單一物種模型；點帶石斑維持東部本島分布證據衝突的審查狀態。所有列目前均不得直接作為模型反應門檻。

重建：
```bash
python P2/species/build_species_response_gap_matrix.py \
  --candidates P1/species/species_candidate_register.csv \
  --ecology P1/species/species_ecology_parameters.csv \
  --evidence P1/species/species_evidence_register.csv \
  --out P2/species/species_response_evidence_gaps.csv
```

CI 會重建並逐位元比對矩陣，確保候選魚種及 P1 證據更新時，研究缺口登錄可追溯更新。


### P2.2.2 首批外部研究文獻

`P2/species/species_response_literature_register.csv` 新增 7 筆有來源的研究結果，涵蓋瓜子鱲（Girella punctata）、臭肚（Siganus fuscescens）及白毛俗名候選中的南方舵魚（Kyphosus bigibbus）。

重要限制：
- 南方舵魚在日本消波塊的冬春群聚研究，及生物遙測研究的水溫關聯，只能標記為外地、特定物種與特定棲地的 context-only 證據；不能直接當作台東磯釣溫度門檻，也不能推廣到所有 Kyphosus。
- 臭肚的 20°C 遙測訊號變化是活動代理指標，不是中魚率；26–29°C 與日間攝食時段來自特定藻類攝食控制試驗，不是野外釣獲最佳溫度/時段。
- 瓜子鱲的 18–23°C 養殖生長適溫及圈養繁殖研究，不能代替野外成魚活動反應。
- 目前 7 筆文獻全數不具備直接作為台灣東部魚情模型門檻的資格。

缺口矩陣已改為同時讀取 P1 生態背景與 P2 外部文獻登錄表；有外部文獻的領域標記為 `external_literature_found_context_only`，白毛物種級鑑定限制及點帶石斑東部分布衝突仍優先於文獻存在狀態。CI 會重建矩陣並逐位元比對。


## P2.1.3 歷史資料完整性稽核

`P2/collector/validate_hourly_history.py` 在每次新增分區並重建 catalog 後執行，稽核：
- 歷史分區與 catalog 的檔案集合一致，沒有漏列或過期索引。
- 每個分區檔案 SHA-256、位元組大小及紀錄數與 catalog 相符。
- JSONL 每列具有完整標準記錄必要欄位、合法六區 ID、合法 data_type、有效時區時間及 environment 物件。
- valid_time 的當地日期與所屬 YYYY/MM/YYYY-MM-DD 分區一致。
- 分區內沒有完全相同的重複紀錄。
- 全庫 record_count、partition_count、regions 及 data_types 統計與 catalog 相符。

執行：
```bash
python P2/collector/validate_hourly_history.py --archive-root p2-history-data/data
```

Open-Meteo 歸檔 workflow 已將此稽核放在提交 p2-history 之前；任何 checksum、分區、重複或索引錯誤都會讓該次歸檔 job 失敗，不會提交不一致的歷史索引。此稽核是資料完整性檢查，不取代 P2 JSON Schema / validator，也不代表觀測值本身已通過物理合理性校正。


## P2.2.3 台灣野外研究證據擴充（首批）

文獻登錄表新增 L008–L014，共 7 筆研究觀察，全部先標記為 context-only，不提供即時適合度門檻：

- L008–L011：Lee & Huang (1981)，瓜子鱲（Girella punctata）北台灣基隆岩岸月採樣研究。241 尾成魚、5 尾幼魚；記載成魚冬季/早春群聚、繁殖約 2–3 月、幼魚夏季可見潮池，以及季節性食性變化。研究年代較早且只有北台灣單一岩岸，不能當作台東最佳月份、潮汐相位或釣餌偏好。
- L012–L014：黑鯛（Acanthopagrus schlegelii）西台灣沿岸刺網漁業與遙測環境資料的 MaxEnt 棲地模型（2015–2018）。模型摘要指出 SST、海流與地形和季節棲地分布相關，漁場高適合度特徵包含 SST 約 20.6–28.9°C、海流約 0.28–0.83 m/s，並觀察到 12 月至翌年 4 月近岸漁獲較集中。這是西台灣刺網漁業空間模型，不能直接移植到東部磯釣，也不是中魚率模型。

缺口矩陣已更新：
- 瓜子鱲 activity_period：有北台灣野外季節群聚文獻，但仍是 context-only。
- 黑鯛 temperature_response / ocean_current_response：有西台灣漁業棲地模型，但仍是 context-only。
- 所有魚種的 model_use_policy 仍維持 not_model_eligible_until_direct_response_evidence_reviewed。

文獻來源：
- Lee & Huang (1981), *Some aspects of the biology of the nibblers, Girella punctata Gray from the northern coastal water of Taiwan*: https://zoolstud.sinica.edu.tw/Journals/20.1/17.pdf
- Black sea bream habitat distribution model, *Journal of Marine Science and Engineering* 9(12), 1442 (2021): https://doi.org/10.3390/jmse9121442

研究證據只用來更新證據登錄與研究缺口狀態；不得將西台灣、北台灣或養殖/圈養研究的數值直接轉成台灣東部魚情分數。


## P2.3 證據門檻式環境適合度引擎（第一版）

新增：
- `P2/species/environment_match_engine.py`：依已審查的物種反應規則，將單一區域/有效小時環境資料轉成環境匹配分數。
- `P2/species/environment_response_rules_template.csv`：反應規則登錄模板。
- `P2/test_environment_match_engine.py`：驗證證據門檻、物種鑑定門檻及缺測行為。

**只有同時符合以下條件的規則才會進入計分：**
1. `model_use_status=eligible_for_environment_scoring`。
2. `evidence_basis=east_taiwan_direct_field`。
3. confidence 為 high 或 medium。
4. 有 evidence_id、HTTP(S) source_url、reviewed_by 及 reviewed_at。
5. 環境欄位、運算子、數值範圍、區域及權重通過格式檢查。
6. 候選魚種的 `eligibility_gate` 必須是 `verified_taxon`。

白毛舵魚屬、俗名黑毛待形態鑑種，以及東部出現紀錄仍有衝突的候選魚種，不會進入計分。研究外地文獻、養殖資料、物種棲地描述及 context-only 參數均不會被當作反應規則。

執行前，環境 JSONL 必須先通過 `P2/validate_p2_data.py`；候選魚種 CSV 使用已重建的 `species_response_evidence_gaps.csv`（提供 eligibility_gate）；規則 CSV 使用審查模板：

```bash
python P2/validate_p2_data.py --environment-jsonl records.jsonl
python P2/species/environment_match_engine.py \
  --environment-jsonl records.jsonl \
  --candidates-csv P2/species/species_response_evidence_gaps.csv \
  --rules-csv P2/species/environment_response_rules_template.csv \
  --out output/p2/environment_match_scores.csv
```

輸出狀態：
- `scored`：有完整適用的已核准規則。
- `partial_environment_data`：部分規則所需環境欄位缺測，分數只根據已觀測規則計算，並揭露 coverage。
- `insufficient_evidence`：沒有已核准的台灣東部直接研究反應規則。
- `insufficient_environment_data`：有規則但所有必要環境欄位均缺測。
- `taxon_or_distribution_gate`：物種鑑定或區域出現資格未通過。

分數名稱為 `environment_match_score`，代表環境條件與已審查反應規則的匹配程度，**不是魚類活動強度、咬餌機率或中魚機率**。目前正式規則模板保持空白；現有 122 筆遷移參數沒有任何一筆被自動升格為反應規則，因此在補齊直接證據前，系統正確回報證據不足，不會虛構魚情分數。


## P2.2.4 白毛俗名與舵魚物種級證據拆分

白毛是地方俗名，不等於單一物種。優先研究矩陣擴充為 10 個候選、70 個反應領域列：
- c002：白毛俗名群組（Kyphosus spp.），仍維持 species_identification_required，不可直接產生物種分數。
- c036：南方舵魚（Kyphosus bigibbus），獨立物種候選。
- c037：天竺舵魚（Kyphosus cinerascens），獨立物種候選。

既有 L001、L003 研究對象均為 K. bigibbus，已由白毛俗名群組 c002 改掛至南方舵魚 c036。日本消波塊群聚及遙測資料仍標記 context_only_external_region，不得套用為台灣東部門檻。

新增 L015–L019：
- L015：瓜子鱲物種資料頁的日行性與岩礁激浪區活動描述，僅為分類資料背景。
- L016：南方舵魚物種資料頁的日行性、中表層與外礁環境描述，僅為分類資料背景。
- L017：天竺舵魚物種資料頁的日行性、中表層、岩礁/海藻床/潟湖描述，僅為分類資料背景。
- L018：天竺舵魚台東三仙台標本 FRIP21798（2007-01-02，底刺網），只證明曾出現。
- L019：瓜子鱲花蓮東堤標本 FRIP22025（竿釣），只證明曾出現。

L015–L017 的用途為 context_only_taxonomic_database；L019–L020 的用途為 occurrence_only_no_environment_response；L018 因典藏欄位衝突暫列 occurrence_record_conflict_requires_reconciliation。任何一筆都不會自動轉成環境反應規則或活動分數。

資料來源：
- 瓜子鱲：臺灣魚類資料庫 https://fishdb.sinica.edu.tw/taxon/381912-fishdb
- 南方舵魚：臺灣魚類資料庫 https://fishdb.sinica.edu.tw/taxon/381913-fishdb
- 天竺舵魚：臺灣魚類資料庫 https://fishdb.sinica.edu.tw/taxon/381914-fishdb
- 台東三仙台天竺舵魚標本 FRIP21798：https://fishdb.sinica.edu.tw/chi/specimendetail.php?id=FRIP21798
- FRIP21798 交叉典藏 ASIZP0802636：https://fishdb.sinica.edu.tw/muse/digi_object/61f77d718847328c7d2424f6381a8891
- 台東三仙台南方舵魚標本 ASIZP0805860：https://fishdb.sinica.edu.tw/muse/digi_object/6149599f37ab67e61a6983029a1734b4
- 花蓮東堤瓜子鱲標本 FRIP22025：https://www.tfrin.gov.tw/theme_data.php?id=1395&sub_theme=kuroshio&theme=collection

CI 會重建 70 列矩陣並逐位元比對；測試確認南方舵魚文獻不再掛在白毛俗名群組，且兩種舵魚各自保有物種級候選紀錄。
