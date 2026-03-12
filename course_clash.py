import pandas as pd
from itertools import combinations
from collections import defaultdict

def data_loader(filepath):
    origin_data = pd.read_excel(filepath)
    return origin_data

def generate_clash_matrix(df):
    # Cleaning the dial
    df.columns = df.columns.str.strip()

    student_col = 'AnonID'
    course_col = 'Course ID'

    df['Base_Module'] = df[course_col].astype(str).str.split('_').str[0]
    student_modules = df.groupby(student_col)['Base_Module'].apply(lambda x: sorted(list(set(x))))
    clash_counts = defaultdict(int)
    for modules in student_modules:
        # Use combinations to count the number of times any two courses are selected simultaneously by this student.
        for pair in combinations(modules, 2):
            clash_counts[pair] += 1

    return dict(clash_counts)

def data_output(df, output_filepath):
    df.to_csv(output_filepath, index=False)

if __name__ == "__main__":

    student_data_path = "origin_data/2024-5 Student Programme Module Event.xlsx"
    output_path = "processed_data/student_clash_matrix.csv"

    student_data = data_loader(student_data_path)

    clash_matrix = generate_clash_matrix(student_data)

    # Turn to list
    clash_list = []
    for (mod_a, mod_b), count in clash_matrix.items():
        if count > 2:
            clash_list.append({
                'Module_A': mod_a,
                'Module_B': mod_b,
                'Clash_Count': count
            })

    # Turn to DataFrame
    clash_df = pd.DataFrame(clash_list)

    if not clash_df.empty:
        clash_df = clash_df.sort_values(by='Clash_Count', ascending=False).reset_index(drop=True)

    data_output(clash_df, output_path)
