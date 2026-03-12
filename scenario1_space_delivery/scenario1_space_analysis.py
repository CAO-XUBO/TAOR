from pathlib import Path
import ast
import json
import pandas as pd
import numpy as np


BASE_DIR = Path(".")
EVENTS_FILE = BASE_DIR / "clean_outputs" / "events_clean.csv"
ROOMS_FILE = BASE_DIR / "Rooms and Room Types.xlsx"
STUDENT_EVENT_FILE = BASE_DIR / "2024-5 Student Programme Module Event.xlsx"
OUTDIR = BASE_DIR / "clean_outputs" / "scenario1_space"
OUTDIR.mkdir(parents=True, exist_ok=True)


DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAYS = DAY_ORDER[:5]
DAY_RANK = {d: i for i, d in enumerate(DAY_ORDER)}
CAMPUS_FIX = {
    "Kings Buildings": "King's Buildings",
}
MIN_TEACHING_START = 8 * 60
MAX_TEACHING_END = 20 * 60
CROSSDAY_START_CANDIDATE_LIMIT = 12
MAX_SLOT_CANDIDATES = 80


def normalize_campus(value):
    if pd.isna(value):
        return np.nan
    txt = str(value).strip()
    return CAMPUS_FIX.get(txt, txt)


def clean_id_series(series):
    return series.astype("string").str.strip().str.upper()


def safe_pct(num, den):
    if den == 0:
        return 0.0
    return round((num / den) * 100.0, 4)


def parse_week_list(week_list_cell):
    if isinstance(week_list_cell, list):
        return [int(x) for x in week_list_cell if pd.notna(x)]
    if pd.isna(week_list_cell):
        return []
    txt = str(week_list_cell).strip()
    if not txt:
        return []
    try:
        parsed = ast.literal_eval(txt)
        if isinstance(parsed, list):
            return [int(x) for x in parsed if pd.notna(x)]
    except Exception:
        pass
    nums = [int(x) for x in "".join(ch if ch.isdigit() else " " for ch in txt).split()]
    return nums


def intervals_overlap(start_a, end_a, start_b, end_b):
    return max(start_a, start_b) < min(end_a, end_b)


def build_reference_starts(gt_events):
    starts = {}
    for day in DAY_ORDER:
        day_starts = (
            gt_events.loc[gt_events["day"] == day, "start_min"]
            .dropna()
            .astype(float)
        )
        day_starts = day_starts[
            (day_starts >= MIN_TEACHING_START) & (day_starts <= MAX_TEACHING_END)
        ]
        starts[day] = sorted(day_starts.unique().tolist())
    return starts


def candidate_shifted_starts(original_start, duration, day, max_shift_minutes, reference_starts):
    base_start = float(original_start)
    if max_shift_minutes <= 0 or day not in reference_starts:
        return [base_start]

    candidates = []
    for start in reference_starts.get(day, []):
        if abs(start - base_start) <= max_shift_minutes and (start + duration) <= MAX_TEACHING_END:
            candidates.append(float(start))

    if (MIN_TEACHING_START <= base_start <= MAX_TEACHING_END) and ((base_start + duration) <= MAX_TEACHING_END):
        candidates.append(base_start)

    if not candidates:
        return [base_start]

    # Prefer minimal move, then earlier start as deterministic tiebreaker.
    ordered = sorted(set(candidates), key=lambda x: (abs(x - base_start), x))
    return ordered


def candidate_days(original_day, allow_day_shift, max_day_shift_steps):
    if not allow_day_shift or original_day not in DAY_RANK:
        return [original_day]

    days = []
    base_rank = DAY_RANK[original_day]
    for day in WEEKDAYS:
        dist = abs(DAY_RANK[day] - base_rank)
        if dist <= max_day_shift_steps:
            days.append((day, dist))
    days = sorted(days, key=lambda x: (x[1], DAY_RANK[x[0]]))
    return [d for d, _ in days]


def crossday_start_candidates(original_start, duration, day, reference_starts):
    starts = [
        float(s) for s in reference_starts.get(day, [])
        if (MIN_TEACHING_START <= float(s) <= MAX_TEACHING_END) and (float(s) + duration <= MAX_TEACHING_END)
    ]
    starts = sorted(set(starts), key=lambda s: (abs(s - float(original_start)), s))
    if not starts:
        return [float(original_start)]
    return starts[:CROSSDAY_START_CANDIDATE_LIMIT]


def build_candidate_slots(
    original_day,
    original_start,
    original_end,
    allow_time_shift,
    max_shift_minutes,
    allow_day_shift,
    max_day_shift_steps,
    reference_starts,
):
    duration = float(original_end - original_start)
    day_list = candidate_days(
        original_day=original_day,
        allow_day_shift=allow_day_shift,
        max_day_shift_steps=max_day_shift_steps,
    )

    slots = []
    for day in day_list:
        if day == original_day:
            starts = (
                candidate_shifted_starts(
                    original_start=original_start,
                    duration=duration,
                    day=day,
                    max_shift_minutes=max_shift_minutes if allow_time_shift else 0,
                    reference_starts=reference_starts,
                )
                if allow_time_shift
                else [float(original_start)]
            )
        else:
            starts = crossday_start_candidates(
                original_start=original_start,
                duration=duration,
                day=day,
                reference_starts=reference_starts,
            )

        for start in starts:
            day_dist = abs(DAY_RANK.get(day, 99) - DAY_RANK.get(original_day, 99))
            time_dist = abs(float(start) - float(original_start))
            slots.append((day, float(start), float(start + duration), int(day_dist), float(time_dist)))

    slots = sorted(slots, key=lambda x: (x[3], x[4], DAY_RANK.get(x[0], 99), x[1]))
    dedup = []
    seen = set()
    for row in slots:
        key = (row[0], row[1])
        if key not in seen:
            seen.add(key)
            dedup.append(row)
    return dedup[:MAX_SLOT_CANDIDATES] if dedup else [(original_day, float(original_start), float(original_end), 0, 0.0)]


def load_inputs():
    events = pd.read_csv(EVENTS_FILE)
    rooms = pd.read_excel(ROOMS_FILE, sheet_name="Room")

    events["event_id"] = clean_id_series(events["event_id"])
    events["campus"] = events["campus"].map(normalize_campus)
    rooms["Campus"] = rooms["Campus"].map(normalize_campus)

    gt_events = events[
        events["room_type_2"].astype("string").str.strip().eq("General Teaching")
        & events["room"].notna()
        & events["day"].notna()
        & events["start_min"].notna()
        & events["end_min"].notna()
    ].copy()

    gt_events["event_size"] = pd.to_numeric(gt_events["event_size"], errors="coerce")
    gt_events["week_list_parsed"] = gt_events["week_list"].apply(parse_week_list)
    gt_events["week_list_parsed"] = gt_events["week_list_parsed"].apply(lambda x: x if x else [-1])
    gt_events["day_order"] = gt_events["day"].map({d: i for i, d in enumerate(DAY_ORDER)}).fillna(999)

    room_inventory = rooms[
        rooms["Specialist room type"].astype("string").str.strip().eq("General Teaching")
        & rooms["Id"].notna()
        & rooms["Campus"].notna()
    ].copy()
    room_inventory["Capacity"] = pd.to_numeric(room_inventory["Capacity"], errors="coerce")
    room_inventory = room_inventory.dropna(subset=["Capacity"])
    room_inventory["Capacity"] = room_inventory["Capacity"].astype(int)
    room_inventory["Id"] = room_inventory["Id"].astype("string").str.strip()

    room_inventory = (
        room_inventory[["Id", "Campus", "Capacity"]]
        .drop_duplicates(subset=["Id"])
        .rename(columns={"Id": "room_id", "Campus": "campus", "Capacity": "capacity"})
    )

    return events, gt_events, room_inventory


def load_programme_event_map():
    required_cols = ["Programme Code-Year", "Event ID"]
    stu = pd.read_excel(STUDENT_EVENT_FILE, usecols=lambda c: c in required_cols)
    stu = stu.rename(
        columns={
            "Programme Code-Year": "programme_code_year",
            "Event ID": "event_id",
        }
    )
    stu["programme_code_year"] = clean_id_series(stu["programme_code_year"])
    stu["event_id"] = clean_id_series(stu["event_id"])
    stu = stu[stu["programme_code_year"].notna() & stu["event_id"].notna()].copy()
    stu = stu.drop_duplicates(subset=["programme_code_year", "event_id"])
    return stu


def load_travel_constraints():
    travel = pd.read_excel(
        ROOMS_FILE,
        sheet_name="Room Constraints",
        usecols=["Campus From", "Campus To", "Travel time (mins)"],
    )
    travel = travel.rename(
        columns={
            "Campus From": "campus_from",
            "Campus To": "campus_to",
            "Travel time (mins)": "travel_time_mins",
        }
    )
    travel["campus_from"] = travel["campus_from"].map(normalize_campus)
    travel["campus_to"] = travel["campus_to"].map(normalize_campus)
    travel["travel_time_mins"] = pd.to_numeric(travel["travel_time_mins"], errors="coerce")
    travel = travel.dropna(subset=["campus_from", "campus_to", "travel_time_mins"]).copy()
    travel = travel.drop_duplicates(subset=["campus_from", "campus_to"])
    return travel


def build_base_travel_schedule(events):
    ev = events.copy()
    ev["event_id"] = clean_id_series(ev["event_id"])
    ev["campus"] = ev["campus"].map(normalize_campus)
    mask = (
        ev["is_travel_relevant"].fillna(False)
        & ev["event_id"].notna()
        & ev["day"].notna()
        & ev["start_min"].notna()
        & ev["end_min"].notna()
        & ev["campus"].notna()
    )
    base = ev.loc[mask, ["event_id", "day", "start_min", "end_min", "campus", "week_list"]].copy()
    base["week_list_parsed"] = base["week_list"].apply(parse_week_list)
    base["week_list_parsed"] = base["week_list_parsed"].apply(lambda x: x if x else [-1])
    base = base.drop_duplicates(subset=["event_id"])
    return base[["event_id", "day", "start_min", "end_min", "campus", "week_list_parsed"]]


def add_event_to_occupancy(occupancy, room_id, day, start_min, end_min, weeks, event_id):
    for week in weeks:
        key = (room_id, int(week), day)
        occupancy.setdefault(key, []).append((float(start_min), float(end_min), event_id))


def room_available(occupancy, room_id, day, start_min, end_min, weeks):
    for week in weeks:
        key = (room_id, int(week), day)
        for occ_start, occ_end, _ in occupancy.get(key, []):
            if intervals_overlap(start_min, end_min, occ_start, occ_end):
                return False
    return True


def run_allocation_scenario(
    gt_events,
    room_inventory,
    scenario_name,
    candidate_campuses,
    allow_time_shift=False,
    max_shift_minutes=0,
    allow_day_shift=False,
    max_day_shift_steps=0,
    reference_starts=None,
):
    if reference_starts is None:
        reference_starts = {}

    candidate_rooms = room_inventory[room_inventory["campus"].isin(candidate_campuses)].copy()
    candidate_rooms = candidate_rooms.sort_values(["capacity", "campus", "room_id"]).reset_index(drop=True)
    room_ids = set(candidate_rooms["room_id"])

    moved = gt_events[gt_events["campus"].eq("Holyrood")].copy()
    fixed = gt_events[
        gt_events["campus"].isin(candidate_campuses) & (~gt_events["campus"].eq("Holyrood"))
    ].copy()

    occupancy = {}
    fixed_in_inventory = fixed[fixed["room"].astype("string").isin(room_ids)].copy()
    for row in fixed_in_inventory.itertuples(index=False):
        add_event_to_occupancy(
            occupancy=occupancy,
            room_id=str(row.room),
            day=row.day,
            start_min=float(row.start_min),
            end_min=float(row.end_min),
            weeks=row.week_list_parsed,
            event_id=row.event_id,
        )

    moved["event_size"] = moved["event_size"].fillna(0)
    moved = moved.sort_values(
        ["event_size", "duration_minutes", "day_order", "start_min"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)

    assigned_rows = []
    for row in moved.itertuples(index=False):
        event_id = row.event_id
        original_day = row.day
        original_start_min = float(row.start_min)
        original_end_min = float(row.end_min)
        weeks = row.week_list_parsed
        event_size = float(row.event_size) if pd.notna(row.event_size) else 0.0
        duration = float(original_end_min - original_start_min)

        capable_rooms = candidate_rooms[candidate_rooms["capacity"] >= event_size]
        if capable_rooms.empty:
            assigned_rows.append(
                {
                    "scenario": scenario_name,
                    "event_id": event_id,
                    "event_name": row.event_name,
                    "module_id": row.module_id,
                    "day": original_day,
                    "start_min": original_start_min,
                    "end_min": original_end_min,
                    "original_day": original_day,
                    "assigned_day": np.nan,
                    "original_start_min": original_start_min,
                    "original_end_min": original_end_min,
                    "assigned_start_min": np.nan,
                    "assigned_end_min": np.nan,
                    "day_shift_steps": np.nan,
                    "shift_minutes": np.nan,
                    "is_time_shifted": False,
                    "is_day_shifted": False,
                    "is_shifted": False,
                    "event_size": event_size,
                    "weeks_count": len(weeks),
                    "assigned": False,
                    "assigned_room": np.nan,
                    "assigned_campus": np.nan,
                    "assigned_capacity": np.nan,
                    "capacity_margin": np.nan,
                    "unassigned_reason": "no_room_with_capacity",
                }
            )
            continue

        slot_candidates = build_candidate_slots(
            original_day=original_day,
            original_start=original_start_min,
            original_end=original_end_min,
            allow_time_shift=allow_time_shift,
            max_shift_minutes=max_shift_minutes,
            allow_day_shift=allow_day_shift,
            max_day_shift_steps=max_day_shift_steps,
            reference_starts=reference_starts,
        )

        selected_room = None
        selected_day = None
        selected_start = None
        selected_end = None
        selected_day_steps = None
        for day_candidate, start_candidate, end_candidate, day_steps, _ in slot_candidates:
            for room_row in capable_rooms.itertuples(index=False):
                room_id = str(room_row.room_id)
                if room_available(
                    occupancy=occupancy,
                    room_id=room_id,
                    day=day_candidate,
                    start_min=start_candidate,
                    end_min=end_candidate,
                    weeks=weeks,
                ):
                    selected_room = room_row
                    selected_day = day_candidate
                    selected_start = float(start_candidate)
                    selected_end = float(end_candidate)
                    selected_day_steps = int(day_steps)
                    break
            if selected_room is not None:
                break

        if selected_room is None:
            assigned_rows.append(
                {
                    "scenario": scenario_name,
                    "event_id": event_id,
                    "event_name": row.event_name,
                    "module_id": row.module_id,
                    "day": original_day,
                    "start_min": original_start_min,
                    "end_min": original_end_min,
                    "original_day": original_day,
                    "assigned_day": np.nan,
                    "original_start_min": original_start_min,
                    "original_end_min": original_end_min,
                    "assigned_start_min": np.nan,
                    "assigned_end_min": np.nan,
                    "day_shift_steps": np.nan,
                    "shift_minutes": np.nan,
                    "is_time_shifted": False,
                    "is_day_shifted": False,
                    "is_shifted": False,
                    "event_size": event_size,
                    "weeks_count": len(weeks),
                    "assigned": False,
                    "assigned_room": np.nan,
                    "assigned_campus": np.nan,
                    "assigned_capacity": np.nan,
                    "capacity_margin": np.nan,
                    "unassigned_reason": "timeslot_room_conflict",
                }
            )
            continue

        add_event_to_occupancy(
            occupancy=occupancy,
            room_id=str(selected_room.room_id),
            day=selected_day,
            start_min=selected_start,
            end_min=selected_end,
            weeks=weeks,
            event_id=event_id,
        )
        shift_minutes = float(selected_start - original_start_min)
        is_time_shifted = abs(shift_minutes) > 0
        is_day_shifted = selected_day != original_day
        assigned_rows.append(
            {
                "scenario": scenario_name,
                "event_id": event_id,
                "event_name": row.event_name,
                "module_id": row.module_id,
                "day": selected_day,
                "start_min": selected_start,
                "end_min": selected_end,
                "original_day": original_day,
                "assigned_day": selected_day,
                "original_start_min": original_start_min,
                "original_end_min": original_end_min,
                "assigned_start_min": selected_start,
                "assigned_end_min": selected_end,
                "day_shift_steps": selected_day_steps,
                "shift_minutes": shift_minutes,
                "is_time_shifted": is_time_shifted,
                "is_day_shifted": is_day_shifted,
                "is_shifted": bool(is_time_shifted or is_day_shifted),
                "event_size": event_size,
                "weeks_count": len(weeks),
                "assigned": True,
                "assigned_room": selected_room.room_id,
                "assigned_campus": selected_room.campus,
                "assigned_capacity": selected_room.capacity,
                "capacity_margin": selected_room.capacity - event_size,
                "unassigned_reason": "",
            }
        )

    assignment_df = pd.DataFrame(assigned_rows)

    # Build final event placement table (fixed + moved assigned only) for utilization metrics.
    fixed_final = fixed_in_inventory[["event_id", "day", "start_min", "end_min", "week_list_parsed", "room", "campus"]].copy()
    fixed_final = fixed_final.rename(columns={"room": "room_id"})
    fixed_final["scenario"] = scenario_name
    fixed_final["source"] = "fixed"

    moved_assigned = assignment_df[assignment_df["assigned"]].copy()
    moved_meta = moved[["event_id", "week_list_parsed"]].drop_duplicates("event_id")
    moved_assigned = moved_assigned.merge(moved_meta, on="event_id", how="left")
    moved_assigned = moved_assigned.rename(
        columns={
            "assigned_room": "room_id",
            "assigned_campus": "campus",
        }
    )
    moved_assigned = moved_assigned[["event_id", "day", "start_min", "end_min", "week_list_parsed", "room_id", "campus"]]
    moved_assigned["scenario"] = scenario_name
    moved_assigned["source"] = "moved_assigned"

    final_events = pd.concat([fixed_final, moved_assigned], ignore_index=True)
    final_events = final_events.dropna(subset=["room_id", "campus", "day", "start_min", "end_min"])

    # Expand to week-level rows for slot utilization.
    exploded = final_events.explode("week_list_parsed").rename(columns={"week_list_parsed": "week"})
    exploded["week"] = pd.to_numeric(exploded["week"], errors="coerce").fillna(-1).astype(int)
    exploded["room_id"] = exploded["room_id"].astype("string")

    if exploded.empty:
        slot_util = pd.DataFrame(
            columns=[
                "scenario",
                "campus",
                "week",
                "day",
                "start_min",
                "end_min",
                "events_in_slot",
                "rooms_used",
                "rooms_available",
                "slot_utilization_rate",
            ]
        )
    else:
        slot_util = (
            exploded.groupby(["scenario", "campus", "week", "day", "start_min", "end_min"], dropna=False)
            .agg(
                events_in_slot=("event_id", "count"),
                rooms_used=("room_id", "nunique"),
            )
            .reset_index()
        )
        room_count_by_campus = candidate_rooms.groupby("campus")["room_id"].nunique().to_dict()
        slot_util["rooms_available"] = slot_util["campus"].map(room_count_by_campus).fillna(0).astype(int)
        slot_util["slot_utilization_rate"] = np.where(
            slot_util["rooms_available"] > 0,
            slot_util["rooms_used"] / slot_util["rooms_available"],
            np.nan,
        )

    total_to_move = len(moved)
    assigned_count = int(assignment_df["assigned"].sum()) if not assignment_df.empty else 0
    unassigned_count = int(total_to_move - assigned_count)
    assigned_only = assignment_df[assignment_df["assigned"]].copy()
    time_shifted_assigned = assigned_only[assigned_only["is_time_shifted"].fillna(False)].copy()
    day_shifted_assigned = assigned_only[assigned_only["is_day_shifted"].fillna(False)].copy()
    shifted_assigned = assigned_only[assigned_only["is_shifted"].fillna(False)].copy()

    summary = {
        "scenario": scenario_name,
        "candidate_campuses": " | ".join(candidate_campuses),
        "allow_time_shift": bool(allow_time_shift),
        "max_shift_minutes": int(max_shift_minutes if allow_time_shift else 0),
        "allow_day_shift": bool(allow_day_shift),
        "max_day_shift_steps": int(max_day_shift_steps if allow_day_shift else 0),
        "candidate_rooms_total": int(len(candidate_rooms)),
        "candidate_rooms_central": int((candidate_rooms["campus"] == "Central").sum()),
        "candidate_rooms_lauriston": int((candidate_rooms["campus"] == "Lauriston").sum()),
        "candidate_rooms_new_college": int((candidate_rooms["campus"] == "New College").sum()),
        "holyrood_gt_events_to_move": int(total_to_move),
        "moved_events_assigned": int(assigned_count),
        "moved_events_unassigned": int(unassigned_count),
        "moved_assignment_rate_pct": round((assigned_count / total_to_move) * 100, 4) if total_to_move else 0.0,
        "unassigned_no_capacity": int((assignment_df["unassigned_reason"] == "no_room_with_capacity").sum()),
        "unassigned_timeslot_conflict": int((assignment_df["unassigned_reason"] == "timeslot_room_conflict").sum()),
        "assigned_to_central": int((assignment_df["assigned_campus"] == "Central").sum()),
        "assigned_to_lauriston": int((assignment_df["assigned_campus"] == "Lauriston").sum()),
        "assigned_to_new_college": int((assignment_df["assigned_campus"] == "New College").sum()),
        "moved_events_shifted": int(len(shifted_assigned)),
        "moved_shifted_rate_pct": round((len(shifted_assigned) / total_to_move) * 100, 4) if total_to_move else 0.0,
        "moved_events_time_shifted": int(len(time_shifted_assigned)),
        "moved_time_shifted_rate_pct": round((len(time_shifted_assigned) / total_to_move) * 100, 4) if total_to_move else 0.0,
        "moved_events_day_shifted": int(len(day_shifted_assigned)),
        "moved_day_shifted_rate_pct": round((len(day_shifted_assigned) / total_to_move) * 100, 4) if total_to_move else 0.0,
        "shifted_avg_abs_minutes": float(time_shifted_assigned["shift_minutes"].abs().mean()) if not time_shifted_assigned.empty else np.nan,
        "shifted_p95_abs_minutes": float(time_shifted_assigned["shift_minutes"].abs().quantile(0.95)) if not time_shifted_assigned.empty else np.nan,
        "day_shift_avg_steps": float(day_shifted_assigned["day_shift_steps"].mean()) if not day_shifted_assigned.empty else np.nan,
        "day_shift_p95_steps": float(day_shifted_assigned["day_shift_steps"].quantile(0.95)) if not day_shifted_assigned.empty else np.nan,
        "avg_capacity_margin_assigned": float(assigned_only["capacity_margin"].mean()) if not assigned_only.empty else np.nan,
        "median_capacity_margin_assigned": float(assigned_only["capacity_margin"].median()) if not assigned_only.empty else np.nan,
        "avg_fill_ratio_assigned": float((assigned_only["event_size"] / assigned_only["assigned_capacity"]).mean())
        if not assigned_only.empty
        else np.nan,
        "slot_utilization_avg": float(slot_util["slot_utilization_rate"].mean()) if not slot_util.empty else np.nan,
        "slot_utilization_p95": float(slot_util["slot_utilization_rate"].quantile(0.95)) if not slot_util.empty else np.nan,
        "high_pressure_slots_90pct_or_more": int((slot_util["slot_utilization_rate"] >= 0.9).sum()) if not slot_util.empty else 0,
    }

    return summary, assignment_df, slot_util


def evaluate_commute_for_scenario(
    scenario_name,
    assignment_df,
    base_travel_schedule,
    programme_event_map,
    travel_constraints,
    moved_event_ids,
):
    if base_travel_schedule.empty or programme_event_map.empty:
        summary = {
            "commute_programmes_covered": 0,
            "commute_schedule_rows": 0,
            "commute_adjacent_checks": 0,
            "commute_cross_campus_checks": 0,
            "commute_conflicts": 0,
            "commute_conflict_rate_pct": 0.0,
            "commute_move_related_checks": 0,
            "commute_move_related_conflicts": 0,
            "commute_move_related_conflict_rate_pct": 0.0,
            "commute_programmes_with_conflicts": 0,
        }
        return summary, pd.DataFrame()

    schedule = base_travel_schedule.copy()
    schedule["event_id"] = clean_id_series(schedule["event_id"])

    moved_assigned = assignment_df[assignment_df["assigned"]].copy()
    moved_assigned["event_id"] = clean_id_series(moved_assigned["event_id"])
    moved_assigned = moved_assigned[
        ["event_id", "day", "start_min", "end_min", "assigned_campus"]
    ].rename(columns={"assigned_campus": "campus"})

    moved_unassigned_ids = set(
        clean_id_series(assignment_df.loc[~assignment_df["assigned"], "event_id"]).dropna()
    )

    if not moved_assigned.empty:
        schedule = schedule.merge(
            moved_assigned.rename(
                columns={
                    "day": "ov_day",
                    "start_min": "ov_start_min",
                    "end_min": "ov_end_min",
                    "campus": "ov_campus",
                }
            ),
            on="event_id",
            how="left",
        )
        schedule["day"] = np.where(schedule["ov_day"].notna(), schedule["ov_day"], schedule["day"])
        schedule["start_min"] = np.where(
            schedule["ov_start_min"].notna(), schedule["ov_start_min"], schedule["start_min"]
        )
        schedule["end_min"] = np.where(
            schedule["ov_end_min"].notna(), schedule["ov_end_min"], schedule["end_min"]
        )
        schedule["campus"] = np.where(
            schedule["ov_campus"].notna(), schedule["ov_campus"], schedule["campus"]
        )
        schedule = schedule.drop(columns=["ov_day", "ov_start_min", "ov_end_min", "ov_campus"])

    if moved_unassigned_ids:
        schedule = schedule[~schedule["event_id"].isin(moved_unassigned_ids)].copy()

    sched = programme_event_map.merge(
        schedule[["event_id", "day", "start_min", "end_min", "campus", "week_list_parsed"]],
        on="event_id",
        how="inner",
    )
    if sched.empty:
        summary = {
            "commute_programmes_covered": int(programme_event_map["programme_code_year"].nunique()),
            "commute_schedule_rows": 0,
            "commute_adjacent_checks": 0,
            "commute_cross_campus_checks": 0,
            "commute_conflicts": 0,
            "commute_conflict_rate_pct": 0.0,
            "commute_move_related_checks": 0,
            "commute_move_related_conflicts": 0,
            "commute_move_related_conflict_rate_pct": 0.0,
            "commute_programmes_with_conflicts": 0,
        }
        return summary, pd.DataFrame()

    sched = sched.explode("week_list_parsed").rename(columns={"week_list_parsed": "week"})
    sched["week"] = pd.to_numeric(sched["week"], errors="coerce").fillna(-1).astype(int)
    sched = sched.sort_values(["programme_code_year", "week", "day", "start_min", "end_min", "event_id"])

    group_cols = ["programme_code_year", "week", "day"]
    sched["next_event_id"] = sched.groupby(group_cols)["event_id"].shift(-1)
    sched["next_start_min"] = sched.groupby(group_cols)["start_min"].shift(-1)
    sched["next_end_min"] = sched.groupby(group_cols)["end_min"].shift(-1)
    sched["next_campus"] = sched.groupby(group_cols)["campus"].shift(-1)

    checks = sched[sched["next_event_id"].notna()].copy()
    if checks.empty:
        summary = {
            "commute_programmes_covered": int(programme_event_map["programme_code_year"].nunique()),
            "commute_schedule_rows": int(len(sched)),
            "commute_adjacent_checks": 0,
            "commute_cross_campus_checks": 0,
            "commute_conflicts": 0,
            "commute_conflict_rate_pct": 0.0,
            "commute_move_related_checks": 0,
            "commute_move_related_conflicts": 0,
            "commute_move_related_conflict_rate_pct": 0.0,
            "commute_programmes_with_conflicts": 0,
        }
        return summary, pd.DataFrame()

    checks["gap_minutes"] = checks["next_start_min"] - checks["end_min"]
    checks["cross_campus"] = (
        checks["campus"].notna()
        & checks["next_campus"].notna()
        & (checks["campus"] != checks["next_campus"])
    )
    checks = checks.rename(columns={"campus": "campus_from", "next_campus": "campus_to"})
    checks = checks.merge(travel_constraints, on=["campus_from", "campus_to"], how="left")
    checks["travel_conflict"] = (
        checks["cross_campus"]
        & checks["travel_time_mins"].notna()
        & checks["gap_minutes"].notna()
        & (checks["travel_time_mins"] > checks["gap_minutes"])
    )
    checks["move_related"] = (
        checks["event_id"].isin(moved_event_ids)
        | checks["next_event_id"].isin(moved_event_ids)
    )

    conflicts = checks[checks["travel_conflict"]].copy()
    move_related_checks = checks[checks["move_related"]].copy()
    move_related_conflicts = checks[checks["travel_conflict"] & checks["move_related"]].copy()

    summary = {
        "commute_programmes_covered": int(programme_event_map["programme_code_year"].nunique()),
        "commute_schedule_rows": int(len(sched)),
        "commute_adjacent_checks": int(len(checks)),
        "commute_cross_campus_checks": int(checks["cross_campus"].sum()),
        "commute_conflicts": int(len(conflicts)),
        "commute_conflict_rate_pct": safe_pct(len(conflicts), len(checks)),
        "commute_move_related_checks": int(len(move_related_checks)),
        "commute_move_related_conflicts": int(len(move_related_conflicts)),
        "commute_move_related_conflict_rate_pct": safe_pct(
            len(move_related_conflicts), len(move_related_checks)
        ),
        "commute_programmes_with_conflicts": int(conflicts["programme_code_year"].nunique()),
    }

    keep_cols = [
        "programme_code_year",
        "week",
        "day",
        "event_id",
        "next_event_id",
        "campus_from",
        "campus_to",
        "end_min",
        "next_start_min",
        "gap_minutes",
        "travel_time_mins",
        "move_related",
    ]
    conflicts = conflicts[keep_cols].copy()
    conflicts["scenario"] = scenario_name
    return summary, conflicts


def main():
    print("Loading cleaned events and room inventory...")
    events_all, gt_events, room_inventory = load_inputs()
    reference_starts = build_reference_starts(gt_events)

    print("Loading programme-event mapping and travel constraints for commute checks...")
    programme_event_map = load_programme_event_map()
    travel_constraints = load_travel_constraints()
    base_travel_schedule = build_base_travel_schedule(events_all)

    moved_event_ids = set(
        clean_id_series(gt_events.loc[gt_events["campus"] == "Holyrood", "event_id"]).dropna()
    )
    affected_programmes = set(
        programme_event_map.loc[
            programme_event_map["event_id"].isin(moved_event_ids), "programme_code_year"
        ]
    )
    programme_event_map = programme_event_map[
        programme_event_map["programme_code_year"].isin(affected_programmes)
    ].copy()
    used_event_ids = set(programme_event_map["event_id"])
    base_travel_schedule = base_travel_schedule[
        base_travel_schedule["event_id"].isin(used_event_ids)
    ].copy()
    print(
        f"Commute scope: {len(affected_programmes):,} programmes, "
        f"{len(base_travel_schedule):,} travel-relevant events."
    )

    scenarios = [
        ("central_only", ["Central"], False, 0, False, 0),
        ("central_plus_lauriston", ["Central", "Lauriston"], False, 0, False, 0),
        ("central_plus_new_college", ["Central", "New College"], False, 0, False, 0),
        ("central_plus_both", ["Central", "Lauriston", "New College"], False, 0, False, 0),
        ("central_plus_both_shift60", ["Central", "Lauriston", "New College"], True, 60, False, 0),
        ("central_plus_both_shift120", ["Central", "Lauriston", "New College"], True, 120, False, 0),
        ("central_plus_both_shift60_crossday", ["Central", "Lauriston", "New College"], True, 60, True, 4),
        ("central_plus_both_shift120_crossday", ["Central", "Lauriston", "New College"], True, 120, True, 4),
    ]

    all_summaries = []
    all_assignments = []
    all_slots = []
    all_commute_conflicts = []

    for scenario_name, campuses, allow_shift, max_shift, allow_day, max_day_steps in scenarios:
        print(f"Running allocation scenario: {scenario_name}")
        summary, assignment_df, slot_util = run_allocation_scenario(
            gt_events=gt_events,
            room_inventory=room_inventory,
            scenario_name=scenario_name,
            candidate_campuses=campuses,
            allow_time_shift=allow_shift,
            max_shift_minutes=max_shift,
            allow_day_shift=allow_day,
            max_day_shift_steps=max_day_steps,
            reference_starts=reference_starts,
        )
        commute_summary, commute_conflicts = evaluate_commute_for_scenario(
            scenario_name=scenario_name,
            assignment_df=assignment_df,
            base_travel_schedule=base_travel_schedule,
            programme_event_map=programme_event_map,
            travel_constraints=travel_constraints,
            moved_event_ids=moved_event_ids,
        )
        summary.update(commute_summary)
        all_summaries.append(summary)
        all_assignments.append(assignment_df)
        all_slots.append(slot_util)
        all_commute_conflicts.append(commute_conflicts)

    summary_df = pd.DataFrame(all_summaries).sort_values("moved_events_unassigned")
    summary_df["commute_conflicts"] = pd.to_numeric(
        summary_df["commute_conflicts"], errors="coerce"
    ).fillna(0).astype(int)
    summary_df["commute_move_related_conflicts"] = pd.to_numeric(
        summary_df["commute_move_related_conflicts"], errors="coerce"
    ).fillna(0).astype(int)
    summary_ranked = summary_df.sort_values(
        [
            "moved_events_unassigned",
            "commute_move_related_conflicts",
            "commute_conflicts",
            "moved_events_shifted",
            "moved_events_day_shifted",
            "moved_events_time_shifted",
            "shifted_avg_abs_minutes",
        ],
        ascending=[True, True, True, True, True, True, True],
    ).reset_index(drop=True)
    assignments_df = pd.concat(all_assignments, ignore_index=True)
    slots_df = pd.concat(all_slots, ignore_index=True)
    commute_conflicts_df = pd.concat(all_commute_conflicts, ignore_index=True)

    summary_path = OUTDIR / "scenario1_space_summary.csv"
    assignments_path = OUTDIR / "scenario1_space_assignment_detail.csv"
    unassigned_path = OUTDIR / "scenario1_space_unassigned_events.csv"
    slot_util_path = OUTDIR / "scenario1_space_slot_utilization.csv"
    campus_slot_summary_path = OUTDIR / "scenario1_space_campus_slot_summary.csv"
    unassigned_hotspots_path = OUTDIR / "scenario1_space_unassigned_hotspots.csv"
    top_pressure_path = OUTDIR / "scenario1_space_top_pressure_slots.csv"
    shift_effect_path = OUTDIR / "scenario1_space_shift_effects.csv"
    shifted_assignments_path = OUTDIR / "scenario1_space_shifted_assignments.csv"
    commute_conflicts_path = OUTDIR / "scenario1_space_commute_conflicts.csv"
    commute_hotspots_path = OUTDIR / "scenario1_space_commute_hotspots.csv"
    decision_path = OUTDIR / "scenario1_space_decision.json"

    summary_df.to_csv(summary_path, index=False)
    assignments_df.to_csv(assignments_path, index=False)
    assignments_df[~assignments_df["assigned"]].to_csv(unassigned_path, index=False)
    slots_df.to_csv(slot_util_path, index=False)
    commute_conflicts_df.to_csv(commute_conflicts_path, index=False)

    campus_slot_summary = (
        slots_df.groupby(["scenario", "campus"], dropna=False)["slot_utilization_rate"]
        .agg(["mean", "median", "max"])
        .reset_index()
        .rename(columns={"mean": "slot_util_mean", "median": "slot_util_median", "max": "slot_util_max"})
    )
    campus_slot_summary.to_csv(campus_slot_summary_path, index=False)

    unassigned_hotspots = (
        assignments_df[~assignments_df["assigned"]]
        .groupby(["scenario", "original_day", "original_start_min", "original_end_min"], dropna=False)
        .size()
        .reset_index(name="unassigned_events")
        .sort_values(["scenario", "unassigned_events"], ascending=[True, False])
        .rename(
            columns={
                "original_day": "day",
                "original_start_min": "start_min",
                "original_end_min": "end_min",
            }
        )
    )
    unassigned_hotspots.to_csv(unassigned_hotspots_path, index=False)

    top_pressure = (
        slots_df.sort_values(["scenario", "slot_utilization_rate"], ascending=[True, False])
        .groupby("scenario", as_index=False)
        .head(100)
    )
    top_pressure.to_csv(top_pressure_path, index=False)

    shift_effect = summary_df[
        summary_df["scenario"].isin(
            [
                "central_plus_both",
                "central_plus_both_shift60",
                "central_plus_both_shift120",
                "central_plus_both_shift60_crossday",
                "central_plus_both_shift120_crossday",
            ]
        )
    ].copy()
    shift_effect.to_csv(shift_effect_path, index=False)

    shifted_assignments = assignments_df[
        assignments_df["assigned"] & assignments_df["is_shifted"].fillna(False)
    ].copy()
    shifted_assignments.to_csv(shifted_assignments_path, index=False)

    if not commute_conflicts_df.empty:
        commute_hotspots = (
            commute_conflicts_df.groupby(
                ["scenario", "day", "campus_from", "campus_to"], dropna=False
            )
            .size()
            .reset_index(name="conflict_count")
            .sort_values(["scenario", "conflict_count"], ascending=[True, False])
        )
    else:
        commute_hotspots = pd.DataFrame(
            columns=["scenario", "day", "campus_from", "campus_to", "conflict_count"]
        )
    commute_hotspots.to_csv(commute_hotspots_path, index=False)

    central_only_unassigned = int(
        summary_df.loc[summary_df["scenario"] == "central_only", "moved_events_unassigned"].iloc[0]
    )
    central_plus_both_unassigned = int(
        summary_df.loc[summary_df["scenario"] == "central_plus_both", "moved_events_unassigned"].iloc[0]
    )
    central_plus_both_shift60_unassigned = int(
        summary_df.loc[summary_df["scenario"] == "central_plus_both_shift60", "moved_events_unassigned"].iloc[0]
    )
    central_plus_both_shift120_unassigned = int(
        summary_df.loc[summary_df["scenario"] == "central_plus_both_shift120", "moved_events_unassigned"].iloc[0]
    )
    central_plus_both_shift60_crossday_unassigned = int(
        summary_df.loc[summary_df["scenario"] == "central_plus_both_shift60_crossday", "moved_events_unassigned"].iloc[0]
    )
    central_plus_both_shift120_crossday_unassigned = int(
        summary_df.loc[summary_df["scenario"] == "central_plus_both_shift120_crossday", "moved_events_unassigned"].iloc[0]
    )
    central_only_move_related_commute_conflicts = int(
        summary_df.loc[
            summary_df["scenario"] == "central_only", "commute_move_related_conflicts"
        ].iloc[0]
    )
    best_min_adjust_row = summary_ranked.iloc[0]
    need_extra_campuses = central_only_unassigned > 0
    both_resolves_all = central_plus_both_unassigned == 0

    decision = {
        "question": "If Holyrood General Teaching rooms close, do we need Lauriston/New College?",
        "need_extra_campuses_beyond_central": bool(need_extra_campuses),
        "central_only_unassigned_events": central_only_unassigned,
        "central_plus_both_unassigned_events": central_plus_both_unassigned,
        "central_plus_both_shift60_unassigned_events": central_plus_both_shift60_unassigned,
        "central_plus_both_shift120_unassigned_events": central_plus_both_shift120_unassigned,
        "central_plus_both_shift60_crossday_unassigned_events": central_plus_both_shift60_crossday_unassigned,
        "central_plus_both_shift120_crossday_unassigned_events": central_plus_both_shift120_crossday_unassigned,
        "additional_events_placed_with_shift60": int(central_plus_both_unassigned - central_plus_both_shift60_unassigned),
        "additional_events_placed_with_shift120": int(central_plus_both_unassigned - central_plus_both_shift120_unassigned),
        "additional_events_placed_with_shift60_crossday": int(
            central_plus_both_unassigned - central_plus_both_shift60_crossday_unassigned
        ),
        "additional_events_placed_with_shift120_crossday": int(
            central_plus_both_unassigned - central_plus_both_shift120_crossday_unassigned
        ),
        "central_plus_both_resolves_all": bool(both_resolves_all),
        "commute_scope_programmes": int(len(affected_programmes)),
        "central_only_move_related_commute_conflicts": central_only_move_related_commute_conflicts,
        "best_scenario_by_unassigned": summary_df.iloc[0]["scenario"],
        "best_scenario_min_adjustment": best_min_adjust_row["scenario"],
        "best_scenario_min_adjustment_shifted_events": int(best_min_adjust_row["moved_events_shifted"]),
        "best_scenario_min_adjustment_day_shifted_events": int(best_min_adjust_row["moved_events_day_shifted"]),
        "best_scenario_min_adjustment_time_shifted_events": int(best_min_adjust_row["moved_events_time_shifted"]),
        "best_scenario_min_adjustment_commute_conflicts": int(best_min_adjust_row["commute_conflicts"]),
        "best_scenario_min_adjustment_move_related_commute_conflicts": int(
            best_min_adjust_row["commute_move_related_conflicts"]
        ),
    }
    with decision_path.open("w", encoding="utf-8") as fh:
        json.dump(decision, fh, indent=2, ensure_ascii=False)

    print("\nScenario summary:")
    print(summary_df.to_string(index=False))
    print("\nDecision:")
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    print(f"\nSaved files in: {OUTDIR.resolve()}")


if __name__ == "__main__":
    main()
