# Scenario 1 (Space) Final Submission

## 1. Problem Definition
- Research question: if Holyrood General Teaching (GT) rooms close, can Central alone absorb demand, or do we need Lauriston/New College plus timetable adjustments?
- Objective: minimize unassigned moved events under room-capacity and timetable-conflict constraints, while keeping schedule changes as small as possible.

## 2. Data and Scope
- Event data: `clean_outputs/events_clean.csv`
- Room data: `Rooms and Room Types.xlsx` (`Room` sheet)
- Included events: `room_type_2 == General Teaching` with valid `room/day/start/end`.
- All GT events originally in Holyrood are treated as mandatory moved events.

## 3. Method (Scenario 1)
- Evaluate 8 policy scenarios:
  - campus set changes (Central only, +Lauriston, +New College, +both)
  - same-day time shifting (<=60, <=120 minutes)
  - within-week cross-day reassignment
- Fixed events are loaded first into room occupancy.
- Moved events are assigned greedily by descending `event_size` (then duration/time order).
- Candidate slots are ranked by minimal disruption:
  - smaller day shift first
  - then smaller time shift
- Feasibility checks:
  - room capacity must satisfy `capacity >= event_size`
  - no overlap in the same room/day/week

## 4. Key Results
| Scenario | Unassigned moved events |
|---|---:|
| `central_only` | 355 |
| `central_plus_both` | 305 |
| `central_plus_both_shift60` | 106 |
| `central_plus_both_shift120` | 40 |
| `central_plus_both_shift60_crossday` | 0 |
| `central_plus_both_shift120_crossday` | 0 |

- Central only is not feasible (355 unassigned).
- Adding Lauriston + New College without retiming is still insufficient (305 unassigned).
- Same-day retiming helps strongly but is not enough alone (106 or 40 unassigned).
- Cross-day reassignment enables full placement (0 unassigned).

## 5. Student Commute Check (Added)
- Commute scope: 666 affected programmes.
- Metric used: adjacent same-day events with cross-campus movement where required travel time exceeds available gap.
- Move-related commute conflicts (pairs where at least one event is a moved Holyrood GT event):
  - `central_only`: 1,393
  - `central_plus_both_shift60_crossday`: 3,265
  - `central_plus_both_shift120_crossday`: 3,095
- Interpretation: once more Holyrood GT events are successfully placed, commute exposure rises; among zero-unassigned options, `shift120_crossday` gives lower move-related commute conflicts than `shift60_crossday`.

## 6. Recommended Option
- Best by minimum unassigned: `central_plus_both_shift60_crossday` (0 unassigned).
- Best by minimum adjustment among zero-unassigned solutions (recommended):
  - `central_plus_both_shift120_crossday`
  - shifted events: 540 total
  - day-shifted: 69
  - time-only shifted: 479
  - move-related commute conflicts: 3,095

## 7. Direct Answer to the Business Question
- Do we need campuses beyond Central? **Yes.**
- Is campus expansion alone enough? **No.**
- What is required to reach operational feasibility (0 unassigned)? **Cross-day retiming capability**, plus bounded time shifts.

## 8. Reproducibility
```powershell
python scenario1_space_analysis.py
python build_scenario1_report_pack.py
```

## 9. Scenario 1 Deliverables
- Decision: `clean_outputs/scenario1_space/scenario1_space_decision.json`
- Summary table: `clean_outputs/scenario1_space/scenario1_space_summary.csv`
- Commute conflicts: `clean_outputs/scenario1_space/scenario1_space_commute_conflicts.csv`
- Report summary: `clean_outputs/scenario1_space/report_pack/scenario1_report_summary.md`
- Final submission note (this file): `clean_outputs/scenario1_space/report_pack/scenario1_submission_final_en.md`
