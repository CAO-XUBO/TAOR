import numpy as np
import pandas as pd
from Hyperparameter import *
import os
import argparse
import math
import random
import copy

def calculate_objective_score(allocation_results):
    metrics = {
        "unscheduled_count": 0,
        'time_shifted_count': 0,
        'campus_shifted_count': 0,
        'wasted_seats_count': 0,
        'total_student_clashes': 0,
        'total_commute_penalty': 0
    }

    total_penalty = 0

    for record in allocation_results:
        if record['Status'] == "Unscheduled":
            total_penalty += globals().get('W_UNSCHEDULED', 100000)
            metrics["unscheduled_count"] += 1
        else:
            total_penalty += record.get('Penalty', 0)
            metrics['total_student_clashes'] += record.get('Clash_Count', 0)
            metrics['total_commute_penalty'] += record.get('Commute_Penalty', 0)

            if record['Assigned_Time'] != record["Original_Time"]:
                metrics["time_shifted_count"] += 1
            if record['Assigned_Campus'] != "Central":
                metrics["campus_shifted_count"] += 1
            wasted = record['Assigned_Capacity'] - record['Event_Size']
            metrics['wasted_seats_count'] += wasted

    return total_penalty, metrics

def get_time_blocks(start_time, num_blocks):
    start_hour = int(str(start_time).split(':')[0])
    return [f"{start_hour + b:02d}:00" for b in range(int(num_blocks))]


def is_room_available(room_id, week, day, time_block_list, occupied_rooms):
    for t in time_block_list:
        if (room_id, week, day, t) in occupied_rooms:
            return False
    return True

def is_module_clashing(module_code, event_type, week, day, time_block_list, module_schedule):
    if pd.isna(module_code) or pd.isna(event_type):
        return False
    exclusive_types = ['Lecture', 'Meeting']
    is_current_exclusive = (event_type in exclusive_types)
    for t in time_block_list:
        key = (module_code, week, day, t)
        if key in module_schedule:
            existing_type, _, _ = module_schedule[key]
            is_existing_exclusive = (existing_type in exclusive_types)
            if is_current_exclusive or is_existing_exclusive:
                return True
    return False

def prefill_local_demand(local_demand_df, occupied_rooms, module_schedule, active_lectures):
    for _, row in local_demand_df.iterrows():
        room = row['Room']
        campus = row.get('Campus', 'Unknown')
        week = str(row['Weeks'])
        day = row['Day']
        start_time = row['Start_Time']
        blocks = row['Time_Blocks']
        mod_code = row['Module Code']
        event_type = row['Event Type']

        t_blocks = get_time_blocks(start_time, blocks)
        for t in t_blocks:
            occupied_rooms[(room, week, day, t)] = row['Event ID']
            if not pd.isna(mod_code):
                module_schedule[(mod_code, week, day, t)] = (event_type, room, campus)
                if event_type in ['Lecture', 'Meeting']:
                    if (week, day, t) not in active_lectures:
                        active_lectures[(week, day, t)] = set()
                    active_lectures[(week, day, t)].add(mod_code)

def allocate_events(demand_df, rooms_list, occupied_rooms, module_schedule, active_lectures, student_clash_dict,
                    distance_dict, w_commute):
    allocation_results = []
    all_possible_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    all_possible_times = [f"{str(h).zfill(2)}:00" for h in range(9, 18)]

    for index, event in demand_df.iterrows():
        event_id = event['Event ID']
        size = event['Event Size']
        orig_week = str(event['Weeks'])
        orig_day = event['Day']
        orig_time = event['Start_Time']
        blocks = event['Time_Blocks']
        mod_code = event['Module Code']
        session_id = event['Session_ID']
        event_type = event['Event Type']

        best_plan = None
        min_penalty = float('inf')

        day_rank = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4}
        search_times = [(orig_day, orig_time)]
        orig_rank = day_rank.get(orig_day, 0)
        orig_hour = int(str(orig_time).split(':')[0])

        for d in all_possible_days:
            test_rank = day_rank.get(d, 0)
            if abs(test_rank - orig_rank) > globals().get('MAX_DAY_SHIFT', 2):
                continue
            for t in all_possible_times:
                if (d, t) != (orig_day, orig_time):
                    search_times.append((d, t))

        for (test_day, test_time) in search_times:
            test_t_blocks = get_time_blocks(test_time, blocks)

            if is_module_clashing(mod_code, event_type, orig_week, test_day, test_t_blocks, module_schedule):
                continue

            time_clash_penalty = 0
            raw_clash_count = 0
            if event_type in ['Lecture', 'Meeting'] and not pd.isna(mod_code):
                for t in test_t_blocks:
                    existing_mods = active_lectures.get((orig_week, test_day, t), set())
                    for e_mod in existing_mods:
                        clashes = student_clash_dict.get((mod_code, e_mod), 0)
                        raw_clash_count += clashes
                        time_clash_penalty += clashes * W_STUDENT_CLASH

            found_room_for_this_time = False

            for room in rooms_list:
                room_id = room['Id']
                capacity = room['Capacity']
                test_room_campus = room['Campus']

                if capacity < size:
                    continue
                if not is_room_available(room_id, orig_week, test_day, test_t_blocks, occupied_rooms):
                    continue

                commute_penalty = 0
                if not pd.isna(mod_code):
                    first_t = test_t_blocks[0]
                    last_t = test_t_blocks[-1]

                    prev_t = f"{int(first_t.split(':')[0]) - 1:02d}:00"
                    prev_active_mods = active_lectures.get((orig_week, test_day, prev_t), set())
                    for p_mod in prev_active_mods:
                        if (p_mod, orig_week, test_day, prev_t) in module_schedule:
                            _, _, p_campus = module_schedule[(p_mod, orig_week, test_day, prev_t)]
                            dist = distance_dict.get((test_room_campus, p_campus),
                                                     distance_dict.get((p_campus, test_room_campus), 0))
                            if dist > 10:  # [FIXED] 将未定义的 TAU_MAX 改回 10
                                if p_mod == mod_code:
                                    commute_penalty += size * (dist - 10) * w_commute
                                else:
                                    clashes = student_clash_dict.get((mod_code, p_mod), 0)
                                    if clashes > 0:
                                        commute_penalty += clashes * (dist - 10) * w_commute

                    next_t = f"{int(last_t.split(':')[0]) + 1:02d}:00"
                    next_active_mods = active_lectures.get((orig_week, test_day, next_t), set())
                    for n_mod in next_active_mods:
                        if (n_mod, orig_week, test_day, next_t) in module_schedule:
                            _, _, n_campus = module_schedule[(n_mod, orig_week, test_day, next_t)]
                            dist = distance_dict.get((test_room_campus, n_campus),
                                                     distance_dict.get((n_campus, test_room_campus), 0))
                            if dist > 10:
                                if n_mod == mod_code:
                                    commute_penalty += size * (dist - 10) * w_commute
                                else:
                                    clashes = student_clash_dict.get((mod_code, n_mod), 0)
                                    if clashes > 0:
                                        commute_penalty += clashes * (dist - 10) * w_commute

                penalty = time_clash_penalty + commute_penalty
                test_rank = day_rank.get(test_day, 0)
                test_hour = int(str(test_time).split(':')[0])

                day_diff = abs(test_rank - orig_rank)
                hour_diff = abs(test_hour - orig_hour)

                penalty += (day_diff * W_DAY_SHIFT)
                penalty += (hour_diff * W_HOUR_SHIFT)

                if test_room_campus != 'Central':
                    penalty += globals().get('W_CAMPUS_SHIFT', 100)
                penalty += W_WASTED_SEAT * (capacity - size)

                if penalty < min_penalty:
                    min_penalty = penalty
                    best_plan = {
                        'Session_ID': session_id,
                        'Event_ID': event_id,
                        'Event_Size': size,
                        'Original_Time': f"{orig_day} {orig_time}",
                        'Assigned_Time': f"{test_day} {test_time}",
                        'Assigned_Room': room_id,
                        'Assigned_Campus': test_room_campus,
                        'Assigned_Capacity': capacity,
                        'Penalty': penalty,
                        'Clash_Count': raw_clash_count,
                        'Commute_Penalty': commute_penalty,
                        'Status': 'Scheduled',
                        'Week': orig_week,
                        'Blocks': blocks,
                        'Module_Code': mod_code,
                        'Event_Type': event_type
                    }
                    found_room_for_this_time = True
                    if penalty == 0:
                        break
            if min_penalty == 0:
                break

        if best_plan:
            allocation_results.append(best_plan)
            assigned_t_blocks = get_time_blocks(best_plan['Assigned_Time'].split(' ')[1], blocks)
            assigned_day = best_plan['Assigned_Time'].split(' ')[0]

            for t in assigned_t_blocks:
                occupied_rooms[(best_plan['Assigned_Room'], orig_week, assigned_day, t)] = event_id
                if not pd.isna(mod_code):
                    module_schedule[(mod_code, orig_week, assigned_day, t)] = (event_type, best_plan['Assigned_Room'],
                                                                               best_plan['Assigned_Campus'])
                    if event_type in ['Lecture', 'Meeting']:
                        if (orig_week, assigned_day, t) not in active_lectures:
                            active_lectures[(orig_week, assigned_day, t)] = set()
                        active_lectures[(orig_week, assigned_day, t)].add(mod_code)
        else:
            allocation_results.append({
                'Session_ID': session_id,
                'Event_ID': event_id,
                'Event_Size': size,
                'Original_Time': f"{orig_day} {orig_time}",
                'Assigned_Time': None,
                'Assigned_Room': None,
                'Status': 'Unscheduled',
                'Week': orig_week,
                'Blocks': blocks,
                'Module_Code': mod_code,
                'Event_Type': event_type
            })

    return allocation_results


def optimize_with_sa(allocation_results, rooms_list, occupied_rooms, module_schedule, active_lectures,
                     student_clash_dict, distance_dict, w_commute, initial_temp=1000, cooling_rate=0.98, max_iter=200):
    print(f"\nStart simulated annealing optimisation (Initial T={initial_temp}, Cooling={cooling_rate})")

    all_possible_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    all_possible_times = [f"{str(h).zfill(2)}:00" for h in range(9, 18)]
    day_rank = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4}

    current_penalty, _ = calculate_objective_score(allocation_results)
    best_penalty = current_penalty
    best_allocation = copy.deepcopy(allocation_results)

    scheduled_indices = [i for i, r in enumerate(allocation_results) if r['Status'] == 'Scheduled']
    if not scheduled_indices:
        return allocation_results

    T = initial_temp
    accepted_moves = 0

    def calc_single_penalty(record, test_day, test_time, capacity, test_room_campus):
        orig_day, orig_time = record['Original_Time'].split(' ')
        orig_rank = day_rank.get(orig_day, 0)
        orig_hour = int(str(orig_time).split(':')[0])
        test_rank = day_rank.get(test_day, 0)
        test_hour = int(str(test_time).split(':')[0])

        time_clash_penalty = 0
        raw_clash_count = 0
        test_t_blocks = get_time_blocks(test_time, record['Blocks'])
        if record['Event_Type'] in ['Lecture', 'Meeting'] and not pd.isna(record['Module_Code']):
            for t in test_t_blocks:
                existing_mods = active_lectures.get((record['Week'], test_day, t), set())
                for e_mod in existing_mods:
                    if e_mod != record['Module_Code']:
                        clashes = student_clash_dict.get((record['Module_Code'], e_mod), 0)
                        raw_clash_count += clashes
                        time_clash_penalty += clashes * W_STUDENT_CLASH

        commute_penalty = 0
        if not pd.isna(record['Module_Code']):
            mod_code = record['Module_Code']
            orig_week = record['Week']
            first_t = test_t_blocks[0]
            last_t = test_t_blocks[-1]
            size = record['Event_Size']

            prev_t = f"{int(first_t.split(':')[0]) - 1:02d}:00"
            prev_active_mods = active_lectures.get((orig_week, test_day, prev_t), set())
            for p_mod in prev_active_mods:
                if (p_mod, orig_week, test_day, prev_t) in module_schedule:
                    _, _, p_campus = module_schedule[(p_mod, orig_week, test_day, prev_t)]
                    dist = distance_dict.get((test_room_campus, p_campus),
                                             distance_dict.get((p_campus, test_room_campus), 0))
                    if dist > 10:
                        if p_mod == mod_code:
                            commute_penalty += size * (dist - 10) * w_commute
                        else:
                            clashes = student_clash_dict.get((mod_code, p_mod), 0)
                            if clashes > 0:
                                commute_penalty += clashes * (dist - 10) * w_commute

            next_t = f"{int(last_t.split(':')[0]) + 1:02d}:00"
            next_active_mods = active_lectures.get((orig_week, test_day, next_t), set())
            for n_mod in next_active_mods:
                if (n_mod, orig_week, test_day, next_t) in module_schedule:
                    _, _, n_campus = module_schedule[(n_mod, orig_week, test_day, next_t)]
                    dist = distance_dict.get((test_room_campus, n_campus),
                                             distance_dict.get((n_campus, test_room_campus), 0))
                    if dist > 10:
                        if n_mod == mod_code:
                            commute_penalty += size * (dist - 10) * w_commute
                        else:
                            clashes = student_clash_dict.get((mod_code, n_mod), 0)
                            if clashes > 0:
                                commute_penalty += clashes * (dist - 10) * w_commute

        day_diff = abs(test_rank - orig_rank)
        hour_diff = abs(test_hour - orig_hour)

        penalty = time_clash_penalty + commute_penalty + (day_diff * W_DAY_SHIFT) + (hour_diff * W_HOUR_SHIFT)
        if test_room_campus != 'Central': penalty += globals().get('W_CAMPUS_SHIFT', 100)
        penalty += W_WASTED_SEAT * (capacity - record['Event_Size'])

        return penalty, raw_clash_count, commute_penalty

    def update_state(record, day, time, mode="remove"):
        t_blocks = get_time_blocks(time, record['Blocks'])
        week = record['Week']
        mod_code = record['Module_Code']
        event_type = record['Event_Type']
        room_id = record['Assigned_Room']
        campus = record['Assigned_Campus']

        for t in t_blocks:
            if mode == "remove":
                occupied_rooms.pop((room_id, week, day, t), None)
                if not pd.isna(mod_code):
                    module_schedule.pop((mod_code, week, day, t), None)
                    if event_type in ['Lecture', 'Meeting'] and (week, day, t) in active_lectures:
                        active_lectures[(week, day, t)].discard(mod_code)
            elif mode == "add":
                occupied_rooms[(room_id, week, day, t)] = record['Event_ID']
                if not pd.isna(mod_code):
                    module_schedule[(mod_code, week, day, t)] = (event_type, room_id, campus)
                    if event_type in ['Lecture', 'Meeting']:
                        if (week, day, t) not in active_lectures:
                            active_lectures[(week, day, t)] = set()
                        active_lectures[(week, day, t)].add(mod_code)

    while T > 1.0:
        for _ in range(max_iter):
            idx = random.choice(scheduled_indices)
            record = allocation_results[idx]

            old_day, old_time = record['Assigned_Time'].split(' ')
            old_penalty = record['Penalty']

            update_state(record, old_day, old_time, mode="remove")

            test_room = random.choice(rooms_list)
            if test_room['Capacity'] < record['Event_Size']:
                update_state(record, old_day, old_time, mode="add")
                continue

            test_day = random.choice(all_possible_days)
            test_time = random.choice(all_possible_times)
            test_t_blocks = get_time_blocks(test_time, record['Blocks'])

            if not is_room_available(test_room['Id'], record['Week'], test_day, test_t_blocks, occupied_rooms):
                update_state(record, old_day, old_time, mode="add")
                continue
            if is_module_clashing(record['Module_Code'], record['Event_Type'], record['Week'], test_day, test_t_blocks,
                                  module_schedule):
                update_state(record, old_day, old_time, mode="add")
                continue

            new_penalty, new_clashes, new_commute = calc_single_penalty(record, test_day, test_time,
                                                                        test_room['Capacity'], test_room['Campus'])
            delta_e = new_penalty - old_penalty

            if delta_e < 0 or random.random() < math.exp(-delta_e / T):
                record['Assigned_Time'] = f"{test_day} {test_time}"
                record['Assigned_Room'] = test_room['Id']
                record['Assigned_Capacity'] = test_room['Capacity']
                record['Assigned_Campus'] = test_room['Campus']
                record['Penalty'] = new_penalty
                record['Clash_Count'] = new_clashes
                record['Commute_Penalty'] = new_commute
                update_state(record, test_day, test_time, mode="add")

                current_penalty += delta_e
                accepted_moves += 1

                if current_penalty < best_penalty:
                    best_penalty = current_penalty
                    best_allocation = copy.deepcopy(allocation_results)
            else:
                update_state(record, old_day, old_time, mode="add")

        T *= cooling_rate

    print(
        f"Simulated annealing complete, Total valid adjustments received {accepted_moves}. Global penalty: {best_penalty}")
    return best_allocation


def print_stage_summary(title, score, metrics):
    print("\n" + "=" * 20 + f" [{title}] " + "=" * 20)
    print(f"Total Penalty:          {score}")
    print(f"Total Student Clashes:  {metrics['total_student_clashes']}")
    print(f"Total Commute Penalty:  {metrics['total_commute_penalty']}")
    print(f"Wasted Seats Total:     {metrics['wasted_seats_count']}")
    print(f"Time Shifted Count:     {metrics['time_shifted_count']}")
    unscheduled = metrics.get('unscheduled_count', 0)
    print(f"Failure Rate:           {(unscheduled / len(demand_df) * 100):.2f}%")
    print("=" * (42 + len(title)))


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--w_clash", type=float, default=W_STUDENT_CLASH)
    parser.add_argument("--w_day", type=float, default=W_DAY_SHIFT)
    parser.add_argument("--w_hour", type=float, default=W_HOUR_SHIFT)
    parser.add_argument("--w_wasted", type=float, default=W_WASTED_SEAT)
    parser.add_argument("--w_commute", type=float, default=W_COMMUTE)  # 你的Hyperparameter里记得有这行
    parser.add_argument("--exp_name", type=str, default="Default_Exp")
    parser.add_argument("--use_sa", action="store_true", help="Enable Simulated Annealing refinement")
    args = parser.parse_args()

    W_STUDENT_CLASH = args.w_clash
    W_DAY_SHIFT = args.w_day
    W_HOUR_SHIFT = args.w_hour
    W_WASTED_SEAT = args.w_wasted
    W_COMMUTE = args.w_commute

    print(
        f"\nStart the experiment: [{args.exp_name}] | Clash={W_STUDENT_CLASH}, Day={W_DAY_SHIFT}, Wasted={W_WASTED_SEAT}, Commute={W_COMMUTE}")

    demand_df = pd.read_csv('processed_data/2024-5_data_demand_General Teaching_Holyrood.csv')
    demand_df = demand_df.sort_values(by=['Event Size'], ascending=False).reset_index(drop=True)
    rooms_df = pd.read_csv('processed_data/Room_data_General Teaching_Central.csv')
    rooms_df['Capacity'] = pd.to_numeric(rooms_df['Capacity'], errors='coerce').fillna(0)
    rooms_list = rooms_df.sort_values(by='Capacity', ascending=True).to_dict('records')

    all_campuses_df = pd.read_csv('processed_data/2024-5_data_demand_General Teaching_All.csv')
    global_background_df = all_campuses_df[all_campuses_df['Campus'] != 'Holyrood'].reset_index(drop=True)

    clash_df = pd.read_csv('processed_data/student_clash_matrix.csv')
    student_clash_dict = {}
    for _, row in clash_df.iterrows():
        student_clash_dict[(row['Module_A'], row['Module_B'])] = row['Clash_Count']
        student_clash_dict[(row['Module_B'], row['Module_A'])] = row['Clash_Count']

    distance_dict = {}
    dist_df = pd.read_csv('processed_data/DistanceMatrix.csv')
    for _, row in dist_df.iterrows():
        campus_from = row['Campus From']
        for col in dist_df.columns:
            if col != 'Campus From':
                distance_dict[(campus_from, col)] = float(row[col])


    occupied_rooms = {}
    module_schedule = {}
    active_lectures = {}

    prefill_local_demand(global_background_df, occupied_rooms, module_schedule, active_lectures)

    greedy_results = allocate_events(
        demand_df, rooms_list, occupied_rooms, module_schedule,
        active_lectures, student_clash_dict, distance_dict, W_COMMUTE
    )
    greedy_score, greedy_metrics = calculate_objective_score(greedy_results)

    print_stage_summary("STAGE 1: GREEDY BASELINE", greedy_score, greedy_metrics)

    final_results = greedy_results
    final_score = greedy_score
    final_metrics = greedy_metrics

    if args.use_sa:
        sa_results = optimize_with_sa(
            copy.deepcopy(greedy_results), rooms_list, occupied_rooms,
            module_schedule, active_lectures, student_clash_dict,
            distance_dict, W_COMMUTE,
            initial_temp=5000, cooling_rate=0.99, max_iter=20000
        )
        sa_score, sa_metrics = calculate_objective_score(sa_results)

        print_stage_summary("STAGE 2: SA REFINEMENT", sa_score, sa_metrics)

        improvement = (greedy_score - sa_score) / greedy_score * 100
        print(f"Optimization Success: Penalty reduced by {improvement:.2f}%")

        final_results = sa_results
        final_score = sa_score
        final_metrics = sa_metrics

    results_df = pd.DataFrame(final_results)
    results_df.to_csv("results/Final_Allocation_Results.csv", index=False)

    summary_file = f"results/{args.exp_name}_Summary.csv"
    file_exists = os.path.isfile(summary_file)
    with open(summary_file, "a", encoding="utf-8") as f:
        if not file_exists:
            f.write(
                "W_CLASH,W_DAY,W_HOUR,W_WASTED,W_COMMUTE,Time_Shifted,Wasted_Seats,Student_Clashes,Commute_Penalty,Total_Penalty\n")
        f.write(
            f"{W_STUDENT_CLASH},{W_DAY_SHIFT},{W_HOUR_SHIFT},{W_WASTED_SEAT},{W_COMMUTE},{final_metrics['time_shifted_count']},{final_metrics['wasted_seats_count']},{final_metrics['total_student_clashes']},{final_metrics['total_commute_penalty']},{final_score}\n"
        )
