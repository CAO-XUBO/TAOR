import numpy as np
import pandas as pd
from Hyperparameter import *

def calculate_objective_score(allocation_resultes):
    metrics = {
        "unscheduled_count": 0,
        'time_shifted_count': 0,
        'campus_shifted_count': 0,
        'wasted_seats_count': 0
    }

    total_penalty = 0

    for record in allocation_resultes:
        if record['Status'] == "Unscheduled":
            total_penalty += W_UNSCHEDULED
            metrics["unscheduled_count"] += 1
            continue

        if record['Assigned_Time'] != record["Original_Time"]:
            total_penalty += W_TIME_SHIFT
            metrics["time_shifted_count"] += 1

        if record['Assigned_Campus'] != "Central":
            total_penalty += W_CAMPUS_SHIFT
            metrics["campus_shifted_count"] += 1

        wasted = record['Assigned_Capacity'] - record['Event_Size']
        total_penalty += (W_WASTED_SEAT * wasted)
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

    # Event type that cannot clash
    exclusive_types = ['Lecture', 'Meeting']
    is_current_exclusive = (event_type in exclusive_types)

    for t in time_block_list:
        key = (module_code, week, day, t)
        if key in module_schedule:
            existing_type = module_schedule[key]
            is_existing_exclusive = (existing_type in exclusive_types)

            if is_current_exclusive or is_existing_exclusive:
                return True
    return False


def prefill_local_demand(local_demand_df, occupied_rooms, module_schedule, active_lectures):
    for _, row in local_demand_df.iterrows():
        room = row['Room']
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
                module_schedule[(mod_code, week, day, t)] = event_type

                if event_type in ['Lecture', 'Meeting']:
                    if (week, day, t) not in active_lectures:
                        active_lectures[(week, day, t)] = set()
                    active_lectures[(week, day, t)].add(mod_code)


def allocate_events(demand_df, rooms_list, occupied_rooms, module_schedule, active_lectures, student_clash_dict):
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

        search_times = [(orig_day, orig_time)]
        for d in all_possible_days:
            for t in all_possible_times:
                if (d, t) != (orig_day, orig_time):
                    search_times.append((d, t))

        for (test_day, test_time) in search_times:
            test_t_blocks = get_time_blocks(test_time, blocks)

            if is_module_clashing(mod_code, event_type, orig_week, test_day, test_t_blocks, module_schedule):
                continue

            time_clash_penalty = 0
            if event_type in ['Lecture', 'Meeting'] and not pd.isna(mod_code):
                for t in test_t_blocks:
                    existing_mods = active_lectures.get((orig_week, test_day, t), set())
                    for e_mod in existing_mods:
                        clash_count = student_clash_dict.get((mod_code, e_mod), 0)
                        time_clash_penalty += clash_count * W_STUDENT_CLASH

            found_room_for_this_time = False

            for room in rooms_list:
                room_id = room['Id']
                capacity = room['Capacity']
                campus = room['Campus']

                if capacity < size:
                    continue

                if not is_room_available(room_id, orig_week, test_day, test_t_blocks, occupied_rooms):
                    continue
                # Calculate the penalty
                penalty = time_clash_penalty
                if test_day != orig_day or test_time != orig_time:
                    penalty += W_TIME_SHIFT
                if campus != 'Central':
                    penalty += W_CAMPUS_SHIFT
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
                        'Assigned_Campus': campus,
                        'Assigned_Capacity': capacity,
                        'Penalty': penalty,
                        'Status': 'Scheduled'
                    }
                    found_room_for_this_time = True
                    break

            if found_room_for_this_time:
                break

        if best_plan:
            allocation_results.append(best_plan)
            assigned_t_blocks = get_time_blocks(best_plan['Assigned_Time'].split(' ')[1], blocks)
            assigned_day = best_plan['Assigned_Time'].split(' ')[0]

            for t in assigned_t_blocks:
                occupied_rooms[
                    (best_plan['Assigned_Room'], orig_week, best_plan['Assigned_Time'].split(' ')[0], t)] = event_id
                if not pd.isna(mod_code):
                    module_schedule[(mod_code, orig_week, best_plan['Assigned_Time'].split(' ')[0], t)] = event_type
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
                'Status': 'Unscheduled'
            })

    return allocation_results


if __name__ == "__main__":

    demand_df = pd.read_csv('processed_data/2024-5_data_demand_General Teaching_Holyrood.csv')
    local_central_df = pd.read_csv('processed_data/2024-5_data_demand_General Teaching_Central.csv')
    rooms_df = pd.read_csv('processed_data/Room_data_General Teaching_Central.csv')

    clash_df = pd.read_csv('processed_data/student_clash_matrix.csv')
    student_clash_dict = {}
    for _, row in clash_df.iterrows():
        student_clash_dict[(row['Module_A'], row['Module_B'])] = row['Clash_Count']
        student_clash_dict[(row['Module_B'], row['Module_A'])] = row['Clash_Count']

    rooms_df['Capacity'] = pd.to_numeric(rooms_df['Capacity'], errors='coerce').fillna(0)
    rooms_list = rooms_df.sort_values(by='Capacity', ascending=True).to_dict('records')

    occupied_rooms = {}
    module_schedule = {}
    active_lectures = {}

    prefill_local_demand(local_central_df, occupied_rooms, module_schedule, active_lectures)

    allocation_results = allocate_events(demand_df, rooms_list, occupied_rooms, module_schedule, active_lectures, student_clash_dict)

    final_score, metrics = calculate_objective_score(allocation_results)

    results_df = pd.DataFrame(allocation_results)
    results_df.to_csv("results/Final_Allocation_Results.csv", index=False)

    total_events = len(results_df)
    unscheduled_count = metrics["unscheduled_count"]
    success_count = total_events - unscheduled_count
    fail_rate = (unscheduled_count / total_events) * 100

    print(f"Unable to be accommodated within the timetable: {unscheduled_count}")
    print(f"Failure Rate: {fail_rate:.2f}%")
