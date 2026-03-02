import pandas as pd

def data_loader(filepath, sheet_name):
    origin_data = pd.read_excel(filepath, sheet_name=sheet_name)
    return origin_data

def distance_matrix(origin_data):
    distance_data = origin_data[["Campus From", "Campus To", "Travel time (mins)"]]
    distance_matrix = distance_data.pivot_table(
        index='Campus From',
        columns='Campus To',
        values='Travel time (mins)'
    )
    return distance_matrix

def data_output(distance_data, output_filepath):
    distance_data.to_csv(output_filepath)

if __name__ == '__main__':
    # Input file path
    filepath = "origin_data/Rooms and Room Types.xlsx"
    sheet_name = "Room Constraints"

    # Output file path
    output_filepath = "processed_data/DistanceMatrix.csv"

    origin_data = data_loader(filepath, sheet_name)
    distance_data = distance_matrix(origin_data)
    data_output(distance_data, output_filepath)