# Bay Area Transit Equity

**Does where you live near transit determine what you can access?**

Bay Area transit expansion has extended BART and Caltrain service into communities like Antioch
and Berryessa over the past decade. However, building a station does not guarantee that the surrounding
neighborhood offers basic amenities that residents may need within walking distance. 

A station that draws hundreds to thousands of daily riders but sits in a neighborhood with few nearby amenities, such 
as grocery stores, phramacies, and clincs creates compunded mobility burdens, with direct implications for
transit-oriented development and equitable service planning. The riders most affected are transit-dependent 
Bay Area residents, particularly low-income households, elderly riders, and people with disabilities, who rely on 
transit not just for commuting but for reaching daily necessities.

This project examines walkable amenity access across 79 BART and Caltrain stations in the 
Bay Area. We ask a simple question: **Do riders at peripheral stations — lower ridership, 
suburban, end-of-line — have systematically worse access to essential services like grocery 
stores, clinics, and pharmacies compared to riders at central core stations?**

## Key Findings
Our analysis finds statistically significant disparities between core and peripheral stations:
- Peripheral stations not only have fewer amenities, but also less diversity in amenities on average
- Core stations had the highest unmeet need, high car-free households and low amenity count

## Data Sources

We built this analysis primarily using FY2025 BART and Caltrain ridership records, OpenStreetMap amenity extracts, 
and 2024 ACS 5-year Census estimates. 

| Dataset | Source | Description |
|---|---|---|
| Census tract boundaries | TIGER/Line 2024, U.S. Census Bureau | California tract shapefiles for spatial joining |
| ACS 2024 (5-Year) | Census API | Tract-level demographics: income, vehicle access, race, poverty |
| BART ridership (FY2025) | BART monthly XLS, Jul 2024–Jun 2025 | Average weekday exits by station |
| Caltrain ridership (FY2025) | FY2025 Annual Ridership Report, Table 3 | Average mid-week ridership (AMWR) by station |
| Amenities | OpenStreetMap / compiled | Grocery, park, clinic, pharmacy, hospital, childcare locations |
| Station locations | Compiled | Lat/lon for all BART and Caltrain stations |

All spatial analysis was done in Python using `GeoPandas`, 
with interactive visualizations built in `Plotly` and `Folium`.

## Scope and Limitations
This analysis focuses on **amenity presence**, not affordability, quality, or availiability. A clinic within a half mile of a station may have limited hours, may not take certain insurance plans, or have long wait times. Additionally, we only examine **BART and Caltrain** stations. There are bus networks that service residents across all nine Bay Area counties, including transit-dependent populations, which is out of our scope.

**Group 13** · Sonya Kiskachi, Destiny Ogu, Donjhai Holland · CP 255 · Spring 2026

---

Use the tabs on the left to explore:
- **Findings** — interactive maps and equity analysis across all 79 stations
- **Statistical Analysis** — permutation tests, correlations, and the full methodology

```{tableofcontents}
```
