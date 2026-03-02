import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 1. Load datasets
central_supply = pd.read_csv('processed_data/Room_data_General Teaching_Central.csv')
central_demand = pd.read_csv('processed_data/2024-5_data_demand_General Teaching_Central.csv')
holyrood_demand = pd.read_csv('processed_data/2024-5_data_demand_General Teaching_Holyrood.csv')

# 2. Extract Room Capacity and Supply Baseline
central_supply['Capacity'] = pd.to_numeric(central_supply['Capacity'], errors='coerce').fillna(0)
valid_rooms = central_supply[central_supply['Capacity'] > 0]
room_counts = valid_rooms.groupby('Capacity').size().reset_index(name='Room Count')
room_counts = room_counts.sort_values('Capacity').reset_index(drop=True)

# Define Weekly Safe Supply: 45 hours/week at 75% utilization factor
room_counts['Weekly_Safe_Supply'] = room_counts['Room Count'] * 45 * 0.75

# Capacity matching: Identify the smallest available room capable of holding the event size
available_caps = room_counts['Capacity'].tolist()
def find_best_fit_room(event_size):
    valid_caps = [c for c in available_caps if c >= event_size]
    return min(valid_caps) if valid_caps else -1

# Pre-process demand data
for df in [central_demand, holyrood_demand]:
    df['Weeks'] = df['Weeks'].astype(str)
    df['Event Size'] = pd.to_numeric(df['Event Size'], errors='coerce').fillna(0)
    df['Duration (hours)'] = pd.to_numeric(df['Duration (minutes)'], errors='coerce').fillna(0) / 60.0
    df['Required_Capacity'] = df['Event Size'].apply(find_best_fit_room)

# 3. Simulation Engine: Weekly Discrete-Time Cascade
def run_strict_simulation(target_weeks_list, title, filename):
    """
    Simulates demand and spillover on a week-by-week basis.
    Calculates supply only for active teaching weeks to avoid holiday skewing.
    """
    cumulative_df = room_counts[['Capacity', 'Room Count', 'Weekly_Safe_Supply']].copy()
    cumulative_df['Total_Safe_Supply'] = 0.0
    cumulative_df['Total_Initial_Demand'] = 0.0
    cumulative_df['Total_Native_Scheduled'] = 0.0
    cumulative_df['Total_Absorbed_Spillover'] = 0.0
    
    global_spillover = 0.0
    active_weeks_count = 0
    
    # Week-by-Week Loop
    for week in target_weeks_list:
        pattern = r'\b' + str(week) + r'\b'
        c_week = central_demand[central_demand['Weeks'].str.contains(pattern, na=False)]
        h_week = holyrood_demand[holyrood_demand['Weeks'].str.contains(pattern, na=False)]
        week_dem = pd.concat([c_week, h_week], ignore_index=True)
        
        # Skip holiday weeks where no classes are scheduled
        if week_dem.empty:
            continue 
            
        active_weeks_count += 1
        
        # Aggregate native demand for the current week
        initial_demand = week_dem[week_dem['Required_Capacity'] != -1].groupby('Required_Capacity')['Duration (hours)'].sum().reset_index(name='Demand_Hours')
        week_df = pd.merge(room_counts[['Capacity', 'Weekly_Safe_Supply']], initial_demand, left_on='Capacity', right_on='Required_Capacity', how='left').fillna(0)
        
        current_overflow = 0.0
        
        # Process cascading spillover across room tiers
        for index, row in week_df.iterrows():
            supply = row['Weekly_Safe_Supply']
            initial = row['Demand_Hours']
            incoming = current_overflow
            
            absorbed = min(incoming, supply)
            rem_supply = supply - absorbed
            native_sched = min(initial, rem_supply)
            
            # Identify new spillover created at this capacity level
            new_overflow = max(0, initial - rem_supply)
            global_spillover += new_overflow
            
            # Total overflow passed to the next (larger) room tier
            spill_out = (incoming - absorbed) + new_overflow
            
            # Log metrics to cumulative ledger
            cumulative_df.at[index, 'Total_Safe_Supply'] += supply
            cumulative_df.at[index, 'Total_Initial_Demand'] += initial
            cumulative_df.at[index, 'Total_Native_Scheduled'] += native_sched
            cumulative_df.at[index, 'Total_Absorbed_Spillover'] += absorbed
            current_overflow = spill_out
            
    # Calculate utilization percentage
    cumulative_df['Total_Load_Percentage'] = ((cumulative_df['Total_Native_Scheduled'] + cumulative_df['Total_Absorbed_Spillover']) / cumulative_df['Total_Safe_Supply'].replace(0, 1)) * 100
    
    # Console Reporting
    print("\n" + "-"*85)
    print(f"SYSTEM METRICS: {title} (Active Weeks: {active_weeks_count})")
    print("-"*85)
    print(f"Total Native Demand:           {cumulative_df['Total_Initial_Demand'].sum():,.2f} Room-Hours")
    print(f"Total Safe Supply:             {cumulative_df['Total_Safe_Supply'].sum():,.2f} Room-Hours")
    print(f"Total Cascading Spillover:     {global_spillover:,.2f} Room-Hours")
    
    print("\n" + "-"*85)
    print(f"TOP 5 CAPACITY BOTTLENECKS: {title}")
    print("-"*85)
    bottlenecks = cumulative_df[cumulative_df['Total_Initial_Demand'] > cumulative_df['Total_Safe_Supply']].copy()
    bottlenecks['Deficit'] = bottlenecks['Total_Initial_Demand'] - bottlenecks['Total_Safe_Supply']
    bottlenecks = bottlenecks.sort_values(by='Deficit', ascending=False).head(5)
    print(bottlenecks[['Capacity', 'Room Count', 'Total_Safe_Supply', 'Total_Initial_Demand', 'Deficit']].round(2).to_string(index=False))

    print("\n" + "-"*85)
    print(f"TOP 5 SPILLOVER ABSORPTION TIERS: {title}")
    print("-"*85)
    absorbers = cumulative_df[cumulative_df['Total_Absorbed_Spillover'] > 0].copy()
    absorbers = absorbers.sort_values(by='Total_Absorbed_Spillover', ascending=False).head(5)
    absorbers['Total_Load_%'] = absorbers['Total_Load_Percentage'].apply(lambda x: f"{x:.1f}%")
    print(absorbers[['Capacity', 'Room Count', 'Total_Safe_Supply', 'Total_Native_Scheduled', 'Total_Absorbed_Spillover', 'Total_Load_%']].round(2).to_string(index=False))

    # Visualization
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(26, 16), sharex=True)
    x = np.arange(len(cumulative_df))
    width = 0.6

    # Subplot 1: Initial Native Demand (Constraint Identification)
    ax1.bar(x, cumulative_df['Total_Initial_Demand'], width, label='Native Demand (Non-cascaded)', color='#1f77b4')
    ax1.plot(x, cumulative_df['Total_Safe_Supply'], color='red', marker='o', linestyle='-', linewidth=2.5, markersize=5, label='Safe Supply Threshold (75% Utilization)')
    
    # Highlight oversubscription
    has_label = False
    for i in range(len(cumulative_df)):
        if cumulative_df['Total_Initial_Demand'].iloc[i] > cumulative_df['Total_Safe_Supply'].iloc[i]:
            label = 'Demand Deficit (Potential Spillover)' if not has_label else ""
            has_label = True
            ax1.bar(x[i], cumulative_df['Total_Initial_Demand'].iloc[i] - cumulative_df['Total_Safe_Supply'].iloc[i], width, bottom=cumulative_df['Total_Safe_Supply'].iloc[i], color='darkred', alpha=0.8, label=label)

    ax1.set_ylabel('Required Room-Hours', fontsize=14, fontweight='bold')
    ax1.set_title(f'Baseline Native Demand vs. Realistic Safe Capacity ({title})', fontsize=18, fontweight='bold')
    ax1.legend(fontsize=14)
    ax1.grid(axis='y', linestyle='--', alpha=0.5)

    # Subplot 2: Final State (System Resolution)
    ax2.bar(x, cumulative_df['Total_Native_Scheduled'], width, label='Scheduled Native Demand', color='#1f77b4')
    ax2.bar(x, cumulative_df['Total_Absorbed_Spillover'], width, bottom=cumulative_df['Total_Native_Scheduled'], label='Absorbed Spillover (Cascaded from smaller tiers)', color='#ff7f0e', hatch='//')
    ax2.plot(x, cumulative_df['Total_Safe_Supply'], color='red', marker='o', linestyle='-', linewidth=2.5, markersize=5, label='Safe Supply Threshold')

    ax2.set_xlabel('Room Capacity (Seats)', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Scheduled Room-Hours', fontsize=14, fontweight='bold')
    ax2.set_title(f'Final System Utilization Including Spillover ({title})', fontsize=18, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(cumulative_df['Capacity'], fontsize=10, rotation=45, ha='right')
    ax2.legend(fontsize=14)
    ax2.grid(axis='y', linestyle='--', alpha=0.5)

    plt.tight_layout(pad=3.0)
    plt.savefig(filename, dpi=300)
    print(f"\nReport generated: '{filename}'")

# 4. Execution
print("\nPhase 1: Analyzing Peak Week (Week 15)...")
run_strict_simulation([15], "PEAK WEEK 15", "strict_week15_peak.png")

print("\nPhase 2: Analyzing Annual Cumulative Trends (Weeks 1-52)...")
run_strict_simulation(range(1, 53), "ANNUAL AGGREGATE", "strict_annual_full.png")

print("\nSimulation complete.")