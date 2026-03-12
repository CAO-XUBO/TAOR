from pathlib import Path
import pandas as pd
import numpy as np
import re
import json
import hashlib
from datetime import datetime, timezone



BASE_DIR = Path(".")
EVENT_FILE = BASE_DIR / "2024-5 Event Module Room.xlsx"
STUDENT_EVENT_FILE = BASE_DIR / "2024-5 Student Programme Module Event.xlsx"
ROOM_FILE = BASE_DIR / "Rooms and Room Types.xlsx"
PROGRAMME_COURSE_FILE = BASE_DIR / "Programme-Course.xlsx"
DPT_FILE = BASE_DIR / "2024-5 DPT Data.xlsx"

OUTDIR = BASE_DIR / "clean_outputs"
OUTDIR.mkdir(exist_ok=True)

SESSION = "2024/5"
BASELINE_VERSION = "2026-03-12_baseline_v1"

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
NO_ROOM_REQUIRED_LABEL = "No room required"
MIN_REASONABLE_START_MIN = 8 * 60
MAX_REASONABLE_START_MIN = 20 * 60
MAX_REASONABLE_DURATION_MIN = 600

QUALITY_TARGETS = {
    "max_unmatched_rate_pct": 1.0,
    "max_unusual_start_events": 100,
    "max_extreme_duration_events": 100,
}

CAMPUS_MAP = {
    "bioquarter": "Bioquarter",
    "bio quarter": "Bioquarter",
    "central": "Central",
    "easter bush": "Easter Bush",
    "holyrood": "Holyrood",
    "kings buildings": "King's Buildings",
    "king's buildings": "King's Buildings",
    "lauriston": "Lauriston",
    "new college": "New College",
    "western general": "Western General",
}

BASELINE_RULES = {
    "session": SESSION,
    "day_order": DAY_ORDER,
    "no_room_required_label": NO_ROOM_REQUIRED_LABEL,
    "reasonable_start_minutes": {
        "min": MIN_REASONABLE_START_MIN,
        "max": MAX_REASONABLE_START_MIN,
    },
    "max_reasonable_duration_minutes": MAX_REASONABLE_DURATION_MIN,
    "travel_relevance_filter": [
        "is_in_person",
        "not is_no_room_required",
        "campus is not null",
        "start_min and end_min are not null",
        "not is_unusual_start_time",
        "not is_extreme_duration",
    ],
    "holyrood_general_teaching_move_rule": (
        "If campus == Holyrood and room_type_2 == General Teaching and in-person,"
        " then campus_after_move = Central"
    ),
    "event_matching_rule": (
        "Match event_id first; fallback to base_event_id only when a base_event_id"
        " maps to exactly one event_id in event master"
    ),
}



def norm_text(x):
    if pd.isna(x):
        return np.nan
    x = str(x).strip()
    x = re.sub(r"\s+", " ", x)
    return x


def snake(s):
    s = norm_text(s)
    s = s.lower().replace("/", "_").replace("-", "_")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def clean_columns(df):
    df = df.copy()
    df.columns = [snake(c) for c in df.columns]
    return df


def clean_id_series(s):
    return s.astype("string").str.strip().str.upper()


def base_event_id(s):
    return (
        s.astype("string")
         .str.strip()
         .str.upper()
         .str.replace(r"-\d{5}$", "", regex=True)
    )


def base_module_code(s):
    return (
        s.astype("string")
         .str.strip()
         .str.upper()
         .str.extract(r"^([A-Z0-9]+)", expand=False)
    )


def standardize_campus_series(s):
    s2 = s.astype("string").str.strip().str.lower()
    return s2.map(CAMPUS_MAP).fillna(s)


def parse_timeslot_series(s):
    days = []
    start_mins = []

    for val in s.fillna(""):
        val = str(val).strip()
        m = re.match(r"([A-Za-z]+)\s+(\d{1,2}):(\d{2})", val)
        if m:
            day = m.group(1).title()
            hh = int(m.group(2))
            mm = int(m.group(3))
            start_min = hh * 60 + mm
        else:
            day = np.nan
            start_min = np.nan

        days.append(day)
        start_mins.append(start_min)

    return pd.Series(days), pd.Series(start_mins, dtype="float")


def parse_weeks_cell(val):
    if pd.isna(val) or str(val).strip() == "":
        return []
    nums = re.findall(r"\d+", str(val))
    return [int(x) for x in nums]


def load_table(path, sheet_name=0, usecols=None):
    path = Path(path)
    if path.suffix.lower() in [".xlsx", ".xls"]:
        return pd.read_excel(path, sheet_name=sheet_name, usecols=usecols)
    elif path.suffix.lower() == ".csv":
        return pd.read_csv(path, usecols=usecols)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")


def safe_pct(num, den):
    if den == 0:
        return 0.0
    return round((num / den) * 100, 6)


def sha256_file(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def ts_to_utc_iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat()


def file_metadata(path, include_sha256=False):
    path = Path(path)
    if not path.exists():
        return {
            "exists": False,
            "path": str(path.resolve()),
        }

    stat = path.stat()
    meta = {
        "exists": True,
        "path": str(path.resolve()),
        "size_bytes": int(stat.st_size),
        "modified_utc": ts_to_utc_iso(stat.st_mtime),
    }
    if include_sha256:
        meta["sha256"] = sha256_file(path)
    return meta


def csv_output_metadata(path, row_count):
    meta = file_metadata(path, include_sha256=False)
    meta["rows"] = int(row_count)
    return meta


def minutes_to_hhmm(m):
    if pd.isna(m):
        return np.nan
    h = int(m // 60)
    mm = int(m % 60)
    return f"{h:02d}:{mm:02d}"


def clean_event_master(event_file):
    df = load_table(event_file, sheet_name="2024-5 Event Module Room")
    df = clean_columns(df)

    df["event_id"] = clean_id_series(df["event_id"])
    df["base_event_id"] = base_event_id(df["event_id"])

    df["module_id"] = clean_id_series(df["module_code"])
    df["base_module_code"] = base_module_code(df["module_id"])

    df["campus"] = standardize_campus_series(df["campus"])
    df["room"] = df["room"].astype("string").str.strip()
    df["semester"] = df["semester"].astype("string").str.strip()
    df["event_type"] = df["event_type"].astype("string").str.strip()
    df["room_type_1"] = df["room_type_1"].astype("string").str.strip()
    df["room_type_2"] = df["room_type_2"].astype("string").str.strip()
    df["online_delivery"] = df["online_delivery"].astype("string").str.strip()

    df["is_in_person"] = (
        df["online_delivery"].isna()
        | (df["online_delivery"] == "")
        | (~df["online_delivery"].str.lower().str.startswith("online"))
    )


    df["day"], df["start_min"] = parse_timeslot_series(df["timeslot"])
    df["duration_minutes"] = pd.to_numeric(df["duration_minutes"], errors="coerce")
    df["end_min"] = df["start_min"] + df["duration_minutes"]

    df["is_no_room_required"] = (
        df["room_type_2"].astype("string").str.strip().str.lower().eq(NO_ROOM_REQUIRED_LABEL.lower())
    )
    df["is_unusual_start_time"] = (
        df["start_min"].notna()
        & (
            (df["start_min"] < MIN_REASONABLE_START_MIN)
            | (df["start_min"] > MAX_REASONABLE_START_MIN)
        )
    )
    df["is_extreme_duration"] = (
        df["duration_minutes"].notna()
        & (df["duration_minutes"] > MAX_REASONABLE_DURATION_MIN)
    )

    # Events with no room/campus, unusual clock times, or extreme lengths are not travel-check candidates.
    df["is_travel_relevant"] = (
        df["is_in_person"]
        & (~df["is_no_room_required"].fillna(False))
        & df["campus"].notna()
        & df["start_min"].notna()
        & df["end_min"].notna()
        & (~df["is_unusual_start_time"].fillna(False))
        & (~df["is_extreme_duration"].fillna(False))
    )

    # week 列表
    df["week_list"] = df["weeks"].apply(parse_weeks_cell)


    df["is_displaced_holyrood_gt"] = (
        df["campus"].eq("Holyrood")
        & df["room_type_2"].eq("General Teaching")
        & df["is_in_person"]
    )


    keep_cols = [
        "event_id", "base_event_id",
        "module_id", "base_module_code",
        "module_name",
        "event_name", "event_type",
        "wholeclass",
        "duration_minutes",
        "event_size",
        "timeslot", "day", "start_min", "end_min",
        "number_of_weeks", "weeks", "week_list",
        "room", "building", "campus",
        "room_type_1", "room_type_2",
        "semester", "room_lock",
        "online_delivery", "is_in_person",
        "is_displaced_holyrood_gt",
        "is_no_room_required",
        "is_unusual_start_time",
        "is_extreme_duration",
        "is_travel_relevant",
    ]

    df = df[keep_cols].copy()


    df = df[df["event_id"].notna() & df["day"].notna() & df["is_in_person"]].copy()


    dedup_cols = [c for c in df.columns if c != "week_list"]
    df = df.drop_duplicates(subset=dedup_cols)

    return df



def clean_student_programme_event(student_event_file):

    required_cols = [
        "Programme",
        "Programme Code-Year",
        "Course Name",
        "Course ID",
        "Event ID",
        "Semester",
    ]

    df = load_table(student_event_file, usecols=lambda c: c in required_cols)
    df = clean_columns(df)

    rename_map = {
        "programme": "programme",
        "programme_code_year": "programme_code_year",
        "course_name": "course_name",
        "course_id": "module_id",
        "event_id": "event_id",
        "semester": "semester",
    }
    df = df.rename(columns=rename_map)


    df["programme"] = df["programme"].astype("string").str.strip()
    df["programme_code_year"] = clean_id_series(df["programme_code_year"])
    df["course_name"] = df["course_name"].astype("string").str.strip()
    df["module_id"] = clean_id_series(df["module_id"])
    df["base_module_code"] = base_module_code(df["module_id"])
    df["event_id"] = clean_id_series(df["event_id"])
    df["base_event_id"] = base_event_id(df["event_id"])
    df["semester"] = df["semester"].astype("string").str.strip()


    df = df[
        df["programme_code_year"].notna()
        & df["module_id"].notna()
        & df["event_id"].notna()
    ].copy()


    df = df.drop_duplicates(
        subset=["programme_code_year", "module_id", "event_id", "semester"]
    )

    return df



def clean_travel_constraints(room_file):

    df = load_table(room_file, sheet_name="Room Constraints")
    df = clean_columns(df)

    travel = df[["campus_from", "campus_to", "travel_time_mins"]].copy()
    travel = travel.dropna(subset=["campus_from", "campus_to", "travel_time_mins"])

    travel["campus_from"] = standardize_campus_series(travel["campus_from"])
    travel["campus_to"] = standardize_campus_series(travel["campus_to"])
    travel["travel_time_mins"] = pd.to_numeric(travel["travel_time_mins"], errors="coerce")

    travel = travel.dropna(subset=["travel_time_mins"]).drop_duplicates()

    return travel



def clean_programme_course(programme_course_file):
    df = load_table(programme_course_file, sheet_name="CourseModule")
    df = clean_columns(df)


    df["programme_code_year"] = clean_id_series(df["courseid"])
    df["module_id"] = clean_id_series(df["moduleid"])
    df["base_module_code"] = base_module_code(df["module_id"])
    df["compulsory_flag"] = df["compulsory"].astype("boolean")

    df = df[["programme_code_year", "module_id", "base_module_code", "compulsory_flag"]].drop_duplicates()
    return df



def clean_dpt(dpt_file):
    df = load_table(dpt_file)
    df = clean_columns(df)

    df["programme_code"] = clean_id_series(df["programme_code"])
    df["programme_year"] = pd.to_numeric(df["programme_year"], errors="coerce").astype("Int64")
    df["programme_code_year"] = (
        df["programme_code"].astype("string")
        + "_YR"
        + df["programme_year"].astype("string")
        + f"_{SESSION}"
    ).str.upper()

    df["base_module_code"] = base_module_code(df["course_code"])
    df["compulsory_optional"] = df["compulsory_optional"].astype("string").str.strip()


    priority_map = {"Compulsory": 2, "Optional": 1}
    df["priority"] = df["compulsory_optional"].map(priority_map).fillna(0)

    df = (
        df.sort_values("priority", ascending=False)
          .drop_duplicates(subset=["programme_code_year", "base_module_code"])
    )

    df = df[["programme_code_year", "base_module_code", "compulsory_optional"]]
    return df



def build_enriched_programme_event(student_map, events, programme_course=None, dpt=None):

    event_lookup_cols = [
        "event_id", "base_event_id",
        "module_id", "base_module_code",
        "event_name", "event_type", "wholeclass",
        "timeslot", "day", "start_min", "end_min",
        "duration_minutes",
        "week_list", "weeks",
        "campus", "room", "building",
        "room_type_1", "room_type_2",
        "semester",
        "is_displaced_holyrood_gt",
        "is_no_room_required",
        "is_unusual_start_time",
        "is_extreme_duration",
        "is_travel_relevant",
    ]

    event_exact = events[event_lookup_cols].drop_duplicates(subset=["event_id"]).copy()

    enriched = student_map.merge(
        event_exact,
        on="event_id",
        how="left",
        suffixes=("", "_evt")
    )
    enriched["_matched_exact_event_id"] = enriched["event_name"].notna()

    # Safe fallback: only use base_event_id when it maps to exactly one event_id in event master.
    base_counts = event_exact.groupby("base_event_id", dropna=False)["event_id"].nunique()
    unique_base_ids = set(base_counts[base_counts == 1].index)

    base_fallback = (
        event_exact[event_exact["base_event_id"].isin(unique_base_ids)]
        .drop_duplicates(subset=["base_event_id"])
        .drop(columns=["event_id"])
        .rename(columns=lambda c: f"fb_{c}" if c != "base_event_id" else c)
    )

    enriched = enriched.merge(base_fallback, on="base_event_id", how="left")

    overlap_cols = {"base_event_id", "module_id", "base_module_code", "semester"}
    for src_col in event_lookup_cols:
        if src_col in {"event_id", "base_event_id"}:
            continue
        target_col = f"{src_col}_evt" if src_col in overlap_cols else src_col
        source_col = f"fb_{src_col}"

        if target_col in enriched.columns and source_col in enriched.columns:
            fill_mask = enriched[target_col].isna() & enriched[source_col].notna()
            enriched.loc[fill_mask, target_col] = enriched.loc[fill_mask, source_col]

    fallback_cols = [c for c in enriched.columns if c.startswith("fb_")]
    if fallback_cols:
        enriched = enriched.drop(columns=fallback_cols)

    fallback_filled = (~enriched["_matched_exact_event_id"]) & enriched["event_name"].notna()
    enriched["event_match_method"] = np.select(
        [
            enriched["_matched_exact_event_id"],
            fallback_filled,
        ],
        [
            "event_id_exact",
            "base_event_id_fallback",
        ],
        default="unmatched",
    )
    enriched = enriched.drop(columns=["_matched_exact_event_id"])


    if "module_id_evt" in enriched.columns:
        enriched = enriched.rename(columns={"module_id_evt": "event_module_id"})


    if programme_course is not None:
        pc = programme_course[["programme_code_year", "module_id", "base_module_code", "compulsory_flag"]].copy()

        enriched = enriched.merge(
            pc[["programme_code_year", "module_id", "compulsory_flag"]],
            on=["programme_code_year", "module_id"],
            how="left"
        )

        if "compulsory_flag" in enriched.columns:
            enriched["compulsory_flag"] = enriched["compulsory_flag"].astype("boolean")


    if dpt is not None:
        enriched = enriched.merge(
            dpt,
            on=["programme_code_year", "base_module_code"],
            how="left"
        )


        if "compulsory_flag" not in enriched.columns:
            enriched["compulsory_flag"] = pd.Series(pd.NA, index=enriched.index, dtype="boolean")
        else:
            enriched["compulsory_flag"] = enriched["compulsory_flag"].astype("boolean")


        enriched["compulsory_optional"] = enriched["compulsory_optional"].astype("string").str.strip()


        mask_comp = enriched["compulsory_flag"].isna() & enriched["compulsory_optional"].eq("Compulsory")
        mask_opt  = enriched["compulsory_flag"].isna() & enriched["compulsory_optional"].eq("Optional")

        enriched.loc[mask_comp, "compulsory_flag"] = True
        enriched.loc[mask_opt,  "compulsory_flag"] = False


    enriched["campus_after_move"] = np.where(
        enriched["is_displaced_holyrood_gt"].fillna(False),
        "Central",
        enriched["campus"]
    )


    enriched["week_list"] = enriched["week_list"].apply(lambda x: x if isinstance(x, list) else [])
    enriched = enriched.explode("week_list").rename(columns={"week_list": "week"})
    enriched["week"] = pd.to_numeric(enriched["week"], errors="coerce").astype("Int64")


    day_rank = {d: i for i, d in enumerate(DAY_ORDER)}
    enriched["day_rank"] = enriched["day"].map(day_rank)


    if "semester_x" in enriched.columns and "semester_y" in enriched.columns:
        enriched["semester"] = enriched["semester_x"].fillna(enriched["semester_y"])
    elif "semester_x" in enriched.columns:
        enriched = enriched.rename(columns={"semester_x": "semester"})
    elif "semester_y" in enriched.columns:
        enriched = enriched.rename(columns={"semester_y": "semester"})

    enriched["is_travel_relevant"] = enriched["is_travel_relevant"].fillna(False)

    return enriched


def build_programme_day_summary(enriched):
    def sorted_unique_string(values):
        vals = sorted({v for v in values if pd.notna(v)})
        return " | ".join(vals)

    daily = (
        enriched.groupby(
            ["programme_code_year", "programme", "semester", "week", "day"],
            dropna=False
        )
        .agg(
            n_events=("event_id", "nunique"),
            campuses_before=("campus", sorted_unique_string),
            campuses_after=("campus_after_move", sorted_unique_string),
            has_holyrood_gt=("is_displaced_holyrood_gt", "any"),
        )
        .reset_index()
    )

    daily["multi_campus_before"] = daily["campuses_before"].str.contains(r"\|", regex=True, na=False)
    daily["multi_campus_after"] = daily["campuses_after"].str.contains(r"\|", regex=True, na=False)

    return daily


def build_adjacent_travel_checks(enriched, travel):
    travel_lookup = {
        (row["campus_from"], row["campus_to"]): row["travel_time_mins"]
        for _, row in travel.iterrows()
    }


    sched_src = enriched.copy()
    if "is_travel_relevant" in sched_src.columns:
        sched_src = sched_src[sched_src["is_travel_relevant"].fillna(False)].copy()

    sched = sched_src.drop_duplicates(
        subset=["programme_code_year", "event_id", "week", "day", "start_min", "end_min"]
    ).copy()

    group_cols = ["programme_code_year", "programme", "semester", "week", "day"]
    sched = sched.sort_values(group_cols + ["start_min", "end_min", "event_id"])


    cols_to_shift = [
        "event_id", "course_name", "module_id", "campus", "campus_after_move",
        "start_min", "end_min", "timeslot",
        "compulsory_flag", "is_displaced_holyrood_gt"
    ]
    for c in cols_to_shift:
        sched[f"next_{c}"] = sched.groupby(group_cols)[c].shift(-1)

    sched["gap_minutes"] = sched["next_start_min"] - sched["end_min"]

    def lookup_travel(row):
        key = (row["campus_after_move"], row["next_campus_after_move"])
        return travel_lookup.get(key, np.nan)

    sched["travel_minutes"] = sched.apply(lookup_travel, axis=1)

    sched["cross_campus_after_move"] = (
        sched["campus_after_move"].notna()
        & sched["next_campus_after_move"].notna()
        & (sched["campus_after_move"] != sched["next_campus_after_move"])
    )

    sched["travel_conflict"] = (
        sched["cross_campus_after_move"]
        & sched["gap_minutes"].notna()
        & sched["travel_minutes"].notna()
        & (sched["travel_minutes"] > sched["gap_minutes"])
    )

    sched["both_compulsory"] = (
        sched["compulsory_flag"].fillna(False)
        & sched["next_compulsory_flag"].fillna(False)
    )

    sched["severity_proxy"] = np.select(
        [
            sched["travel_conflict"] & sched["both_compulsory"],
            sched["travel_conflict"],
        ],
        [
            "high",
            "medium",
        ],
        default="low"
    )


    out = sched[sched["next_event_id"].notna()].copy()


    out["end_hhmm"] = out["end_min"].apply(minutes_to_hhmm)
    out["next_start_hhmm"] = out["next_start_min"].apply(minutes_to_hhmm)

    keep_cols = [
        "programme_code_year", "programme", "semester", "week", "day",
        "event_id", "course_name", "module_id", "campus", "campus_after_move",
        "timeslot", "end_hhmm",
        "next_event_id", "next_course_name", "next_module_id",
        "next_campus", "next_campus_after_move", "next_timeslot", "next_start_hhmm",
        "gap_minutes", "travel_minutes",
        "cross_campus_after_move", "travel_conflict",
        "compulsory_flag", "next_compulsory_flag",
        "both_compulsory", "severity_proxy",
        "is_displaced_holyrood_gt", "next_is_displaced_holyrood_gt"
    ]

    return out[keep_cols]


def build_baseline_metrics(events, student_map, enriched, daily, travel_checks, conflicts, affected_daily):
    events_rows = len(events)
    student_rows = len(student_map)
    enriched_rows = len(enriched)
    daily_rows = len(daily)
    travel_checks_rows = len(travel_checks)
    conflicts_rows = len(conflicts)

    unmatched_rows = int((enriched["event_match_method"] == "unmatched").sum())
    fallback_rows = int((enriched["event_match_method"] == "base_event_id_fallback").sum())
    exact_rows = int((enriched["event_match_method"] == "event_id_exact").sum())

    move_related_mask = (
        travel_checks["travel_conflict"].fillna(False)
        & (
            travel_checks["is_displaced_holyrood_gt"].fillna(False)
            | travel_checks["next_is_displaced_holyrood_gt"].fillna(False)
        )
    )
    move_related_rows = int(move_related_mask.sum())
    move_related_both_compulsory_rows = int(
        (move_related_mask & travel_checks["both_compulsory"].fillna(False)).sum()
    )

    multi_campus_before_rows = int(daily["multi_campus_before"].fillna(False).sum())
    multi_campus_after_rows = int(daily["multi_campus_after"].fillna(False).sum())

    metrics = {
        "events_clean_rows": int(events_rows),
        "events_clean_unique_event_id": int(events["event_id"].nunique()),
        "events_no_room_required_rows": int(events["is_no_room_required"].fillna(False).sum()),
        "events_unusual_start_rows": int(events["is_unusual_start_time"].fillna(False).sum()),
        "events_extreme_duration_rows": int(events["is_extreme_duration"].fillna(False).sum()),
        "events_travel_relevant_rows": int(events["is_travel_relevant"].fillna(False).sum()),
        "events_displaced_holyrood_gt_rows": int(events["is_displaced_holyrood_gt"].fillna(False).sum()),
        "programme_event_clean_rows": int(student_rows),
        "programme_event_clean_unique_programmes": int(student_map["programme_code_year"].nunique()),
        "programme_event_enriched_rows": int(enriched_rows),
        "match_exact_rows": exact_rows,
        "match_fallback_rows": fallback_rows,
        "match_unmatched_rows": unmatched_rows,
        "match_exact_rate_pct": safe_pct(exact_rows, enriched_rows),
        "match_fallback_rate_pct": safe_pct(fallback_rows, enriched_rows),
        "match_unmatched_rate_pct": safe_pct(unmatched_rows, enriched_rows),
        "affected_programmes_nunique": int(
            enriched.loc[
                enriched["is_displaced_holyrood_gt"].fillna(False),
                "programme_code_year",
            ].nunique()
        ),
        "programme_day_summary_rows": int(daily_rows),
        "affected_programme_days_rows": int(len(affected_daily)),
        "multi_campus_before_rows": multi_campus_before_rows,
        "multi_campus_after_rows": multi_campus_after_rows,
        "multi_campus_reduction_rows": int(multi_campus_before_rows - multi_campus_after_rows),
        "multi_campus_reduction_rate_pct": safe_pct(
            max(multi_campus_before_rows - multi_campus_after_rows, 0),
            multi_campus_before_rows,
        ),
        "programme_adjacent_travel_checks_rows": int(travel_checks_rows),
        "travel_conflicts_only_rows": int(conflicts_rows),
        "travel_conflict_rate_pct": safe_pct(conflicts_rows, travel_checks_rows),
        "travel_conflict_high_rows": int((travel_checks["severity_proxy"] == "high").sum()),
        "travel_conflict_medium_rows": int((travel_checks["severity_proxy"] == "medium").sum()),
        "travel_conflict_low_rows": int((travel_checks["severity_proxy"] == "low").sum()),
        "move_related_conflict_rows": move_related_rows,
        "move_related_both_compulsory_rows": move_related_both_compulsory_rows,
    }

    quality_checks = {
        "check_unmatched_rate_pass": (
            metrics["match_unmatched_rate_pct"] <= QUALITY_TARGETS["max_unmatched_rate_pct"]
        ),
        "check_unusual_start_count_pass": (
            metrics["events_unusual_start_rows"] <= QUALITY_TARGETS["max_unusual_start_events"]
        ),
        "check_extreme_duration_count_pass": (
            metrics["events_extreme_duration_rows"] <= QUALITY_TARGETS["max_extreme_duration_events"]
        ),
    }
    quality_checks["all_checks_pass"] = bool(all(quality_checks.values()))

    return metrics, quality_checks


def write_baseline_artifacts(outdir, run_started_utc, metrics, quality_checks):
    source_files = {
        "event_file": file_metadata(EVENT_FILE, include_sha256=True),
        "student_event_file": file_metadata(STUDENT_EVENT_FILE, include_sha256=True),
        "room_file": file_metadata(ROOM_FILE, include_sha256=True),
        "programme_course_file": file_metadata(PROGRAMME_COURSE_FILE, include_sha256=True),
        "dpt_file": file_metadata(DPT_FILE, include_sha256=True),
    }

    output_files = {
        "events_clean": csv_output_metadata(outdir / "events_clean.csv", metrics["events_clean_rows"]),
        "programme_event_clean": csv_output_metadata(
            outdir / "programme_event_clean.csv", metrics["programme_event_clean_rows"]
        ),
        "travel_constraints_clean": csv_output_metadata(
            outdir / "travel_constraints_clean.csv", metrics["travel_constraints_clean_rows"]
        ),
        "programme_course_clean": csv_output_metadata(
            outdir / "programme_course_clean.csv", metrics["programme_course_clean_rows"]
        ),
        "dpt_clean": csv_output_metadata(outdir / "dpt_clean.csv", metrics["dpt_clean_rows"]),
        "programme_event_enriched": csv_output_metadata(
            outdir / "programme_event_enriched.csv", metrics["programme_event_enriched_rows"]
        ),
        "programme_day_summary": csv_output_metadata(
            outdir / "programme_day_summary.csv", metrics["programme_day_summary_rows"]
        ),
        "programme_adjacent_travel_checks": csv_output_metadata(
            outdir / "programme_adjacent_travel_checks.csv",
            metrics["programme_adjacent_travel_checks_rows"],
        ),
        "affected_programme_days": csv_output_metadata(
            outdir / "affected_programme_days.csv", metrics["affected_programme_days_rows"]
        ),
        "travel_conflicts_only": csv_output_metadata(
            outdir / "travel_conflicts_only.csv", metrics["travel_conflicts_only_rows"]
        ),
    }

    manifest = {
        "baseline_version": BASELINE_VERSION,
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "run_started_utc": run_started_utc,
        "session": SESSION,
        "quality_targets": QUALITY_TARGETS,
        "rules": BASELINE_RULES,
        "source_files": source_files,
        "output_files": output_files,
        "metrics": metrics,
        "quality_checks": quality_checks,
    }

    manifest_path = outdir / "baseline_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    kpi_row = {}
    kpi_row.update(metrics)
    for k, v in QUALITY_TARGETS.items():
        kpi_row[f"target_{k}"] = v
    for k, v in quality_checks.items():
        kpi_row[k] = v
    pd.DataFrame([kpi_row]).to_csv(outdir / "baseline_kpi_snapshot.csv", index=False)

    return manifest_path


def main():
    run_started_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    print("Loading and cleaning event master...")
    events = clean_event_master(EVENT_FILE)
    events.to_csv(OUTDIR / "events_clean.csv", index=False)

    print("Loading and cleaning student-programme-event mapping...")
    student_map = clean_student_programme_event(STUDENT_EVENT_FILE)
    student_map.to_csv(OUTDIR / "programme_event_clean.csv", index=False)

    print("Loading and cleaning travel constraints...")
    travel = clean_travel_constraints(ROOM_FILE)
    travel.to_csv(OUTDIR / "travel_constraints_clean.csv", index=False)

    print("Loading programme-course map...")
    programme_course = clean_programme_course(PROGRAMME_COURSE_FILE)
    programme_course.to_csv(OUTDIR / "programme_course_clean.csv", index=False)

    print("Loading DPT fallback...")
    try:
        dpt = clean_dpt(DPT_FILE)
        dpt.to_csv(OUTDIR / "dpt_clean.csv", index=False)
    except Exception as e:
        print(f"[WARN] DPT fallback not loaded: {e}")
        dpt = None

    print("Building enriched programme-event table...")
    enriched = build_enriched_programme_event(
        student_map=student_map,
        events=events,
        programme_course=programme_course,
        dpt=dpt
    )
    print("\n[DEBUG] enriched columns:")
    print(enriched.columns.tolist())
    enriched.to_csv(OUTDIR / "programme_event_enriched.csv", index=False)

    print("Building programme-day summary...")
    daily = build_programme_day_summary(enriched)
    daily.to_csv(OUTDIR / "programme_day_summary.csv", index=False)

    print("Building adjacent travel checks...")
    travel_checks = build_adjacent_travel_checks(enriched, travel)
    travel_checks.to_csv(OUTDIR / "programme_adjacent_travel_checks.csv", index=False)


    affected_daily = daily[daily["has_holyrood_gt"]].copy()
    affected_daily.to_csv(OUTDIR / "affected_programme_days.csv", index=False)

    conflicts = travel_checks[travel_checks["travel_conflict"]].copy()
    conflicts.to_csv(OUTDIR / "travel_conflicts_only.csv", index=False)

    metrics, quality_checks = build_baseline_metrics(
        events=events,
        student_map=student_map,
        enriched=enriched,
        daily=daily,
        travel_checks=travel_checks,
        conflicts=conflicts,
        affected_daily=affected_daily,
    )
    metrics["travel_constraints_clean_rows"] = int(len(travel))
    metrics["programme_course_clean_rows"] = int(len(programme_course))
    metrics["dpt_clean_rows"] = int(len(dpt)) if dpt is not None else 0

    print("Writing baseline manifest and KPI snapshot...")
    manifest_path = write_baseline_artifacts(
        outdir=OUTDIR,
        run_started_utc=run_started_utc,
        metrics=metrics,
        quality_checks=quality_checks,
    )

    print("\nDone.")
    print(f"Outputs saved to: {OUTDIR.resolve()}")
    print(f"- baseline manifest: {manifest_path.resolve()}")
    print(f"- baseline KPI snapshot: {(OUTDIR / 'baseline_kpi_snapshot.csv').resolve()}")

    print("\nQuick sanity checks:")
    print(f"- events_clean rows: {len(events):,}")
    print(f"- programme_event_clean rows: {len(student_map):,}")
    print(f"- programme_event_enriched rows: {len(enriched):,}")
    print(f"- programme_day_summary rows: {len(daily):,}")
    print(f"- travel_conflicts_only rows: {len(conflicts):,}")
    print(f"- no-room-required events: {events['is_no_room_required'].sum():,}")
    print(f"- unusual-start-time events: {events['is_unusual_start_time'].sum():,}")
    print(f"- extreme-duration events: {events['is_extreme_duration'].sum():,}")
    print(f"- rows matched via base_event_id fallback: {(enriched['event_match_method'] == 'base_event_id_fallback').sum():,}")
    print(f"- rows still unmatched after fallback: {(enriched['event_match_method'] == 'unmatched').sum():,}")


if __name__ == "__main__":
    main()
