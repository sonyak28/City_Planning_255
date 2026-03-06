"""
Clean Census Data - Fix Negative/Invalid Values
Run this after the pipeline to clean up data quality issues
"""

import pandas as pd
import numpy as np

print("="*80)
print("CLEANING CENSUS DATA")
print("="*80)

# Load the data
df = pd.read_csv("../data/final_results/final_station_data.csv")

print(f"\nLoaded {len(df)} stations")

# ============================================================
# IDENTIFY ISSUES
# ============================================================

print("\n1. IDENTIFYING DATA QUALITY ISSUES")
print("-"*80)

issues_found = []

# Check for negative income
neg_income = df[df['median_income'] < 0]
if len(neg_income) > 0:
    print(f"⚠️  {len(neg_income)} stations with negative median income")
    issues_found.append('negative_income')
    print(neg_income[['station_name', 'median_income', 'GEOID']].head())

# Check for extreme outliers in income
income_valid = df[(df['median_income'] > 0) & (df['median_income'] < 500000)]
if len(income_valid) < len(df):
    print(f"\n⚠️  {len(df) - len(income_valid)} stations with extreme income values")
    issues_found.append('extreme_income')

# Check for invalid percentages
invalid_pct_noveh = df[(df['pct_no_vehicle'] < 0) | (df['pct_no_vehicle'] > 100)]
if len(invalid_pct_noveh) > 0:
    print(f"\n⚠️  {len(invalid_pct_noveh)} stations with invalid % no vehicle")
    issues_found.append('invalid_pct_noveh')

invalid_pct_nonwhite = df[(df['pct_nonwhite'] < 0) | (df['pct_nonwhite'] > 100)]
if len(invalid_pct_nonwhite) > 0:
    print(f"\n⚠️  {len(invalid_pct_nonwhite)} stations with invalid % nonwhite")
    issues_found.append('invalid_pct_nonwhite')

# Check for missing GEOID
missing_geoid = df[df['GEOID'].isna()]
if len(missing_geoid) > 0:
    print(f"\n⚠️  {len(missing_geoid)} stations missing GEOID (census tract)")
    issues_found.append('missing_geoid')

if not issues_found:
    print("\n✓ No data quality issues found!")
    exit()

# ============================================================
# FIX ISSUES
# ============================================================

print("\n\n2. FIXING DATA QUALITY ISSUES")
print("-"*80)

df_clean = df.copy()

# Fix negative/extreme income values
# Strategy: Replace with NaN (will be excluded from analysis)
mask_bad_income = (df_clean['median_income'] < 10000) | (df_clean['median_income'] > 500000)
n_bad_income = mask_bad_income.sum()

if n_bad_income > 0:
    print(f"\nFixing {n_bad_income} invalid income values...")
    print("Stations affected:")
    print(df_clean[mask_bad_income][['station_name', 'median_income', 'GEOID']])
    
    df_clean.loc[mask_bad_income, 'median_income'] = np.nan
    print("→ Set to NaN (will be excluded from income correlations)")

# Fix invalid percentages
mask_bad_pct = (
    (df_clean['pct_no_vehicle'] < 0) | (df_clean['pct_no_vehicle'] > 100) |
    (df_clean['pct_nonwhite'] < 0) | (df_clean['pct_nonwhite'] > 100)
)
n_bad_pct = mask_bad_pct.sum()

if n_bad_pct > 0:
    print(f"\nFixing {n_bad_pct} invalid percentage values...")
    df_clean.loc[mask_bad_pct, ['pct_no_vehicle', 'pct_nonwhite']] = np.nan
    print("→ Set to NaN")

# ============================================================
# ALTERNATIVE: RE-FETCH CENSUS DATA FOR BAD TRACTS
# ============================================================

if 'negative_income' in issues_found:
    print("\n\n3. INVESTIGATING PROBLEMATIC CENSUS TRACTS")
    print("-"*80)
    
    bad_tracts = df_clean[mask_bad_income]['GEOID'].dropna().unique()
    
    print(f"\nProblematic GEOIDs: {list(bad_tracts)}")
    print("\nPossible causes:")
    print("  1. Census API returned error code (-666666666 = missing data)")
    print("  2. Tract has suppressed data (very small population)")
    print("  3. Tract is industrial/unpopulated area")
    print("\nFor these stations, demographics will be excluded from analysis.")

# ============================================================
# RECALCULATE SUMMARY STATS
# ============================================================

print("\n\n4. RECALCULATED SUMMARY STATISTICS")
print("-"*80)

core_clean = df_clean[df_clean['station_type'] == 'core']
peri_clean = df_clean[df_clean['station_type'] == 'peripheral']

print(f"\nCore stations (n={len(core_clean)}):")
print(f"  Mean % no vehicle:  {core_clean['pct_no_vehicle'].mean():.2f}%")
print(f"  Mean median income: ${core_clean['median_income'].mean():,.0f}")
print(f"  Mean % nonwhite:    {core_clean['pct_nonwhite'].mean():.2f}%")

print(f"\nPeripheral stations (n={len(peri_clean)}):")
print(f"  Mean % no vehicle:  {peri_clean['pct_no_vehicle'].mean():.2f}%")
print(f"  Mean median income: ${peri_clean['median_income'].mean():,.0f}")
print(f"  Mean % nonwhite:    {peri_clean['pct_nonwhite'].mean():.2f}%")

# ============================================================
# SAVE CLEANED DATA
# ============================================================

print("\n\n5. SAVING CLEANED DATA")
print("-"*80)

# Save cleaned version
df_clean.to_csv("../data/final_results/final_station_data_CLEANED.csv", index=False)
print("✓ Saved: ../data/final_results/final_station_data_CLEANED.csv")

# Also save just stations with valid demographics
df_valid = df_clean.dropna(subset=['median_income', 'pct_no_vehicle', 'pct_nonwhite'])
df_valid.to_csv("../data/final_results/stations_valid_demographics.csv", index=False)
print(f"✓ Saved: ../data/final_results/stations_valid_demographics.csv ({len(df_valid)} stations)")

# ============================================================
# RECOMMENDATIONS
# ============================================================

print("\n\n" + "="*80)
print("RECOMMENDATIONS")
print("="*80)

n_invalid = len(df) - len(df_valid)

if n_invalid > 5:
    print(f"""
⚠️  {n_invalid} stations have invalid/missing census data

OPTIONS:

1. EXCLUDE FROM DEMOGRAPHIC ANALYSIS (RECOMMENDED)
   - Use cleaned data for correlations with demographics
   - Peripheral vs Core comparison still uses all {len(df)} stations
   - Only demographic correlations use {len(df_valid)} stations with valid data
   
2. MANUAL LOOKUP
   - Look up GEOIDs on censusreporter.org
   - Manually enter correct values
   - Only worth it if <5 stations affected

3. INVESTIGATE SPATIAL JOIN
   - Check if stations are in weird locations (water, borders)
   - May need to manually assign correct census tracts

CURRENT STATUS:
✓ Your main finding (peripheral vs core) is unaffected
✓ Use 'final_station_data_CLEANED.csv' for any demographic analysis
✓ Report: "Demographic data available for {len(df_valid)}/{len(df)} stations"
""")
else:
    print(f"""
✓ Only {n_invalid} stations have missing/invalid data - ACCEPTABLE

Use 'final_station_data_CLEANED.csv' for final analysis.
Report: "Demographic analysis based on {len(df_valid)} stations with valid census data"
""")

print("="*80)
