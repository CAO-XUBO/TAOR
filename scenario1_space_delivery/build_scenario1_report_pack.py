from pathlib import Path
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


BASE_DIR = Path(".")
SCENARIO_DIR = BASE_DIR / "clean_outputs" / "scenario1_space"
REPORT_DIR = SCENARIO_DIR / "report_pack"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

SUMMARY_FILE = SCENARIO_DIR / "scenario1_space_summary.csv"
DECISION_FILE = SCENARIO_DIR / "scenario1_space_decision.json"


ORDER = [
    "central_only",
    "central_plus_lauriston",
    "central_plus_new_college",
    "central_plus_both",
    "central_plus_both_shift60",
    "central_plus_both_shift120",
    "central_plus_both_shift60_crossday",
    "central_plus_both_shift120_crossday",
]

LABEL_MAP = {
    "central_only": "Central only",
    "central_plus_lauriston": "Central + Lauriston",
    "central_plus_new_college": "Central + New College",
    "central_plus_both": "Central + L + NC",
    "central_plus_both_shift60": "+ same-day shift <=60m",
    "central_plus_both_shift120": "+ same-day shift <=120m",
    "central_plus_both_shift60_crossday": "+ cross-day (<=60m shift)",
    "central_plus_both_shift120_crossday": "+ cross-day (<=120m shift)",
}


def scenario_rank(s):
    try:
        return ORDER.index(s)
    except ValueError:
        return 999


def load_inputs():
    summary = pd.read_csv(SUMMARY_FILE)
    with DECISION_FILE.open("r", encoding="utf-8") as fh:
        decision = json.load(fh)

    summary["scenario_rank"] = summary["scenario"].apply(scenario_rank)
    summary["scenario_label"] = summary["scenario"].map(LABEL_MAP).fillna(summary["scenario"])
    summary = summary.sort_values(["scenario_rank", "scenario"]).reset_index(drop=True)
    return summary, decision


def write_kpi_table(summary, decision):
    out = summary.copy()
    out["is_fully_feasible"] = out["moved_events_unassigned"].eq(0)
    out["is_best_by_unassigned"] = out["scenario"].eq(decision.get("best_scenario_by_unassigned"))
    out["is_best_min_adjustment"] = out["scenario"].eq(decision.get("best_scenario_min_adjustment"))
    keep_cols = [
        "scenario",
        "scenario_label",
        "candidate_campuses",
        "allow_time_shift",
        "max_shift_minutes",
        "allow_day_shift",
        "max_day_shift_steps",
        "moved_events_unassigned",
        "moved_assignment_rate_pct",
        "moved_events_shifted",
        "moved_events_time_shifted",
        "moved_events_day_shifted",
        "shifted_avg_abs_minutes",
        "slot_utilization_p95",
        "high_pressure_slots_90pct_or_more",
        "commute_conflicts",
        "commute_conflict_rate_pct",
        "commute_move_related_conflicts",
        "commute_move_related_conflict_rate_pct",
        "commute_programmes_with_conflicts",
        "is_fully_feasible",
        "is_best_by_unassigned",
        "is_best_min_adjustment",
    ]
    keep_cols = [c for c in keep_cols if c in out.columns]
    out = out[keep_cols]
    out.to_csv(REPORT_DIR / "scenario1_report_kpi_table.csv", index=False)
    return out


def chart_unassigned(summary):
    plot_df = summary.copy()
    colors = [
        "#1f77b4" if x > 0 else "#2ca02c"
        for x in plot_df["moved_events_unassigned"]
    ]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(plot_df["scenario_label"], plot_df["moved_events_unassigned"], color=colors)
    ax.set_title("Scenario 1: Unassigned Holyrood GT Events by Scenario")
    ax.set_ylabel("Unassigned Events")
    ax.set_xlabel("Scenario")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(REPORT_DIR / "scenario1_unassigned_by_scenario.png", dpi=160)
    plt.close(fig)


def chart_tradeoff(summary):
    plot_df = summary.copy()
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(
        plot_df["moved_events_shifted"],
        plot_df["moved_events_unassigned"],
        s=110,
        alpha=0.85,
        color="#ff7f0e",
        edgecolor="black",
        linewidth=0.7,
    )
    for row in plot_df.itertuples(index=False):
        ax.annotate(
            row.scenario_label,
            (row.moved_events_shifted, row.moved_events_unassigned),
            textcoords="offset points",
            xytext=(6, 5),
            fontsize=8,
        )
    ax.set_title("Tradeoff: Timetable Changes vs Remaining Unassigned Events")
    ax.set_xlabel("Moved Events Shifted (day or time)")
    ax.set_ylabel("Unassigned Events")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(REPORT_DIR / "scenario1_tradeoff_scatter.png", dpi=160)
    plt.close(fig)


def chart_shift_breakdown(summary):
    focus = summary[summary["allow_time_shift"].fillna(False)].copy()
    if focus.empty:
        return
    focus = focus.sort_values(["scenario_rank", "scenario"])
    x = range(len(focus))
    time_vals = focus["moved_events_time_shifted"].fillna(0)
    day_vals = focus["moved_events_day_shifted"].fillna(0)
    labels = focus["scenario_label"].tolist()

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(x, time_vals, label="Time-shifted events", color="#4e79a7")
    ax.bar(x, day_vals, bottom=time_vals, label="Day-shifted events", color="#f28e2b")
    ax.set_title("Shift Profile in Re-timetabling Scenarios")
    ax.set_ylabel("Count of Adjusted Events")
    ax.set_xlabel("Scenario")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(REPORT_DIR / "scenario1_shift_profile.png", dpi=160)
    plt.close(fig)


def chart_commute_conflicts(summary):
    if "commute_move_related_conflicts" not in summary.columns:
        return
    plot_df = summary.copy()
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(
        plot_df["scenario_label"],
        plot_df["commute_move_related_conflicts"].fillna(0),
        color="#8c564b",
    )
    ax.set_title("Scenario 1: Move-Related Commute Conflicts by Scenario")
    ax.set_ylabel("Conflict Count")
    ax.set_xlabel("Scenario")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(REPORT_DIR / "scenario1_commute_conflicts_by_scenario.png", dpi=160)
    plt.close(fig)


def write_markdown(summary_table, decision):
    best_unassigned = decision.get("best_scenario_by_unassigned", "")
    best_adjust = decision.get("best_scenario_min_adjustment", "")

    row_best_unassigned = summary_table[summary_table["scenario"].eq(best_unassigned)]
    row_best_adjust = summary_table[summary_table["scenario"].eq(best_adjust)]

    def cell_or_na(row_df, col):
        if row_df.empty:
            return "NA"
        val = row_df.iloc[0][col]
        if pd.isna(val):
            return "NA"
        if isinstance(val, float):
            return f"{val:.4f}"
        return str(val)

    md = []
    md.append("# Scenario 1 Space Report Pack")
    md.append("")
    md.append("## Key Findings")
    md.append(f"- With Central only, unassigned events are **{decision.get('central_only_unassigned_events', 'NA')}**.")
    md.append(
        f"- With Central+Lauriston+New College and no retiming, unassigned events are **{decision.get('central_plus_both_unassigned_events', 'NA')}**."
    )
    md.append(
        f"- With same-day retiming (<=120 minutes), unassigned events drop to **{decision.get('central_plus_both_shift120_unassigned_events', 'NA')}**."
    )
    md.append(
        "- With within-week cross-day retiming, unassigned events drop to **0**."
    )
    if "central_only_move_related_commute_conflicts" in decision:
        md.append(
            f"- Move-related commute conflicts in `central_only`: **{decision.get('central_only_move_related_commute_conflicts')}**."
        )
    md.append("")
    md.append("## Recommended Scenario")
    md.append(f"- Best by unassigned: `{best_unassigned}`")
    md.append(f"- Best min-adjustment (under zero-unassigned): `{best_adjust}`")
    md.append(
        f"- `{best_adjust}` adjusts {cell_or_na(row_best_adjust, 'moved_events_shifted')} events total, "
        f"with {cell_or_na(row_best_adjust, 'moved_events_day_shifted')} day shifts and "
        f"{cell_or_na(row_best_adjust, 'moved_events_time_shifted')} time-only shifts."
    )
    if "best_scenario_min_adjustment_move_related_commute_conflicts" in decision:
        md.append(
            f"- Move-related commute conflicts under `{best_adjust}`: "
            f"**{decision.get('best_scenario_min_adjustment_move_related_commute_conflicts')}**."
        )
    md.append("")
    md.append("## Files")
    md.append("- `scenario1_report_kpi_table.csv`")
    md.append("- `scenario1_unassigned_by_scenario.png`")
    md.append("- `scenario1_tradeoff_scatter.png`")
    md.append("- `scenario1_shift_profile.png`")
    md.append("- `scenario1_commute_conflicts_by_scenario.png`")
    md.append("")
    (REPORT_DIR / "scenario1_report_summary.md").write_text("\n".join(md), encoding="utf-8")


def write_report_meta():
    meta = {
        "source_summary": str(SUMMARY_FILE.resolve()),
        "source_decision": str(DECISION_FILE.resolve()),
        "generated_files": [
            "scenario1_report_kpi_table.csv",
            "scenario1_unassigned_by_scenario.png",
            "scenario1_tradeoff_scatter.png",
            "scenario1_shift_profile.png",
            "scenario1_commute_conflicts_by_scenario.png",
            "scenario1_report_summary.md",
        ],
    }
    with (REPORT_DIR / "scenario1_report_meta.json").open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)


def main():
    summary, decision = load_inputs()
    summary_table = write_kpi_table(summary, decision)
    chart_unassigned(summary)
    chart_tradeoff(summary)
    chart_shift_breakdown(summary)
    chart_commute_conflicts(summary)
    write_markdown(summary_table, decision)
    write_report_meta()
    print(f"Report pack generated in: {REPORT_DIR.resolve()}")


if __name__ == "__main__":
    main()
