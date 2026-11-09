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

分數名稱為 `environment_match_score`，代表環境條件與已審查反應規則的匹配程度，**不是魚類活動強度、咬餌機率或中魚機率**。 規則條件符合時採用該列 `match_score`；條件不符合時該列貢獻 0，再依權重計算已觀測規則的加權平均。輸出 `rules_matched` 是符合規則數，`rules_evaluated` 是具備有效輸入而實際評估的規則數；`rule_coverage` 則反映已評估權重占全部適用權重的比例。目前正式規則模板保持空白；現有 122 筆遷移參數沒有任何一筆被自動升格為反應規則，因此在補齊直接證據前，系統正確回報證據不足，不會虛構魚情分數。


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
- L018：天竺舵魚台東東部標本 FRIP21798。交叉典藏對同一關聯紀錄的日期、漁法與地點標示不一致（2007-01-02 底刺網、三仙台 vs 2006-01-02 手釣、成功），已標記 occurrence_record_conflict_requires_reconciliation；僅保留台東東部出現資訊，不把兩個頁面當成兩筆樣本。
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


## P2.4.1 魚種活動證據登錄（不產生活性分數）

新增：
- `species/species_activity_evidence_register.csv`：活動證據標準化登錄。
- `schema/species_activity_evidence.schema.json`：單筆活動證據 JSON Schema 契約。
- `species/validate_activity_evidence.py`：驗證候選物種、文獻編號、來源 URL、證據用途及分類。
- `test_activity_evidence.py`：測試來源對應、物種對應及禁止升格計分。

第一批 7 筆活動相關證據依研究方法與時間尺度分開保存：
- AE001：瓜子鱲北台灣野外冬季/早春成魚群聚（L008）；不是東部釣獲率。
- AE002：瓜子鱲資料庫日行性概述（L015）；不是東部逐時觀測。
- AE003：臭肚控制/養殖條件下藻類攝食日週期（L005）；不是野外咬況。
- AE004：黑鯛西台灣刺網季節漁獲/棲地模型（L014）；不是東部磯釣時段。
- AE005：南方舵魚日本海藻場生物遙測訊號與夜間未檢出（L003）；遙測訊號是活動代理，不是攝食或中魚率。
- AE006：南方舵魚資料庫日行性概述（L016）。
- AE007：天竺舵魚資料庫日行性概述（L017）。

目前所有紀錄均維持各自的 `context_only_*` 用途，不得輸出活動分數或最佳作釣時段。候選 c001（黑毛俗名）仍要求個體形態鑑種；白毛屬群組 c002 不因其他舵魚物種資料而自動取得活動參數。日行性、攝食時間、季節群聚、繁殖季及遙測訊號是不同觀測概念，不可互相替代。

驗證：
```bash
python P2/species/validate_activity_evidence.py \\
  --activity-csv P2/species/species_activity_evidence_register.csv \\
  --candidates-csv P1/species/species_candidate_register.csv \\
  --literature-csv P2/species/species_response_literature_register.csv
python -m unittest P2.test_activity_evidence -v
python -m unittest discover -s P2 -p 'test_*.py' -v
```

本工作僅完成活動證據資料層與品質閘門，尚未建立日出/日落、晨昏、季節、潮汐或海流對逐時活動的已驗證權重。下一步 P2.4.2 才會建立日夜/晨昏特徵；在缺乏直接東部活動資料前，時間特徵僅作上下文，不可當成魚活性分數。


## P2.4.2 日夜/晨昏中性時間特徵

新增 `collector/build_solar_time_context.py`，從逐時環境紀錄中的來源日出/日落時間，衍生不帶魚種假設的時間上下文：
- `dawn`：日出前後設定窗口內。
- `daylight`：日出窗口結束後至日落窗口開始前。
- `dusk`：日落前後設定窗口內。
- `night`：上述時段以外。
- 日出或日落缺值、時間格式無效時回傳 `unknown`，不猜測日出日落。
- 同時保留距日出/距日落分鐘數、區域、有效時間、資料類型及來源紀錄。

預設晨昏窗口為日出/日落前後各 60 分鐘，可透過 CLI 設定 0–180 分鐘。此窗口只是時間分箱設定，不是魚種活動門檻。輸出明確標記 `neutral_time_context_not_fish_activity_or_catch_probability`，不可直接換算成活性分數、咬況或最佳作釣時間。

執行：
```bash
python P2/collector/build_solar_time_context.py \\
  --input output/p2/hourly_environment.jsonl \\
  --out output/p2/solar_time_context.jsonl \\
  --twilight-window-minutes 60
python -m unittest P2.test_solar_time_context -v
```

P2.4.2 僅產生日夜/晨昏的中性時間特徵；魚種對晨昏的反應仍須有對應物種、地區、季節、生命階段及研究方法的直接證據後，才可進入後續活動模型。


## P2.4.3 季節性活動證據（證據層，不產生季節分數）

新增：
- `species/species_seasonal_activity_register.csv`：物種季節性活動證據登錄。
- `schema/species_seasonal_activity.schema.json`：季節證據資料契約。
- `species/validate_seasonal_activity.py`：驗證候選物種、學名、文獻來源、URL、用途限制。
- `test_seasonal_activity.py`：測試來源追溯、錯誤學名、白毛俗名群組隔離及禁止升格計分。
- `species/species_response_literature_register.csv` 新增 L021：臭肚北台灣北海岸近岸群聚自然史解說來源。

第一批季節性證據：
- SE001 瓜子鱲：基隆附近北台灣岩岸歷史月採樣，成魚冬季及早春群聚（L008）。這是北台灣單一岩岸歷史資料，不是台東/花蓮季節釣況；黑毛俗名仍須個體鑑種。
- SE002 南方舵魚：日本壹岐/九州消波塊周邊調查記錄 1–4 月群聚及研究場域的低水溫關聯（L001）。只適用已鑑定 K. bigibbus，不能套用天竺舵魚或台灣白毛俗名群組。
- SE003 臭肚：中研院生命科學圖書館自然史解說提及北台灣石門海岸春季至 5 月/6 月初近岸群聚；幼魚覓食與成魚繁殖需分開理解（L021）。該文不是原始定量長期研究，信心低，不可外推台灣東部。
- SE004 黑鯛：西台灣 2015–2018 刺網資料/MaxEnt 模型呈現 12 月至翌年 4 月近岸分布較集中（L014）。這是西部漁法與漁場的季節空間分布，不是東部磯釣活動或中魚率。

區域尺度研究另顯示台灣東部外海魚類群聚組成具有季節變化，並與黑潮動態相關；該研究使用 eDNA 群聚資料，不能據此推斷上述任一目標魚種的東部繁殖月份、近岸活動量或釣獲率。參考：國立臺灣大學學位論文「利用環境DNA高通量複合分子條碼技術以探究臺灣東部及西部外海魚類群聚在空間和季節上之差異」（2023 年季節採樣，24 個離岸採樣點）。

驗證：
```bash
python P2/species/validate_seasonal_activity.py \\
  --seasonal-csv P2/species/species_seasonal_activity_register.csv \\
  --candidates-csv P1/species/species_candidate_register.csv \\
  --literature-csv P2/species/species_response_literature_register.csv
python -m unittest P2.test_seasonal_activity -v
python -m unittest discover -s P2 -p 'test_*.py' -v
```

限制：所有 SE001–SE004 均維持 `context_only_*`。本階段不建立月份權重、不宣稱東部魚種最佳月份、不將繁殖期/漁業分布/群聚觀察轉成咬況或釣獲機率。後續若要形成東部季節性活動分數，必須有可定位到東部區域、物種鑑定、時間戳、漁法/觀察方法與足夠樣本量的連續資料，並將 effort 與未釣獲樣本納入，避免只用成功釣獲紀錄造成偏差。


## P2.4.4 潮汐與海流反應：證據層及中性水文上下文

本階段先把「資料可用」與「魚種反應已知」分開，避免把潮汐經驗直接寫成魚活性規則。

### 中性逐時水文上下文
新增：
- `collector/build_tide_current_context.py`：從已驗證逐時環境 JSONL，逐筆保留潮位、潮汐階段、潮汐轉折、潮流速度/方向及一般海流速度/方向。
- `schema/tide_current_context.schema.json`：上下文輸出契約。
- `test_tide_current_context.py`：驗證潮位、潮流與一般海流不混用，缺值不補值、不推斷。

執行：
```bash
python P2/validate_p2_data.py --environment-jsonl output/p2/hourly_environment.jsonl
python P2/collector/build_tide_current_context.py \\
  --input output/p2/hourly_environment.jsonl \\
  --out output/p2/tide_current_context.jsonl
python -m unittest P2.test_tide_current_context -v
```

轉換器只直接傳遞既有欄位：
- `tide_height_m` 是潮位高度，不是流速。
- `tide_phase` 只有來源明確提供 rising/falling/high_slack/low_slack 才保留；缺值不從潮位曲線自行猜測。
- `tide_turning` 只保留來源明確提供的布林值，不以單一小時資料推定轉折。
- `tidal_current_velocity_ms` 與 `ocean_current_velocity_ms` 分欄保存，不互相複製或換算。
- 任何缺值均明確標記 missing/unknown。

### 新增研究證據（全部 context-only）
文獻登錄新增：
- L022：Mori (1956)，日本岩岸瓜子鱲幼魚在低潮潮池被隔離時的社會/領域行為。這是幼魚潮池行為，不代表成魚偏好退潮或潮流越強越容易中魚。
- L023：Cowx 等（1998），台灣西部黑鯛幼生於春潮期間採樣，沿岸與河口樣點的平均流速不同，幼生多見於冬末至早春。這不是東部成魚磯釣研究；因只在春潮期間採樣，不能據此證明大潮優於小潮。

活動證據登錄新增：
- AE008：瓜子鱲幼魚低潮潮池行為，低信心、日本外部區域。
- AE009：黑鯛幼生與西部沿岸/河口流速差異，台灣西部、幼生階段。

更新 activity evidence schema、validator 與測試，允許上述兩種研究維度，但仍強制 `context_only_*`。目前沒有找到足以建立台灣東部目標魚種「漲/退潮偏好」、「大/小潮偏好」或「最佳潮流速度」的直接成魚釣獲研究，因此不建立任何潮汐/海流計分權重或門檻。

研究來源：
- Mori (1956), `https://doi.org/10.18960/seitai.5.4_145`
- Cowx et al. (1998), `https://agris.fao.org/search/en/records/65e00de37c7033e84bf001c6`

驗收限制：此階段完成的是水文欄位上下文與外部/西部研究證據整理，不代表魚種潮汐反應模型已可預測。未來要升格為東部活動反應，必須有物種鑑定、精確釣點/觀察位置、有效時間、潮位與實測潮流、方法/努力量及中魚與未中魚紀錄，並先做跨日期/釣點驗證。


## P2.4.5 環境適合度 × 活動證據整合（不虛構活性分數）

新增：
- `species/integrate_environment_and_activity.py`：以 candidate × region × valid_time 為鍵，整合 P2.3 環境適合度結果、活動證據及季節證據。
- `schema/integrated_hourly_fish_assessment.schema.json`：整合結果契約。
- `test_integrated_activity.py`：驗證活動分數/中魚機率不會由 context-only 文獻自動產生，物種鑑定 gate 不會被繞過，缺少環境適合度結果與重複鍵會明確處理。

執行順序：
```bash
python P2/species/environment_match_engine.py \\
  --environment-jsonl output/p2/hourly_environment.jsonl \\
  --candidates-csv P2/species/species_response_evidence_gaps.csv \\
  --rules-csv P2/species/environment_response_rules_template.csv \\
  --out output/p2/environment_match_scores.csv

python P2/species/integrate_environment_and_activity.py \\
  --environment-jsonl output/p2/hourly_environment.jsonl \\
  --candidates-csv P2/species/species_response_evidence_gaps.csv \\
  --environment-match-csv output/p2/environment_match_scores.csv \\
  --activity-csv P2/species/species_activity_evidence_register.csv \\
  --seasonal-csv P2/species/species_seasonal_activity_register.csv \\
  --out output/p2/integrated_hourly_fish_assessment.csv

python -m unittest P2.test_integrated_activity -v
```

輸出將環境適合度與活動證據分欄：
- `environment_match_status / environment_match_score`：只來自 P2.3 已審查的環境反應規則。
- `activity_evidence_status`：區分物種/分布 gate、只有背景證據、缺乏東部活動證據、或直接證據尚待規則審查。
- `activity_evidence_count / seasonal_evidence_count`：顯示可追溯的背景研究數量及 ID。
- `activity_score`、`catch_probability` 保持空白；`best_fishing_window_status=not_established`。

即使環境適合度已有分數，也不代表魚當下活躍或容易咬餌。外地研究、幼魚行為、繁殖/群聚背景、圈養攝食、物種資料庫概述及西台灣漁業模型，均不能自動升格成東部逐時活動規則。白毛屬群組、黑毛俗名待鑑種及分布衝突候選仍依既有 gate 阻擋。

此階段完成資料整合介面與證據閘門，並未完成可預測的魚種活性模型；真正的活動分數仍須等待台灣東部物種級、具時間戳且包含觀察努力/未觀察到魚的直接資料與正式審查。


## P2.4.6 未來 6/12/24 小時逐時展望彙整

新增：
- `species/build_hourly_fish_outlook.py`：依六個東部區域、候選魚種與 6/12/24 小時窗口彙整逐時預報。
- `schema/hourly_fish_outlook.schema.json`：展望摘要輸出契約。
- `test_hourly_fish_outlook.py`：驗證三種窗口、預報版本選擇、觀測/預報隔離、缺時段不補值、物種 gate、活動分數留白及六區無資料狀態。

預報版本選擇：
- 只取 `data_type=forecast`，不混入 observation。
- `collected_at` 必須不晚於 `--as-of`，避免使用分析時間之後才蒐集到的未來版本。
- 同一區域/有效小時保留截至 as-of 最新的 forecast vintage。
- `--as-of` 必須有時區且對齊整點；每個 horizon 以 [as-of, as-of + N hours) 計算。
- 6/12/24 小時缺少的預報小時不插值、不補值，輸出 coverage；六區即使完全沒有預報，也會回報 no_forecast_records。

執行：
```bash
python P2/species/build_hourly_fish_outlook.py \\
  --environment-jsonl output/p2/hourly_environment.jsonl \\
  --candidates-csv P2/species/species_response_evidence_gaps.csv \\
  --integrated-csv output/p2/integrated_hourly_fish_assessment.csv \\
  --as-of 2026-11-09T10:00:00+08:00 \\
  --out output/p2/hourly_fish_outlook.csv
python -m unittest P2.test_hourly_fish_outlook -v
```

每筆摘要分開呈現預報完整度、環境適合度可用時數及環境匹配分數的平均/最低/最高值；這些統計僅描述環境匹配，不是魚類活動強度。活動證據狀態及來源 ID 一併保留。由於目前沒有足夠的東部成魚逐時活動/釣獲資料，`activity_score`、`catch_probability` 保持空白，`best_fishing_window_status=not_established`；本階段不會把環境分數最高的小時稱為最佳作釣時段。

此輸出是 P2.4 的逐時展望資料層，尚未接入 PWA，也不是已驗證中魚機率模型。後續須以實際釣獲與空軍紀錄、作釣努力量及東部物種級直接觀察，逐步建立並驗證活動/中魚模型。


## P2.4.6 → PWA 即時展望發布管線

Open-Meteo 六區預報 workflow 在標準化逐時資料與驗證通過後，依序執行：
1. 驗證魚種活動及季節證據登錄表；所有現有證據維持 context-only。
2. 使用 `environment_response_rules_template.csv` 的已審查規則（目前模板為空，不得自行建立數值門檻）執行環境匹配。
3. 以 candidate × region × valid_time × data_type 整合環境匹配、活動與季節證據；forecast 與 observation 即使有效時間相同也保持分離。
4. 產生六區未來 6/12/24 小時展望，缺資料區域仍明確輸出。
5. 匯出 `data/latest_hourly_fish_outlook.json` 至 `p2-history` 分支，供 PWA 讀取。

PWA 從下列 raw JSON 讀取最新展望：
`https://raw.githubusercontent.com/fb326549-lang/fishing-intelligence/p2-history/data/latest_hourly_fish_outlook.json`

前端目前顯示四個已建立俗名對應的目標：黑毛（保留鑑種 gate）、白毛（舵魚屬群組 gate）、臭肚、黑鯛。其他魚種尚未接上此版 P2 物種登錄。前端呈現每個 horizon 的預報時數/完整度、環境反應規則狀態及活動證據狀態。

重要限制：
- 目前環境反應規則模板沒有任何經審查的東部數值規則，因此環境匹配分數應為空白/證據不足，不可從網站舊 heuristic 分數回填。
- 活動分數、中魚機率與最佳作釣時段一律不建立。
- P2.4.6 展望是預報環境摘要，不是魚群偵測或安全許可。
- 展望以 workflow 最新成功執行產出為準；前端若資料超過 8 小時會顯示可能過期。


## P2.5.1 真實釣況 Ground Truth 資料契約

P2.5 先建立可稽核的實際釣況資料，不急著訓練或輸出中魚率。

### 兩張表分離
- `P2/field_data/fishing_session_template.csv`：一筆代表一次完整出勤/釣況時段，包含開始/結束時間、六區代碼、釣法、實際有效作釣分鐘及總漁獲數。
- `P2/field_data/catch_event_template.csv`：一筆代表同一時段內某一魚種的一次漁獲批次，保留俗名、候選物種 ID、鑑定信心、數量、尺寸、重量、放流狀態及照片參照。
- JSON Schema 分別位於 `P2/schema/fishing_session.schema.json` 與 `P2/schema/catch_event.schema.json`。

### 關鍵資料規則
1. **零漁獲也必須記錄**：只要確實作釣且 effort_minutes > 0，就必須建立 session，catch_count 可為 0，catch event 可為空。這是避免模型只看成功案例而高估魚況的必要條件。
2. 有漁獲時，session.catch_count 必須等於其 catch events 的 count 加總。
3. 每個 catch event 必須連回有效 session，時間需落在該次 session 之內。
4. 時間必須包含時區；台灣資料建議使用 ISO 8601 +08:00。
5. 不確定魚種時保留俗名及 low/unconfirmed，不可猜測學名或 candidate_id。
6. 不要求上傳精確私人座標；location_label 記錄到可分析但不暴露私人進出資訊的程度。
7. 不從記憶補寫海溫、浪高、潮位等量測值。環境條件應由系統依區域與時間，從 P2 歷史資料配對；缺值維持缺值。
8. effort_minutes 是實際有效作釣時間，不是單純停留時間。

### 驗證
```bash
python P2/field_data/validate_fishing_logs.py \
  --sessions P2/field_data/fishing_session_template.csv \
  --catches P2/field_data/catch_event_template.csv
python -m unittest P2.test_fishing_logs -v
```

目前資料契約只驗證紀錄完整性與 session/catch 關聯，不會推論魚種活動分數、環境偏好或中魚率。下一步才建立環境快照配對器，並以「每次出勤」為樣本單位，避免把同一次出勤的多尾魚當成多次獨立成功樣本。


## P2.4.7 CWA 高低潮事件推導逐時潮汐階段

Open-Meteo 工作流程新增 CWA F-A0021-001 高低潮預報事件蒐集，使用明確審查的 `P1/stations/cwa_tide_region_mapping.csv` 將預報地點對應到六區，再由 `build_hourly_environment_records.py --cwa-tide-forecast-csv` 為逐時 forecast record 建立 `tide_phase` 與 `tide_turning`。

推導規則：
- 只使用同一 CWA 地點前後相鄰的官方滿潮/乾潮預報事件；乾潮→滿潮為 rising，滿潮→乾潮為 falling。
- 距離最近高/低潮事件 30 分鐘內，標記 high_slack / low_slack 及 `tide_turning=true`，表示預報轉折時間窗，不代表實測潮流已停流。
- 同一區域所有已映射預報地點必須得到相同階段；若地點間相位不同、缺少前後事件或事件資料不完整，整區階段保持 null，不以平均或最近點代替。
- 只在 forecast records 加入預報潮勢；不回填歷史 observation，避免以事後取得的預報版本造成時間洩漏。
- 不插值潮位高度、不推算潮流速度；`tide_height_m`、`tidal_current_velocity_ms` 仍保持各自獨立欄位與缺值。
- `source_records` 保留 CWA F-A0021-001 來源與擷取時間；品質旗標明示潮勢是由預報高低潮事件推導，並非實測潮流或流速。

執行：
```bash
python P1/collector/fetch_cwa_tide_forecast.py --out output/cwa_tides
python P1/collector/build_cwa_regional_tide_forecast.py --input output/cwa_tides/F-A0021-001.csv --mapping P1/stations/cwa_tide_region_mapping.csv --out output/cwa_tides/regional_tide_forecast.csv
python P2/collector/build_hourly_environment_records.py \
  --forecast-csv output/open_meteo/RUN_ID/environmental_forecast.csv \
  --forecast-dir output/open_meteo/RUN_ID \
  --cwa-observations-jsonl tide-history-data/data/regional_marine_observations_48h.jsonl \
  --cwa-tide-forecast-csv output/cwa_tides/regional_tide_forecast.csv \
  --out output/p2/hourly_environment.jsonl
```

測試涵蓋漲/退潮方向、高潮/低潮轉折時間窗、事件未涵蓋時段、不同地點相位不一致、來源可追溯，以及潮位/潮流不被虛構。潮汐階段只是水文上下文，不是任何魚種的偏好或中魚率。


## P2.4.8 六區 6/12/24 小時潮勢摘要

`build_hourly_fish_outlook.py` 會從每個區域的逐時 forecast record 彙整：
- 漲潮小時數、退潮小時數、高潮轉折窗小時數、低潮轉折窗小時數。
- 已判定潮勢時數、潮勢未判定時數、缺少預報時數及潮勢覆蓋率。
- 轉折窗小時數只統計上游 `tide_turning=true` 的預報小時，不表示實測潮流停流。

潮勢摘要是所有候選魚種共用的區域水文上下文，不參與魚種排序、環境匹配分數、活動分數、中魚機率或最佳時段。若沒有有效潮勢資料，維持零/未判定並揭露覆蓋率，不以其他區域或鄰近時段補值。PWA 決策首頁將在 P2 智慧魚情面板顯示這組 6/12/24 小時摘要。


## P2.4.9 台東物種出現標本證據（不等於活動證據）

新增可追溯的台東標本出現紀錄：
- 臭肚 `Siganus fuscescens`：ASIZP0072322，台東成功，2010-03-30。
- 條紋豆娘魚 `Abudefduf vaigiensis`：ASIZP0911844，台東基翬，2005-10-06，成魚，採集資料記載釣獲。
- 條紋豆娘魚 `Abudefduf vaigiensis`：FRIP21009，台東成功，2005-04-02，一支釣，幼魚標本。

這些資料用於補強東部物種出現證據與資料來源可追溯性；每筆只代表單一典藏標本/採集事件，不能推論當地族群密度、季節性、逐時活動、潮汐/海象反應或中魚率。活動證據維持 `context_only_east_taiwan_occurrence`，不進入環境規則、活動分數或最佳時段模型。P1 證據 ID 全域唯一，這三筆新增標本紀錄使用 E047–E049。P2 整合狀態可以顯示「已有東部出現背景資料」，但仍不視為已具備魚種活動預測證據。


## P2.4.10 核心目標魚種的東部出現紀錄

新增三筆核心候選魚種的東部紀錄：
- 瓜子鱲／黑毛俗名候選 `Girella punctata`：水產試驗所典藏 FRIP22025，2007-06-28 花蓮東堤釣魚比賽竿釣釣獲，300mm、485g。這是單次釣獲紀錄，但不提供釣獲時段或環境條件。
- 南方舵魚 `Kyphosus bigibbus`：ASIZP0805860，2012-04-30 台東三仙台尾柄肌肉組織標本。
- 天竺舵魚 `Kyphosus cinerascens`：ASIZP0802636，2006-01-02 台東成功尾柄肌肉組織標本。

三筆均為 `context_only_east_taiwan_occurrence`，只證明物種/單次釣獲曾在東部出現。不得推論季節性、逐時活動、潮汐/海象反應或中魚率。黑毛俗名群仍須個體鑑種；白毛舵魚屬群仍須鑑定到種。組織標本不代表可釣獲或常態族群。


## P2.6 海保署魚類 eDNA 出現背景（非魚群數量／非釣況預測）

資料來源：海洋保育署「110–113年臺灣鄰近海域魚類 eDNA 調查分析」政府資料開放資料集（資料集 172487），包含潛水調查、船舶調查及海洋保護區站點三組資料。欄位包含站點、座標、深度、採樣時間、學名、中文學名、科別及計畫類別。

新增：
- `collector/fetch_oca_edna_occurrence.py`：下載三組官方資料，支援 CSV、JSON 及 ZIP 包裝，統一欄位與採樣年月。
- `schema/edna_occurrence_context.schema.json`：單筆 eDNA 陽性偵測資料契約。
- `test_oca_edna_occurrence.py`：測試資料格式解析、民國年月、六區最近參考站距離、物種候選對應及出現資料限制。
- `.github/workflows/oca-edna-occurrence-context.yml`：每月蒐集一次，並支援手動執行；原始標準化輸出以 Actions artifact 保存，待資料品質審查後才考慮接入 P2 展望。

執行：
```bash
python P2/collector/fetch_oca_edna_occurrence.py \\
  --mapping P1/stations/east_region_station_mapping.csv \\
  --candidates P1/species/species_candidate_register.csv \\
  --out-dir output/oca_edna_context
python -m unittest P2.test_oca_edna_occurrence -v
```

資料解讀與防誤用規則：
1. eDNA 陽性偵測只代表該次採樣在該站點檢出物種 DNA，不代表個體數、族群密度、生物量、釣獲率或即時活動強度。
2. 沒有檢出不代表魚不存在；不得把未檢出紀錄當作負樣本，因採樣努力量、季節、檢測靈敏度及環境 DNA 傳輸/降解可能不同。
3. 依最近東部參考站的區域對應僅供地理上下文，並保留距離；超出 35 公里不強行分配六區，也不把參考站當成實際採樣站或釣點。
4. 只對已能以學名精確對應的候選物種填入 candidate_id；斜線合併的多物種名稱（例如 Abudefduf sexfasciatus/vaigiensis、Siganus canaliculatus/fuscescens）保留 possible_candidate_ids 並標記 ambiguous_multi_species_taxon，不會強制歸到其中一種。俗名群組、屬級候選及未確認物種不做模糊配對。
5. 月摘要的 `positive_detection_record_count` 是陽性資料列數，不是魚隻數或標準化盛度；不同計畫/方法/採樣努力量不可直接比較。manifest 另分開報告精確候選、模糊多物種與未匹配資料筆數。
6. 所有資料固定為 `context_only_edna_occurrence`，不輸出 activity_score、catch_probability、最佳作釣時段，也不作為環境規則的數值權重。

第一次官方資料抓取已成功取得 19,731 筆陽性 eDNA 資料列、258 筆候選物種/月/區域摘要。這是資料列數而非魚隻數；約 13,381 筆因距六區參考站超過 35 公里而保留為未分區背景資料，避免硬塞進六區。資料中也存在多物種合併學名，必須保持 ambiguous，不能當成 c003 臭肚或 c027 條紋豆娘魚的確證。

只有在成功取得三組來源、資料解析通過且輸出筆數大於零時才產生 artifact。此階段先建立可追溯的物種出現背景資料，尚未把 eDNA 偵測轉成魚情分數或即時魚群判斷。

## P2.6 海保署魚類 eDNA 出現背景（非魚群數量／非釣況預測）

資料來源：海洋保育署「110–113年臺灣鄰近海域魚類 eDNA 調查分析」政府資料開放資料集（資料集 172487），包含潛水調查、船舶調查及海洋保護區站點三組資料。欄位包含站點、座標、深度、採樣時間、學名、中文學名、科別及計畫類別。

新增：
- `collector/fetch_oca_edna_occurrence.py`：下載三組官方資料，支援 CSV、JSON 及 ZIP 包裝，統一欄位與採樣年月。
- `schema/edna_occurrence_context.schema.json`：單筆 eDNA 陽性偵測資料契約。
- `test_oca_edna_occurrence.py`：測試資料格式解析、民國年月、六區最近參考站距離、物種候選精確/模糊對應及出現資料限制。
- `.github/workflows/oca-edna-occurrence-context.yml`：每月蒐集一次，並支援手動執行；標準化輸出以 Actions artifact 保存，待資料品質審查後才考慮接入 P2 展望。

資料解讀與防誤用規則：
1. eDNA 陽性偵測只代表該次採樣在該站點檢出物種 DNA，不代表個體數、族群密度、生物量、釣獲率或即時活動強度。
2. 沒有檢出不代表魚不存在；不得把未檢出紀錄當作負樣本，因採樣努力量、季節、檢測靈敏度及環境 DNA 傳輸/降解可能不同。
3. 依最近東部參考站的區域對應僅供地理上下文，並保留距離；超出 35 公里不強行分配六區，也不把參考站當成實際採樣站或釣點。
4. 只對已能以學名精確對應的候選物種填入 candidate_id；多物種合併學名、俗名群組、屬級候選及未確認物種不做模糊配對。
5. 月摘要的 `positive_detection_record_count` 是陽性資料列數，不是魚隻數或標準化盛度；不同計畫/方法/採樣努力量不可直接比較。
6. 所有資料固定為 `context_only_edna_occurrence`，不輸出 activity_score、catch_probability、最佳作釣時段，也不作為環境規則的數值權重。

資料流程會先通過三組來源蒐集、欄位正規化、逐筆 JSON Schema 驗證及 occurrence-only 語意檢查。此階段只建立可追溯的物種出現背景資料，尚未把 eDNA 偵測轉成魚情分數或即時魚群判斷。


### P2.6 → PWA 歷史出現背景介接

eDNA 蒐集器另輸出精簡的 `edna_candidate_region_context.json`，按候選物種 × 六區分開計算：
- 精確學名陽性檢出資料列數、採樣月份數、站點數、採樣年月範圍及樣本深度範圍。
- 可能涉及該候選的多物種合併標籤筆數與原始合併學名，獨立標示為 ambiguous，不加到精確檢出數。
- 每筆均固定 `context_only_edna_occurrence`，不輸出活動分數或中魚機率。

每月 OCA workflow 將精簡 JSON 與資料 manifest 發布至 `p2-history/data/`；Open-Meteo/P2 四小時流程讀取該檔，將它嵌入 `latest_hourly_fish_outlook.json` 的 `edna_occurrence_context` 區塊。PWA 可依目前區域及候選魚種顯示歷史採樣背景。若尚未發布或沒有該候選/區域資料，前端必須明確說明「未找到精確檢出紀錄不代表魚不存在」，不能顯示為物種不存在。


## P2.4.10 東部出現紀錄與活動研究證據分流

活動證據登錄表中的 `activity_dimension=occurrence_record` 代表博物館標本、單次採集或單次釣獲等「曾在當地出現」紀錄，不是魚類活動研究。整合器現在將其獨立分流：
- `activity_evidence_count/ids`：只計入活動、攝食、季節、遙測等活動研究資料；不含單次出現紀錄。
- `occurrence_evidence_count/ids`：只列出經鑑種且具來源的地區出現紀錄。
- 只有出現紀錄時，活動狀態仍為 context-only；活動分數、中魚機率與最佳時段保持空白/未建立。
- 逐時展望將同一候選的出現紀錄去重後彙整，不因 6/12/24 小時內多筆 forecast row 而重複計數。

PWA 分開顯示「活動研究」與「東部出現紀錄」，避免使用者將單筆標本或單次釣獲誤讀成活動證據或即時魚群訊號。


## P2.4.11 東部鬼頭刀商業漁業季節分布研究

新增 L030 / SE005，來源為農業部農業知識入口網研究報告「臺灣東部新港海域鬼頭刀延繩釣漁業漁獲組成及作業漁場分布」：
- 2003–2018 年台東新港魚市場量測 88,902 尾鬼頭刀；另使用 2012–2018 年延繩釣樣本船作業資料。
- 報告主要商業盛漁期為 4–6 月及 10–12 月。
- 1–3 月約 75% 作業航次集中於新港外海；4–6 月漁場往東南移動；10–12 月往北偏移至花蓮海域。
- 此資料具有台灣東部在地季節性商業漁業資訊，但漁法是離岸延繩釣，不是岸際磯釣。只能作為鬼頭刀季節分布與商業漁場移動背景，不能轉成岸釣最佳月份、逐時活動或中魚率。
- 模型用途維持 `context_only_east_taiwan_commercial_fishery`，不參與即時活動分數及最佳時段推估。
