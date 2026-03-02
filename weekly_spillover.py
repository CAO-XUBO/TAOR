import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


# 1. Load datasets
central_supply = pd.read_csv('processed_data/Room_data_General Teaching_Central.csv')
central_demand = pd.read_csv('processed_data/2024-5_data_demand_General Teaching_Central.csv')
holyrood_demand = pd.read_csv('processed_data/2024-5_data_demand_General Teaching_Holyrood.csv')

# 2. Prepare room capacity and supply metrics
central_supply['Capacity'] = pd.to_numeric(central_supply['Capacity'], errors='coerce').fillna(0)
valid_rooms = central_supply[central_supply['Capacity'] > 0]
room_counts = valid_rooms.groupby('Capacity').size().reset_index(name='Room Count')

# Weekly safe supply: 45 hours/week at 75% utilization factor
room_counts['Weekly_Safe_Supply'] = room_counts['Room Count'] * 45 * 0.75
available_caps = room_counts['Capacity'].tolist()

def find_best_fit_room(event_size):
    """Returns the smallest available capacity tier that fits the event size."""
    valid_caps = [c for c in available_caps if c >= event_size]
    return min(valid_caps) if valid_caps else -1

for df in [central_demand, holyrood_demand]:
    df['Weeks'] = df['Weeks'].astype(str)
    df['Event Size'] = pd.to_numeric(df['Event Size'], errors='coerce').fillna(0)
    df['Duration (hours)'] = pd.to_numeric(df['Duration (minutes)'], errors='coerce').fillna(0) / 60.0
    df['Required_Capacity'] = df['Event Size'].apply(find_best_fit_room)

# 3. Weekly demand and spillover calculation
weeks = list(range(1, 53))
trend_data = []

for week in weeks:
    pattern = r'\b' + str(week) + r'\b'
    c_week = central_demand[central_demand['Weeks'].str.contains(pattern, na=False)]
    h_week = holyrood_demand[holyrood_demand['Weeks'].str.contains(pattern, na=False)]
    week_dem = pd.concat([c_week, h_week], ignore_index=True)

    if week_dem.empty:
        trend_data.append({'Week': week, 'Total_Demand_Hours': 0.0, 'Spillover_Hours': 0.0})
        continue

    initial_demand = week_dem[week_dem['Required_Capacity'] != -1].groupby('Required_Capacity')['Duration (hours)'].sum().reset_index(name='Demand_Hours')
    week_df = pd.merge(room_counts[['Capacity', 'Weekly_Safe_Supply']], initial_demand, left_on='Capacity', right_on='Required_Capacity', how='left').fillna(0)

    current_overflow = 0.0
    week_spillover = 0.0
    total_demand = week_df['Demand_Hours'].sum()

    for index, row in week_df.iterrows():
        supply = row['Weekly_Safe_Supply']
        initial = row['Demand_Hours']
        incoming = current_overflow
        
        absorbed = min(incoming, supply)
        rem_supply = supply - absorbed
        new_overflow = max(0, initial - rem_supply)
        
        week_spillover += new_overflow
        current_overflow = (incoming - absorbed) + new_overflow

    trend_data.append({'Week': week, 'Total_Demand_Hours': total_demand, 'Spillover_Hours': week_spillover})

trend_df = pd.DataFrame(trend_data)

# Console Summary Output
total_annual_demand = trend_df['Total_Demand_Hours'].sum()
total_annual_spillover = trend_df['Spillover_Hours'].sum()
empty_weeks_count = len(trend_df[trend_df['Total_Demand_Hours'] == 0])
active_weeks_count = len(trend_df[trend_df['Total_Demand_Hours'] > 0])

print("\n" + "-"*50)
print("ANNUAL SUMMARY STATISTICS")
print("-"*50)
print(f"Total Weeks:                52")
print(f"Active Teaching Weeks:      {active_weeks_count}")
print(f"Holiday/Inactive Weeks:     {empty_weeks_count}")
print(f"Total Annual Demand:        {total_annual_demand:,.2f} Room-Hours")
print(f"Total Annual Spillover:     {total_annual_spillover:,.2f} Room-Hours")

print("\nTOP 5 WEEKS BY SPILLOVER VOLUME")
print("-"*50)
top_chaos = trend_df.sort_values(by='Spillover_Hours', ascending=False).head(5)
top_chaos['% of Total Spillover'] = (top_chaos['Spillover_Hours'] / total_annual_spillover * 100).fillna(0).apply(lambda x: f"{x:.1f}%")
print(top_chaos[['Week', 'Total_Demand_Hours', 'Spillover_Hours', '% of Total Spillover']].to_string(index=False))

print("\nTOP 5 WEEKS BY TOTAL DEMAND")
print("-"*50)
top_busy = trend_df.sort_values(by='Total_Demand_Hours', ascending=False).head(5)
print(top_busy[['Week', 'Total_Demand_Hours', 'Spillover_Hours']].to_string(index=False))
print("-"*50 + "\n")

# 4. Visualization
fig, ax1 = plt.subplots(figsize=(18, 7))

# Synchronize scales for direct comparison
global_max = max(trend_df['Total_Demand_Hours'].max(), trend_df['Spillover_Hours'].max()) * 1.1

# Primary Axis: Demand
ax1.bar(trend_df['Week'], trend_df['Total_Demand_Hours'], color='#1f77b4', alpha=0.5, label='Total Native Demand (Room-Hours)')
ax1.set_xlabel('Academic Week (1 to 52)', fontsize=14, fontweight='bold')
ax1.set_ylabel('Total System Demand (Hours)', color='#1f77b4', fontsize=14, fontweight='bold')
ax1.tick_params(axis='y', labelcolor='#1f77b4', labelsize=12)
ax1.set_xticks(weeks)
ax1.set_xticklabels(weeks, fontsize=9)
ax1.set_ylim(0, global_max)
ax1.grid(axis='y', linestyle='--', alpha=0.3)

# Secondary Axis: Spillover
ax2 = ax1.twinx()
ax2.plot(trend_df['Week'], trend_df['Spillover_Hours'], color='red', marker='o', linewidth=3, markersize=6, label='Cascading Spillover (Hours)')
ax2.set_ylabel('Spillover Hours', color='red', fontsize=14, fontweight='bold')
ax2.tick_params(axis='y', labelcolor='red', labelsize=12)
ax2.set_ylim(0, global_max)

plt.title('Weekly Room Demand vs. Cascading Spillover Trends (Synchronized Scales)', fontsize=18, fontweight='bold')

lines_1, labels_1 = ax1.get_legend_handles_labels()
lines_2, labels_2 = ax2.get_legend_handles_labels()
ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left', fontsize=12)

fig.tight_layout()
plt.savefig('weekly_spillover_trend.png', dpi=300)
print("Analysis complete. Plot saved as 'weekly_spillover_trend.png'.")