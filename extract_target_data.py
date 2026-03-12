import pandas as pd
import numpy as np

def data_loader(filepath):
    origin_data = pd.read_excel(filepath)
    return origin_data

def data_extraction(origin_data, target_campus, target_room_type="General Teaching"):
    '''
    This function only adapt to the target campus with target room type
    '''
    extract_data = origin_data[
        ["Module Department", "Module Code", "Event ID", "Event Type", "Duration (minutes)", "Event Size", "Timeslot",
         "Number of Weeks", "Weeks", "Room", "Room Type 1", "Room type 2", "Building", "Campus"]]


    # delete null value of "Room"
    clean_data = extract_data.copy()
    clean_data.dropna(subset=["Room"], inplace=True)

    # Pick up the target campus
    target_campus_data = clean_data[clean_data["Campus"] == target_campus]

    # Pick up the target transfer data
    target_rooms = target_campus_data[target_campus_data["Room type 2"] == target_room_type]["Room"].unique()

    # Reverse data screening
    target_data = target_campus_data[target_campus_data["Room"].isin(target_rooms)].copy()

    target_data.dropna(subset=["Weeks", "Timeslot"], inplace=True)

    target_data["Weeks"] = target_data['Weeks'].astype(str).str.split(',')
    target_data = target_data.explode('Weeks')
    target_data['Weeks'] = target_data['Weeks'].str.strip()
    target_data = target_data[target_data['Weeks'] != 'nan']
    target_data[['Day', 'Start_Time']] = target_data['Timeslot'].str.split(' ', expand=True)

    target_data['Duration (minutes)'] = pd.to_numeric(target_data['Duration (minutes)'], errors='coerce').fillna(60)
    target_data['Time_Blocks'] = np.ceil(target_data['Duration (minutes)'] / 60.0).astype(int)

    target_data['Session_ID'] = target_data['Event ID'] + "_W" + target_data['Weeks']

    target_data['Event Size'] = pd.to_numeric(target_data['Event Size'], errors='coerce').fillna(0)
    target_data = target_data.sort_values(by=['Event Size'], ascending=False).reset_index(drop=True)

    return target_data

def clean_event_type(event_str):
    """
    Even type cleaning
    """
    if pd.isna(event_str):
        return 'Other'

    s = str(event_str).upper() # Uniform capitalisation to prevent omissions

    # Delete
    if any(kw in s for kw in ['EXAM', 'TEST', 'PRESENTATION', 'SELF STUDY']):
        return 'DROP'

    # Lecture
    if any(kw in s for kw in ['LECTURE', 'Q&A', 'INDUCTION', 'FIRST CLASS']):
        return 'Lecture'

    # Tutorial/Seminar/Workshop
    if 'TUTORIAL' in s:
        return 'Tutorial'
    if 'SEMINAR' in s:
        return 'Seminar'
    if 'WORKSHOP' in s:
        return 'Workshop'

    # Activity/Lab/Breakout
    if any(kw in s for kw in ['ACTIVITY', 'BREAKOUT', 'PRACTICAL', 'LABORATORY', 'STUDIO', 'GROUPWORK', 'CRIT']):
        return 'Activity'

    # Meeting/Feedback
    if any(kw in s for kw in ['MEETING', 'FEEDBACK', 'REVIEW']):
        return 'Meeting'

    return 'Other'

def data_output(df, output_filepath):
    df.to_csv(output_filepath)

if __name__ == "__main__":
    # Origin data and processed data file path
    filepath = "origin_data/2024-5 Event Module Room.xlsx"

    target_campus = "Holyrood"
    target_room_type = "General Teaching"

    output_filename = f"2024-5_data_demand_{target_room_type}_{target_campus}.csv"
    output_filepath = f"processed_data/{output_filename}"

    origin_data = data_loader(filepath)

    target_data = data_extraction(origin_data, target_campus, target_room_type)

    target_data['Clean_Type'] = target_data['Event Type'].apply(clean_event_type)

    clean_target_data = target_data[target_data['Clean_Type'] != 'DROP'].copy()

    clean_target_data['Event Type'] = clean_target_data['Clean_Type']
    clean_target_data.drop(columns=['Clean_Type'], inplace=True)

    data_output(clean_target_data, output_filepath)