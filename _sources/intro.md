# Bay Area Transit Equity

**Does where you live near transit determine what you can access?**

Bay Area transit expansion has extended BART and Caltrain service into communities like Antioch
and Berryessa over the past decade. However, building a station does not guarantee that the surrounding
neighborhood offers basic amenities that residents may need within walking distance.

A station that draws hundreds to thousands of daily riders but sits in a neighborhood with few nearby
amenities — such as grocery stores, pharmacies, and clinics — creates compounded mobility burdens,
with direct implications for transit-oriented development and equitable service planning. The riders
most affected are transit-dependent Bay Area residents, particularly low-income households, elderly
riders, and people with disabilities, who rely on transit not just for commuting but for reaching daily necessities.

This project examines walkable amenity access across 79 BART and Caltrain stations in the
Bay Area. We ask a simple question: **Do riders at peripheral stations — lower ridership,
suburban, end-of-line — have systematically worse access to essential services like grocery
stores, clinics, and pharmacies compared to riders at central core stations?**

## Key Findings

Our analysis finds statistically significant disparities between core and peripheral stations:

```{raw} html
<div class="finding-card f1">
  <div class="finding-num">Finding 01</div>
  Peripheral stations average <strong>9.8 amenities</strong> within walking 
  distance versus <strong>21.9 for core stations</strong> — a gap that held 
  across 6 of 10 amenity types after correcting for multiple comparisons 
  (Glass Delta = 2.17).
</div>
<div class="finding-card f2">
  <div class="finding-num">Finding 02</div>
  The stations with the highest unmet need — where car-free household rates are 
  high and walkable amenities are scarce — are concentrated in East Oakland and 
  the outer East Bay, with Coliseum station ranking worst (index = 0.801).
</div>
<div class="finding-card f3">
  <div class="finding-num">Finding 03</div>
  Stations in majority non-white neighborhoods have significantly fewer walkable 
  amenities (Spearman rho = −0.243, p = 0.047). Income was not a significant 
  predictor, meaning the gap follows racial geography more than income alone.
</div>
```

## Data Sources

We built this analysis primarily using FY2025 BART and Caltrain ridership records, OpenStreetMap amenity extracts, and 2024 ACS 5-year Census estimates.

```{raw} html
<div class="table-wrap">
  <table>
    <thead>
      <tr><th>Dataset</th><th>Source</th><th>Description</th></tr>
    </thead>
    <tbody>
      <tr>
        <td>Census tract boundaries</td>
        <td>TIGER/Line 2024, U.S. Census Bureau</td>
        <td>California tract shapefiles for spatial joining</td>
      </tr>
      <tr>
        <td>ACS 2024 (5-Year)</td>
        <td>Census API</td>
        <td>Tract-level demographics: income, vehicle access, race, poverty</td>
      </tr>
      <tr>
        <td>BART ridership (FY2025)</td>
        <td>BART monthly XLS, Jul 2024–Jun 2025</td>
        <td>Average weekday exits by station</td>
      </tr>
      <tr>
        <td>Caltrain ridership (FY2025)</td>
        <td>FY2025 Annual Ridership Report, Table 3</td>
        <td>Average mid-week ridership (AMWR) by station</td>
      </tr>
      <tr>
        <td>Amenities</td>
        <td>OpenStreetMap / compiled</td>
        <td>Grocery, park, clinic, pharmacy, hospital, childcare locations</td>
      </tr>
      <tr>
        <td>Station locations</td>
        <td>Compiled</td>
        <td>Lat/lon for all BART and Caltrain stations</td>
      </tr>
    </tbody>
  </table>
</div>
```

All spatial analysis was done in Python using `GeoPandas`, with interactive visualizations built in `Plotly` and `Folium`.

## Scope and Limitations

This analysis focuses on **amenity presence**, not affordability, quality, or availability.
A clinic within a half mile of a station may have limited hours, may not take certain insurance plans,
or have long wait times. Additionally, we only examine **BART and Caltrain** stations.
There are bus networks that service residents across all nine Bay Area counties, including
transit-dependent populations, which is out of our scope.

---

**Group 13** · Sonya Kiskachi, Destiny Ogu, Donjhai Holland · CP 255 · Spring 2026

---

```{tableofcontents}
```
