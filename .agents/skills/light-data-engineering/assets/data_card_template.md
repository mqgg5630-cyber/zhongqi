# Dataset Card: {{dataset_name}}

> Datasheet for the dataset. Fill every section honestly. Empty/unknown fields
> must say "unknown" or "not assessed" — never leave a false impression.
> Field names align with HuggingFace Dataset Card / Datasheets for Datasets / Croissant for portability.

## 1. Overview
- **dataset_name**: {{dataset_name}}
- **version / DOI**: {{version}} / {{doi}}
- **provider / dataset_id**: {{provider}} / {{dataset_id}}
- **source_url**: {{source_url}}  (official host, not a repost/mirror)
- **source_revision**: {{revision_or_version}}  (commit/revision/data_id+version/record version)
- **domain**: {{domain}}
- **task**: {{task}}  (e.g. classification / regression / detection / segmentation)
- **data_type**: {{data_type}}  (tabular / image / text / time-series / multimodal)
- **size**: {{n_rows}} rows × {{n_cols}} cols  ({{n_bytes}} on disk)
- **format**: {{format}}  (csv / parquet / jsonl / ...)
- **license**: {{license}}  (commercial use? redistribution? attribution?)
- **license_locator**: {{official license/terms URL + section}}
- **access / gating**: {{public | login | gated | restricted}} — {{terms accepted / approver / expiry}}
- **download_url**: {{download_url}}
- **paper_url / citation**: {{paper_url}}
- **retrieved_at / raw_sha256 / raw_bytes**: {{timestamp}} / {{sha256}} / {{bytes}}

## 2. Motivation
- Why was this dataset created? What gap does it fill?
- Who funded / created it? (`creator`, `funder`)

## 3. Composition
- What does each instance represent? (a user, an image, a transaction...)
- Column/field dictionary: name, type, unit, meaning, allowed range/values.
- Label definition + how labels were obtained.
- Class balance / target distribution (attach counts).
- Are there splits provided? (`recommended_splits`) How were they made
  (random / stratified / temporal / by-group)? Seed?

## 4. Collection Process
- How was data acquired? (sensors, scraping, survey, logs, synthetic)
- Time window of collection. Sampling strategy. Selection bias risks.
- Was consent obtained? From whom? Under what terms?

## 5. Preprocessing / Cleaning (`preprocessing_steps`)
- Deduplication, type fixes, unit normalization, text cleaning.
- Missing-value handling (mechanism MCAR/MAR/MNAR + strategy).
- Outlier treatment. Filtering rules applied.
- Is the raw data preserved alongside the cleaned data?
- **lineage**: raw SHA256 → cleaning script + git commit → cleaned SHA256.
- **row mapping**: where is the kept/removed/changed row map? Never make cleaning irreversible.

## 6. Quality Assessment (run the tooling, paste results)
- **data_doctor.py** report attached? health summary:
- **quality_gate.py** result against `rules.yaml`: PASS / FAIL ( / checks)
- Completeness, consistency, accuracy, timeliness, uniqueness, representativeness.

## 7. Known Issues & Risks
- **known_issues**: {{known_issues}}
- **bias_risk**: {{bias_risk}}  (under-represented groups, label noise, spurious correlations)
- **privacy_risk**: {{privacy_risk}}  (PII present? de-identified how? re-identification risk?)
- Documented leakage hazards (columns that encode the target / future info).

## 7b. Access Level (访问分级)
> 给这份数据声明一个访问级别，决定它能流向哪些下游环节。由 `scripts/check_access_level.py` 校验。
- **access_level**: {{access_level}}  必须是以下之一：
  - `raw` — 含 PII / 未脱敏 / 受限原始数据。**禁止**进入会公开的产物（论文表格、图、附录、仓库样例）。
  - `redacted` — 已脱敏 / 去标识，PII 已移除或泛化。可用于内部分析，公开前仍需复核。
  - `verified_only` — 已核验可公开的派生数据 / 聚合统计。可进入论文与公开产物。
- **downgrade_from**: {{源数据的 access_level}}  （若本数据由更高敏感级派生而来，记录来源级别与脱敏动作）
- **redaction_actions**: {{做了哪些脱敏：删列 / 哈希 / 分桶 / 加噪 / k-匿名}}
- **gated_sinks**: 声明本级别**不可**流向的下游（如 raw → 不可进 paper/figure/public-repo）。

## 8. Recommended Use & Splits
- Intended tasks and metrics (`leaderboard_url` if any).
- **recommended_splits**: scheme + seed (use safe_split.py task = clf/reg/timeseries/group).
- **split identity**: observation unit + group/time columns that must not cross splits.
- **provided split provenance**: official split / self-created; source file/revision and generation script.
- Uses to avoid (out-of-scope, ethically problematic).

## 9. Maintenance
- Maintainer / contact. Update cadence. Versioning policy.
- How to report errors. Will old versions stay available?

## 10. Provenance & Verification
- Sources with checkable links (honor research-ethics: no fabricated DOIs).
- `last_checked_date`: {{date}}
- Which fields are verified vs inferred/unknown.
- **candidate decision**: why this dataset was selected; which alternatives were rejected and why.
- **snapshot**: provider/id + revision/version + source URL + retrieval timestamp + file list/hash manifest.
- **authority chain**: portal card → original paper/creator page → license/terms locator; note any conflicts.
