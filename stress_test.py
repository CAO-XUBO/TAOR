import argparse
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import allocator_heuristic as ah


def build_student_clash_dict(clash_df):
    clash_dict = {}
    for _, row in clash_df.iterrows():
        clash_dict[(row["Module_A"], row["Module_B"])] = row["Clash_Count"]
        clash_dict[(row["Module_B"], row["Module_A"])] = row["Clash_Count"]
    return clash_dict


def build_distance_dict(dist_df):
    distance_dict = {}
    for _, row in dist_df.iterrows():
        campus_from = row["Campus From"]
        for col in dist_df.columns:
            if col != "Campus From":
                distance_dict[(campus_from, col)] = float(row[col])
    return distance_dict


def build_scenario_dataframes(scenario):
    demand_holyrood = pd.read_csv("processed_data/2024-5_data_demand_General Teaching_Holyrood.csv")
    demand_central = pd.read_csv("processed_data/2024-5_data_demand_General Teaching_Central.csv")
    all_data = pd.read_csv("processed_data/2024-5_data_demand_General Teaching_All.csv")

    if scenario == "local":
        demand_df = demand_holyrood.copy()
        background_df = all_data[~all_data["Campus"].isin(["Holyrood"])].reset_index(drop=True)
    elif scenario == "global":
        demand_df = pd.concat([demand_holyrood, demand_central], ignore_index=True)
        background_df = all_data[~all_data["Event ID"].isin(demand_df["Event ID"])].reset_index(drop=True)
    else:
        raise ValueError(f"Unsupported scenario: {scenario}")

    demand_df = demand_df.sort_values(by=["Event Size"], ascending=False).reset_index(drop=True)
    return demand_df, background_df


def scale_demand(base_demand_df, scale_ratio, seed):
    if scale_ratio <= 1.0:
        return base_demand_df.copy()

    base_count = len(base_demand_df)
    extra_count = int(round(base_count * (scale_ratio - 1.0)))
    sampled = base_demand_df.sample(n=extra_count, replace=True, random_state=seed).copy().reset_index(drop=True)

    tag = f"X{int(round(scale_ratio * 100))}"
    sampled["Event ID"] = sampled["Event ID"].astype(str) + "__" + tag + "__" + sampled.index.astype(str)
    sampled["Session_ID"] = sampled["Session_ID"].astype(str) + "__" + tag + "__" + sampled.index.astype(str)

    scaled = pd.concat([base_demand_df, sampled], ignore_index=True)
    scaled = scaled.sort_values(by=["Event Size"], ascending=False).reset_index(drop=True)
    return scaled


def run_stress_test(scenario, scale_start, scale_end, scale_step, output_tag):
    base_demand_df, background_df = build_scenario_dataframes(scenario)

    rooms_df = pd.read_csv("processed_data/Room_data_General Teaching_Central.csv")
    rooms_df["Capacity"] = pd.to_numeric(rooms_df["Capacity"], errors="coerce").fillna(0)
    rooms_list = rooms_df.sort_values(by="Capacity", ascending=True).to_dict("records")

    clash_df = pd.read_csv("processed_data/student_clash_matrix.csv")
    student_clash_dict = build_student_clash_dict(clash_df)

    dist_df = pd.read_csv("processed_data/DistanceMatrix.csv")
    distance_dict = build_distance_dict(dist_df)

    scale_levels = []
    cur = scale_start
    while cur <= scale_end + 1e-9:
        scale_levels.append(round(cur, 2))
        cur += scale_step

    records = []

    print(f"Running stress test for scenario={scenario}")
    print(f"Base demand events: {len(base_demand_df)}")
    print(f"Prefilled background events: {len(background_df)}")
    print(f"Candidate rooms: {len(rooms_list)}\n")

    for ratio in scale_levels:
        t0 = time.time()
        demand_df = scale_demand(base_demand_df, float(ratio), seed=20260325 + int(ratio * 100))

        occupied_rooms = {}
        module_schedule = {}
        active_modules = {}
        ah.prefill_local_demand(background_df, occupied_rooms, module_schedule, active_modules)

        allocation_results = ah.allocate_events(
            demand_df,
            rooms_list,
            occupied_rooms,
            module_schedule,
            active_modules,
            student_clash_dict,
            distance_dict,
            ah.W_COMMUTE,
        )
        total_penalty, metrics = ah.calculate_objective_score(allocation_results)
        runtime_sec = time.time() - t0

        total_events = len(demand_df)
        unscheduled = metrics["unscheduled_count"]
        failure_rate = (unscheduled / total_events) * 100.0 if total_events else 0.0

        print(
            f"Scale={ratio:.2f} | Events={total_events} | Unscheduled={unscheduled} "
            f"| Failure={failure_rate:.2f}% | Penalty={total_penalty:.1f} | Runtime={runtime_sec:.1f}s"
        )

        records.append(
            {
                "Scenario": scenario,
                "Scale_Ratio": ratio,
                "Total_Events": total_events,
                "Unscheduled_Events": unscheduled,
                "Failure_Rate_Pct": failure_rate,
                "Total_Penalty": float(total_penalty),
                "Time_Shifted_Count": metrics["time_shifted_count"],
                "Wasted_Seats_Total": metrics["wasted_seats_count"],
                "Student_Clashes_Total": metrics["total_student_clashes"],
                "Commute_Penalty_Total": metrics["total_commute_penalty"],
                "Runtime_Sec": runtime_sec,
            }
        )

    result_df = pd.DataFrame(records)
    result_csv = f"results/stress_test_{output_tag}.csv"
    result_png = f"results/stress_test_{output_tag}.png"
    result_df.to_csv(result_csv, index=False)

    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.plot(result_df["Scale_Ratio"], result_df["Failure_Rate_Pct"], marker="o", color="red", label="Failure Rate (%)")
    ax1.set_xlabel("Demand Scale Ratio")
    ax1.set_ylabel("Failure Rate (%)", color="red")
    ax1.tick_params(axis="y", labelcolor="red")
    ax1.grid(True, linestyle="--", alpha=0.4)

    ax2 = ax1.twinx()
    ax2.plot(result_df["Scale_Ratio"], result_df["Total_Penalty"], marker="s", color="blue", label="Total Penalty")
    ax2.set_ylabel("Total Penalty", color="blue")
    ax2.tick_params(axis="y", labelcolor="blue")

    plt.title(f"Stress Test ({scenario})")
    fig.tight_layout()
    plt.savefig(result_png, dpi=220)

    breakpoint_row = result_df[result_df["Failure_Rate_Pct"] > 0].head(1)
    if breakpoint_row.empty:
        print(f"\nNo failure observed up to {max(scale_levels) * 100:.0f}% demand.")
    else:
        bp_ratio = float(breakpoint_row.iloc[0]["Scale_Ratio"])
        bp_fail = float(breakpoint_row.iloc[0]["Failure_Rate_Pct"])
        print(f"\nFirst failure breakpoint: scale={bp_ratio:.2f}, failure_rate={bp_fail:.4f}%")

    print(f"Saved stress test table: {result_csv}")
    print(f"Saved stress test figure: {result_png}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, choices=["local", "global"], default="local")
    parser.add_argument("--start", type=float, default=1.00)
    parser.add_argument("--end", type=float, default=4.50)
    parser.add_argument("--step", type=float, default=0.25)
    parser.add_argument("--tag", type=str, default="heuristic_method_local")
    args = parser.parse_args()

    run_stress_test(
        scenario=args.scenario,
        scale_start=args.start,
        scale_end=args.end,
        scale_step=args.step,
        output_tag=args.tag,
    )

