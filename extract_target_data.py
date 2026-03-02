import pandas as pd

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
    target_data = target_campus_data[target_campus_data["Room"].isin(target_rooms)]

    return target_data

def data_output(target_data, output_filepath):
    target_data.to_csv(output_filepath)

if __name__ == "__main__":
    # Origin data and processed data file path
    filepath = "origin_data/2024-5 Event Module Room.xlsx"

    target_campus = "Holyrood"
    target_room_type = "General Teaching"

    output_filename = f"2024-5_data_demand_{target_room_type}_{target_campus}.csv"
    output_filepath = f"processed_data/{output_filename}"

    origin_data = data_loader(filepath)

    target_data = data_extraction(origin_data, target_campus, target_room_type)

    data_output(target_data, output_filepath)