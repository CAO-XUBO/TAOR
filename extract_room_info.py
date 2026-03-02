import pandas as pd

def data_loader(filepath):
    origin_data = pd.read_excel(filepath)
    return origin_data

def data_extraction(origin_data, target_campus, target_room_type="General Teaching"):
    '''
    This function only adapt to the target campus with target room type information
    '''
    extract_data = origin_data[
        ["Id", "Capacity", "Specialist room type", "Campus"]]

    # delete null value of "Room"
    clean_data = extract_data.copy()

    # Pick up the target campus
    target_rooms_df = clean_data[
        (clean_data["Campus"] == target_campus) &
        (clean_data["Specialist room type"] == target_room_type)
    ].copy()

    # Pick up the target transfer data
    target_rooms_df.drop_duplicates(subset=["Id"], inplace=True)

    return target_rooms_df

def data_output(target_data, output_filepath):
    target_data.to_csv(output_filepath)

if __name__ == "__main__":
    # Origin data and processed data file path
    filepath = "origin_data/Rooms and Room Types.xlsx"

    target_campus = "Central"
    target_room_type = "General Teaching"

    output_filename = f"Room_data_{target_room_type}_{target_campus}.csv"
    output_filepath = f"processed_data/{output_filename}"

    origin_data = data_loader(filepath)
    target_data = data_extraction(origin_data, target_campus, target_room_type)
    data_output(target_data, output_filepath)