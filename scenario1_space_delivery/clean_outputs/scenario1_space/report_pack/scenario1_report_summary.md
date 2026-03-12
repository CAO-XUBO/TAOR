# Scenario 1 Space Report Pack

## Key Findings
- With Central only, unassigned events are **355**.
- With Central+Lauriston+New College and no retiming, unassigned events are **305**.
- With same-day retiming (<=120 minutes), unassigned events drop to **40**.
- With within-week cross-day retiming, unassigned events drop to **0**.
- Move-related commute conflicts in `central_only`: **1393**.

## Recommended Scenario
- Best by unassigned: `central_plus_both_shift60_crossday`
- Best min-adjustment (under zero-unassigned): `central_plus_both_shift120_crossday`
- `central_plus_both_shift120_crossday` adjusts 540 events total, with 69 day shifts and 479 time-only shifts.
- Move-related commute conflicts under `central_plus_both_shift120_crossday`: **3095**.

## Files
- `scenario1_report_kpi_table.csv`
- `scenario1_unassigned_by_scenario.png`
- `scenario1_tradeoff_scatter.png`
- `scenario1_shift_profile.png`
- `scenario1_commute_conflicts_by_scenario.png`
