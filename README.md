# City_Planning_255
Destiny Ogu, Sonya Kiskachi, Donjhai Holland
# Bay Area Transit Equity Analysis

An analysis of amenity access disparities at BART and Caltrain stations across the Bay Area, examining whether core (high-ridership) stations serve communities with greater transit dependency than peripheral (low-ridership) stations.

## Research Question

Do peripheral BART and Caltrain stations provide statistically significantly less access to essential amenities than core, and are these disparities concentrated among stations serving transit-dependent populations?

## Data Sources

| Dataset | Source | Description |
|---|---|---|
| Census tract boundaries | TIGER/Line 2024, U.S. Census Bureau | California tract shapefiles for spatial joining |
| ACS 2024 (5-Year) | Census API | Tract-level demographics: income, vehicle access, race, poverty |
| BART ridership (FY2025) | BART monthly XLS, Jul 2024–Jun 2025 | Average weekday exits by station |
| Caltrain ridership (FY2025) | FY2025 Annual Ridership Report, Table 3 | Average mid-week ridership (AMWR) by station |
| Amenities | OpenStreetMap / compiled | Grocery, park, clinic, pharmacy, hospital, childcare locations |
| Station locations | Compiled | Lat/lon for all BART and Caltrain stations |

## Project Structure

```
City_Planning_255/
├── data/
│   ├── raw/
│   │   ├── tl_2024_06_tract/         # Census TIGER/Line shapefiles
│   │   ├── transit_gdf.csv           # Station locations
│   │   ├── all_amenities.csv         # Amenity points
│   │   └── bart_stations_ridership.csv
│   └── processed/
│       ├── census_tract_data_2024_clean.csv
│       ├── classification_results_fy2025.csv
│       ├── final_station_data.csv
│       ├── geo_info_transit.csv
│       ├── new_stations_transit_data.csv
│       ├── ridership_raw_fy2025.csv
│       ├── transit_census_info.csv
│       └── peripheral_vs_core_results.csv
├── src/
│   └── transit_equity/               # Reusable package
│       ├── __init__.py
│       ├── amenities.py              # Haversine distance, amenity counting
│       ├── census.py                 # ACS constants, derived rate calculations
│       ├── classify.py               # Core/peripheral classification methods
│       └── stats.py                  # Gini, unmet-need index, entropy
├── scripts/
│   ├── get_census_data.py            # Fetch ACS data from Census API
│   ├── core_vs_peripheral_classification.py  # Classify stations by ridership
│   └── complete_analysis_pipeline.py # Full end-to-end analysis
├── manual_scripts/
│   ├── get_census_data.py            
│   ├── core_vs_peripheral_classification.py  
│   ├── get_transit_amenity_data.py  
│   └── complete_analysis_pipeline.py
├── visualizations/
├── notebooks/
│   ├── 01_get_census_data.ipynb # Gets census data            
│   ├── 02_eda.ipynb # Initial data exploration
│   ├── 03_core_vs_peripheral.ipynb # Classification analysis
│   └── initial_transit_stat_analysis.ipynb # Initial transit analysis
├── results/
│   └── summaries.csv # Summary of statistical analysis results
├── pyproject.toml
├── requirements.txt # All versions and packages required
├── environment.yaml # Conda Environment setup
└── README.md
```

## Setup

### 1. Create and activate the conda environment

```bash
conda env create -f environment.yaml
conda activate cp255
```

### 2. Install the project package

From the project root (the folder containing `pyproject.toml`):

```bash
pip install -e .
```

This installs `transit_equity` as an editable package so all scripts can import from `src/` without path hacks. You only need to do this once.

### 3. Verify the install

```bash
pip show transit-equity
```

## Running the Analysis

```bash
python scripts/complete_analysis_pipeline.py
```

## Methods

### Station Classification

Each station is classified as **core** or **peripheral** using a consensus of three independent methods applied to FY2025 ridership data:

- **Percentile** — stations at or above the median (50% percentile) ridership are core
- **K-means** — k-means clustering (k=2) on log-transformed ridership; higher centroid = core
- **Jenks natural breaks** — splits at the largest gap in the ridership distribution

A station is labelled **core** if at least 2 of 3 methods agree.

### Amenity Access

Amenities are counted within a **half-mile radius** (804.67 m) of each station using the haversine great-circle distance formula. Categories counted: grocery, park, clinic, pharmacy, hospital, doctors, childcare.

### Statistical Tests

- **Permutation tests** (10,000 resamples) comparing core vs. peripheral amenity counts, with Benjamini-Hochberg FDR correction across five variables
- **Spearman correlations** between amenity counts and demographic variables (median income, % no vehicle, % nonwhite), with FDR correction
- **Mann-Whitney U test** comparing amenity diversity (Shannon entropy) between core and peripheral stations

### Equity Metrics

**Gini coefficient** — measures inequality in amenity distribution across all stations (0 = perfect equality, 1 = perfect inequality). Reported with 95% bootstrap confidence intervals.

**Unmet need index** — composite score combining:
- *Need percentile rank*: percentile rank of a station's % car-free households (high = more transit-dependent)
- *Supply gap*: 1 minus the percentile rank of total amenities (high = fewer amenities)

Index = need × supply gap. Stations score highest when they have both high transit dependency *and* low amenity access.

**Amenity entropy** — Shannon entropy of the amenity-type distribution at each station. Higher entropy = more diverse mix of amenity types.
