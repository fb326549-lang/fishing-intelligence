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
