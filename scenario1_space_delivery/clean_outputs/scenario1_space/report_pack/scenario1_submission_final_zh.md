# Scenario 1（Space）最终提交版

## 1. 任务与问题定义
- 研究问题：若 Holyrood 的 General Teaching（GT）房间不可用，是否仅靠 Central 可承接教学，还是必须引入 Lauriston / New College，并允许一定重排。
- 目标：在保证容量和时间不冲突的前提下，最小化需要迁移事件的 `unassigned` 数量，并控制重排幅度。

## 2. 数据与建模边界
- 事件数据：`clean_outputs/events_clean.csv`
- 房间数据：`Rooms and Room Types.xlsx`（`Room` sheet）
- 仅纳入：`room_type_2 == General Teaching` 且有有效 `room/day/start/end` 的事件。
- 将 `campus == Holyrood` 的 GT 事件视为“必须迁移事件”。

## 3. 方法说明（Scenario 1）
- 建立 8 个策略场景（Central-only、加入 Lauriston / New College、同日时间平移、跨天重排）。
- 固定事件先占用房间时段；迁移事件按 `event_size` 从大到小依次分配（贪心优先分配）。
- 候选时段按“改动最小”排序：先最小 day shift，再最小 time shift。
- 分配约束：
  - 房间容量 `capacity >= event_size`
  - 同 room/day/week 不允许时间区间重叠
- 评估指标：
  - `moved_events_unassigned`（核心主指标）
  - `moved_events_shifted`、`moved_events_day_shifted`、`moved_events_time_shifted`
  - `shifted_avg_abs_minutes`、利用率与高压时段统计

## 4. 关键结果
| 场景 | 未分配事件 |
|---|---:|
| `central_only` | 355 |
| `central_plus_both` | 305 |
| `central_plus_both_shift60` | 106 |
| `central_plus_both_shift120` | 40 |
| `central_plus_both_shift60_crossday` | 0 |
| `central_plus_both_shift120_crossday` | 0 |

- 结论 1：只用 Central 明显不可行（355 未分配）。
- 结论 2：仅增加 Lauriston + New College 仍不足（305 未分配）。
- 结论 3：允许同日平移可显著下降，但仍非 0（60 分钟余 106，120 分钟余 40）。
- 结论 4：允许“周内跨天 + 时间平移”后可实现 `0 unassigned`。

## 5. 推荐方案
- 若仅按“未分配最少”：`central_plus_both_shift60_crossday`（0 未分配）。
- 若在“0 未分配”前提下追求更少改动（项目推荐）：
  - `central_plus_both_shift120_crossday`
  - 总调整事件：540
  - 其中 day shift：69
  - 其中 time-only shift：479

## 6. 对业务问题的直接回答
- “是否需要 Central 之外校区？”：**需要**。
- “仅扩容校区是否足够？”：**不够**。
- “达到可执行（0 未分配）需要什么？”：**需要跨天重排能力**（并配合有限时间平移）。

## 7. 可复现命令
```powershell
python scenario1_space_analysis.py
python build_scenario1_report_pack.py
```

## 8. 交付文件（Scenario 1）
- 决策文件：`clean_outputs/scenario1_space/scenario1_space_decision.json`
- 汇总表：`clean_outputs/scenario1_space/scenario1_space_summary.csv`
- 报告摘要：`clean_outputs/scenario1_space/report_pack/scenario1_report_summary.md`
- 提交版文档（本文件）：`clean_outputs/scenario1_space/report_pack/scenario1_submission_final_zh.md`
