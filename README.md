# TAOR

## Project Overview
This repository contains the complete suite of Python scripts developed for the Data Preparation and Baseline Analysis of our project.

The primary purpose of this repository is to clean raw university timetabling datasets, extract exact physical space constraints, and run advanced week-by-week capacity simulations. These scripts establish the empirical baseline required to determine whether Holyrood's teaching demand can be successfully reallocated to the Central campus.

## Repository Structure

The repository is divided into two modules: **Data Extraction** and **Baseline Simulation**.

### Part 1: Data Extraction Modules
These scripts are responsible for cleaning and mining the raw timetable and estate databases.

* **`extract_target_data.py` (Teaching Demand Extraction)**
  * **Functionality:** Filters the raw university timetable to isolate target modules, event sizes, durations, and weekly occurrences for designated campuses.
  * **Business Value:** Constructs the precise "demand" side of our capacity equation, accurately quantifying the teaching hours that require relocation.

* **`extract_room_info.py` (Room Capacity Extraction)**
  * **Functionality:** Queries the master room database to extract room IDs, exact seating capacities, and room types for the target campus, while actively cleaning null values.
  * **Business Value:** Provides the absolute "supply" side of our equation, ensuring the model references true physical capacities rather than only currently scheduled rooms.

* **`distance_matrix.py` (Distance Matrix Generation)**
  * **Functionality:** Transforms raw, point-to-point cross-campus travel logs into a structured 2D matrix using `pandas.pivot_table`.
  * **Business Value:** Allows the allocation algorithm to instantly verify if a student has enough time to commute between consecutive classes, turning travel feasibility into a strict algorithmic rule.

### Part 2: Baseline Simulation Modules
These scripts contain our core analytical models and generate the evidence base for our feasibility report.

* **`Capacity_Check.py` (Waterfall Capacity Engine)**
  * **Functionality:** Implements an exact-capacity matching algorithm. It strictly enforces a 75% weekly utilization limit (safety buffer) and applies a "waterfall" logic where small classes are allowed to spill over into larger available rooms once small rooms are full.
  * **Business Value:** Proves whether Central campus can absorb the displaced classes under realistic, strict operational constraints without splitting large cohorts.

* **`weekly_spillover.py` (Time-Series Bottleneck Analysis)**
  * **Functionality:** Abandons traditional annual averages to run a strict 52-week discrete-time simulation. It calculates demand and classroom spillover on a week-by-week basis.
  * **Business Value:** Eliminates the "ghost capacity" illusion caused by quiet holiday periods. It successfully isolates and visualizes mid-semester bottlenecks (e.g., peak teaching weeks), providing the Timetabling Team with actionable risk-management data.

## Stress Testing

* **`stress_test.py`**
  * **Functionality:** Performs demand stress testing by scaling timetable demand while keeping room supply fixed, then reports failure rate and objective metrics at each load level.
  * **Inputs:** Processed demand, room capacity, clash matrix, and campus distance matrix.
  * **Outputs:** CSV summary and PNG trend chart in `results/`.

### Reproducibility Commands

* Coarse scan (`1.00x` to `4.50x`, step `0.25`):
  * `python stress_test.py --scenario local --start 1.00 --end 4.50 --step 0.25 --tag heuristic_method_local_100_450_s25`
* Fine scan around the critical region:
  * `python stress_test.py --scenario local --start 2.80 --end 4.00 --step 0.05 --tag heuristic_method_local_280_400_s05_combined`

### Presentation Result Files

The following stress-test outputs are kept for presentation and report use:

* `results/stress_test_heuristic_method_local_100_450_s25.csv`
* `results/stress_test_heuristic_method_local_100_450_s25.png`
* `results/stress_test_heuristic_method_local_280_400_s05_combined.csv`
* `results/stress_test_heuristic_method_local_280_400_s05_combined.png`
