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
