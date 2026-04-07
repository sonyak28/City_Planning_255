# %% [markdown]
# # 🏙️ Buildings Highlighted by Nearby Amenity Count
# 
# Each **building footprint** is colored by how many amenity points fall within **100 m** of it.  
# Buildings with more amenities nearby glow bright — buildings with none stay dark.
# 
# ### Layers
# 1. **Buildings** — 3D extruded by height, colored dark→bright by amenity count
# 2. **Amenity points** — individual dots colored by category
# 3. **Station circles** — BART/Caltrain stations sized by ridership
# 4. **½-mile buffer rings** — station catchment outlines

# %% [markdown]
# ## 1. Install

# %%
!uv pip -q install "geopandas[all]" pyproj lonboard mapclassify ipywidgets overturemaps palettable requests

# %% [markdown]
# ## 2. Imports

# %%
try:
    from google.colab import output
    output.enable_custom_widget_manager()
except ImportError:
    pass

import warnings
warnings.filterwarnings('ignore', category=UserWarning)

import numpy as np
import pandas as pd
import geopandas as gpd
import requests
import overturemaps
from matplotlib.colors import Normalize
from palettable.colorbrewer.sequential import YlOrRd_9
from palettable.cartocolors.qualitative import Safe_10

from lonboard import Map, SolidPolygonLayer, ScatterplotLayer, PolygonLayer
from lonboard.basemap import MaplibreBasemap, CartoStyle
from lonboard.colormap import apply_continuous_cmap, apply_categorical_cmap
import ipywidgets as W

print('✅ Imports OK')

# %% [markdown]
# ## 3. Load data

# %%
# SF bounding box
SF_BBOX = (-122.52, 37.00, -121.55, 38.03)
BUFFER_M = 100        # metres around each amenity to count as "near" a building
HALF_MILE_M = 804     # station catchment ring
# Full Bay Area bounding box covering all BART + Caltrain stations


# ── Stations ──────────────────────────────────────────────────────────────────
stations = pd.read_csv('../data/processed/final_station_data.csv', encoding='latin-1')
stations_gdf = gpd.GeoDataFrame(
    stations,
    geometry=gpd.points_from_xy(stations['longitude'], stations['latitude']),
    crs='EPSG:4326'
)
# keep only SF stations
import shapely
sf_stations = stations_gdf.copy()
print(f'Stations: {len(sf_stations)}')


# ── Amenities ─────────────────────────────────────────────────────────────────
amenities_raw = pd.read_csv('../data/raw/all_amenities.csv', index_col=0)
# clip to SF bbox first for speed
amenities_sf = amenities_raw[
    amenities_raw['longitude'].between(-122.52, -121.55) &
    amenities_raw['latitude'].between(37.00, 38.03)
].copy()

amenities_gdf = gpd.GeoDataFrame(
    amenities_sf,
    geometry=gpd.points_from_xy(amenities_sf['longitude'], amenities_sf['latitude']),
    crs='EPSG:4326'
)
print(f'SF amenity points: {len(amenities_gdf)}')
print(amenities_gdf['category'].value_counts())

# %% [markdown]
# ## 4. Fetch SF buildings from Overture Maps

# %%
latest_release = requests.get('https://stac.overturemaps.org/catalog.json').json().get('latest')
print(f'Overture release: {latest_release}')


# Fetch buildings in two tiles to avoid timeout
bbox_north = (-122.52, 37.60, -121.55, 38.03)
bbox_south = (-122.52, 37.00, -121.55, 37.60)

bldgs_n = overturemaps.core.geodataframe('building', bbox=bbox_north, release=latest_release).set_crs(4326)
bldgs_s = overturemaps.core.geodataframe('building', bbox=bbox_south, release=latest_release).set_crs(4326)

buildings_gdf = pd.concat([bldgs_n, bldgs_s], ignore_index=True)
buildings_gdf['height_clean'] = buildings_gdf['height'].fillna(4.0).clip(lower=1.0)
print(f'Buildings: {len(buildings_gdf):,}')

buildings_gdf.to_parquet('bay_area_buildings.parquet')
print('✅ Buildings saved')

# buildings_gdf = overturemaps.core.geodataframe(
#     'building', bbox=SF_BBOX, release=latest_release
# ).set_crs(4326)

# buildings_gdf['height_clean'] = buildings_gdf['height'].fillna(4.0).clip(lower=1.0)
# print(f'Buildings: {len(buildings_gdf):,}')


# %% [markdown]
# ## 5. Count amenities near each building
# 
# We buffer each **amenity point** by `BUFFER_M` metres, then spatial-join to buildings.  
# Each building receives the **count of distinct amenity points** whose buffer overlaps its footprint.

# %%
# Project to metres (California Albers)
CRS_M = 'EPSG:3310'
buildings_m  = buildings_gdf[['height_clean', 'geometry']].to_crs(CRS_M).reset_index(drop=True)
amenities_m  = amenities_gdf[['category', 'name', 'geometry']].to_crs(CRS_M)

# Buffer amenity points
amenity_buffers = amenities_m.copy()
amenity_buffers['geometry'] = amenities_m.geometry.buffer(BUFFER_M)

# Spatial join: building index → amenity rows that overlap
joined = gpd.sjoin(
    buildings_m.reset_index().rename(columns={'index': 'bldg_idx'}),
    amenity_buffers[['category', 'geometry']],
    how='left',
    predicate='intersects'
)

# Count amenities per building
amenity_counts = (
    joined
    .groupby('bldg_idx')['index_right']
    .count()
    .rename('amenity_count')
)

buildings_m['amenity_count'] = amenity_counts.reindex(buildings_m.index).fillna(0).astype(int)
buildings_plot = buildings_m.to_crs('EPSG:4326')

n_highlighted = (buildings_plot['amenity_count'] > 0).sum()
print(f'Buildings with ≥1 nearby amenity: {n_highlighted:,} / {len(buildings_plot):,}')
print(buildings_plot['amenity_count'].describe().round(1))

# %% [markdown]
# ## 6. Color buildings by amenity count

# %%
counts = buildings_plot['amenity_count'].to_numpy(dtype=float)

# Use log scale so 1-amenity buildings aren't swamped by high-count ones
from matplotlib.colors import LogNorm
norm = LogNorm(vmin=1, vmax=max(counts.max(), 2), clip=True)
normed = np.where(counts > 0, norm(np.maximum(counts, 1)), 0.0)

building_colors = apply_continuous_cmap(normed, YlOrRd_9, alpha=220)
# apply_continuous_cmap returns RGB (3 cols) — match the shape when overriding
if building_colors.shape[1] == 3:
    building_colors[counts == 0] = [30, 30, 40]
else:
    building_colors[counts == 0] = [30, 30, 40, 160] # dark/invisible for zero-count buildings

print('Color array ready')

# %% [markdown]
# ## 7. Color amenity points by category

# %%
CATEGORY_ORDER = [
    'park', 'grocery', 'convenience', 'clinic',
    'pharmacy', 'doctors', 'hospital', 'childcare', 'kindergartens'
]
palette = (np.array(Safe_10.mpl_colors[:len(CATEGORY_ORDER)]) * 255).astype(np.uint8)
cat_color_map = {cat: palette[i].tolist() for i, cat in enumerate(CATEGORY_ORDER)}

amenities_gdf['category'] = amenities_gdf['category'].astype('string').fillna('park')
amenity_categorical = amenities_gdf['category'].astype(
    pd.CategoricalDtype(categories=CATEGORY_ORDER)
)
amenity_colors = apply_categorical_cmap(amenity_categorical, cat_color_map, alpha=230)

# %% [markdown]
# ## 8. Station & buffer layers

# %%
AGENCY_COLORS = {'BART': [0, 140, 255, 240], 'Caltrain': [255, 80, 80, 240]}

station_colors = np.array(
    [AGENCY_COLORS.get(a, [180, 180, 180, 200]) for a in sf_stations['agency']],
    dtype=np.uint8
)
ridership = sf_stations['ridership'].fillna(sf_stations['ridership'].median()).to_numpy()
r_norm = (ridership - ridership.min()) / (ridership.max() - ridership.min() + 1e-9)
station_radii = (r_norm * 200 + 80).astype(float)

# ½-mile buffers
buffers = sf_stations.to_crs(CRS_M).copy()
buffers['geometry'] = buffers.geometry.buffer(HALF_MILE_M)
buffers = buffers.to_crs('EPSG:4326')
buf_outline = np.array(
    [AGENCY_COLORS.get(a, [180, 180, 180, 200]) for a in buffers['agency']],
    dtype=np.uint8
)
buf_fill = buf_outline.copy(); buf_fill[:, 3] = 12

# %% [markdown]
# ## 9. Render the map

# %%
try:
    map_kwargs = {'basemap': MaplibreBasemap(style=CartoStyle.DarkMatter)}
except Exception:
    map_kwargs = {'basemap_style': 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'}

# Layer 1 — Buildings highlighted by amenity count
bldg_layer = SolidPolygonLayer.from_geopandas(
    buildings_plot[['height_clean', 'amenity_count', 'geometry']],
    extruded=True,
    get_elevation=buildings_plot['height_clean'].to_numpy(),
    elevation_scale=1.0,
    get_fill_color=building_colors,
    get_line_color=[20, 20, 20, 30],
    wireframe=False,
    pickable=True,
)

# Layer 2 — ½-mile rings
ring_layer = PolygonLayer.from_geopandas(
    buffers,
    get_fill_color=buf_fill,
    get_line_color=buf_outline,
    line_width_min_pixels=1.5,
    pickable=False,
)

# Layer 3 — Individual amenity points
amenity_layer = ScatterplotLayer.from_geopandas(
    amenities_gdf,
    get_fill_color=amenity_colors,
    get_radius=60,
    radius_min_pixels=3,
    radius_max_pixels=9,
    pickable=True,
    opacity=0.9,
)

# Layer 4 — Stations
station_layer = ScatterplotLayer.from_geopandas(
    sf_stations,
    get_fill_color=station_colors,
    get_radius=station_radii,
    radius_min_pixels=7,
    radius_max_pixels=20,
    get_line_color=[255, 255, 255, 220],
    line_width_min_pixels=1.5,
    stroked=True,
    pickable=True,
    opacity=1.0,
)

m = Map(
    layers=[bldg_layer, ring_layer, amenity_layer, station_layer],
    height=780,
    **map_kwargs
)
m.set_view_state(longitude=-122.419, latitude=37.775, zoom=9, pitch=55, bearing=-15)

print('✅ Map ready')

# %% [markdown]
# ## 10. Legend + display

# %%
import ipywidgets as W

def rgb_hex(rgb): return '#{:02x}{:02x}{:02x}'.format(*rgb[:3])

def legend(title, items, note=''):
    rows = ''.join(
        f'<div style="display:flex;align-items:center;margin:3px 0">'
        f'<span style="width:11px;height:11px;border-radius:3px;background:{c};'
        f'border:1px solid #fff3;margin-right:7px;flex-shrink:0"></span>'
        f'<span style="font-size:11px;color:#ddd">{l}</span></div>'
        for l, c in items
    )
    note_html = f'<p style="font-size:10px;color:#aaa;margin-top:5px;margin-bottom:0">{note}</p>' if note else ''
    return W.HTML(f"""
    <div style="background:#111827;border:1px solid #ffffff22;border-radius:10px;
                padding:10px 14px;font-family:system-ui,sans-serif;margin:0 6px 0 0">
      <div style="font-weight:700;font-size:10px;text-transform:uppercase;
                  letter-spacing:.06em;color:#f0f0f0;margin-bottom:7px">{title}</div>
      {rows}{note_html}
    </div>""")

bldg_legend = legend(
    'Buildings — nearby amenity count',
    [('0  (dark)', '#1e1e28'), ('Low', '#ffffb2'), ('Medium', '#fd8d3c'), ('High', '#bd0026')],
    note='Height = actual building height · Log scale'
)
amenity_legend = legend(
    'Amenity type',
    [(cat, rgb_hex(cat_color_map[cat])) for cat in CATEGORY_ORDER]
)
station_legend = legend(
    'Station  (size = ridership)',
    [('BART', '#008cff'), ('Caltrain', '#ff5050')],
    note='Ring = ½-mile (804 m) catchment'
)

W.VBox([W.HBox([bldg_legend, amenity_legend, station_legend]), m])

# %% [markdown]
# ## 11. Export to HTML

# %%
m.set_view_state(longitude=-122.419, latitude=37.775, zoom=9, pitch=55, bearing=-15)
m.to_html('sf_amenity_buildings.html', title='SF Buildings Highlighted by Amenity Count')
print('✅ Saved: sf_amenity_buildings.html')

# %% [markdown]
# ---
# ## Appendix A — Filter to one amenity category
# Swap `FILTER_CATEGORY` to see which buildings are near only that type of amenity.

# %%
FILTER_CATEGORY = 'grocery'  # change to: park, clinic, pharmacy, convenience, etc.

# Re-run the count for just this category
amenity_buffers_cat = amenities_m[amenities_m['category'] == FILTER_CATEGORY].copy()
amenity_buffers_cat['geometry'] = amenity_buffers_cat.geometry.buffer(BUFFER_M)

joined_cat = gpd.sjoin(
    buildings_m.reset_index().rename(columns={'index': 'bldg_idx'}),
    amenity_buffers_cat[['geometry']],
    how='left', predicate='intersects'
)
cat_counts = joined_cat.groupby('bldg_idx')['index_right'].count().rename('cat_count')
buildings_m['cat_count'] = cat_counts.reindex(buildings_m.index).fillna(0).astype(int)
buildings_cat = buildings_m.to_crs('EPSG:4326')

cat_vals = buildings_cat['cat_count'].to_numpy(dtype=float)
if cat_vals.max() > 0:
    norm_cat = LogNorm(vmin=1, vmax=max(cat_vals.max(), 2), clip=True)
    normed_cat = np.where(cat_vals > 0, norm_cat(np.maximum(cat_vals, 1)), 0.0)
else:
    normed_cat = np.zeros_like(cat_vals)

cat_bldg_colors = apply_continuous_cmap(normed_cat, YlOrRd_9, alpha=220)
if cat_bldg_colors.shape[1] == 3:
    cat_bldg_colors[cat_vals == 0] = [30, 30, 40]
else:
    cat_bldg_colors[cat_vals == 0] = [30, 30, 40, 130]

cat_bldg_layer = SolidPolygonLayer.from_geopandas(
    buildings_cat[['height_clean', 'cat_count', 'geometry']],
    extruded=True,
    get_elevation=buildings_cat['height_clean'].to_numpy(),
    get_fill_color=cat_bldg_colors,
    wireframe=False, pickable=True,
)

# Only show amenity points for this category
cat_amenities = amenities_gdf[amenities_gdf['category'] == FILTER_CATEGORY].copy()
cat_dot_color = np.tile(
    np.array(cat_color_map.get(FILTER_CATEGORY, [255,255,255]) + [240], dtype=np.uint8),
    (len(cat_amenities), 1)
)
cat_amenity_layer = ScatterplotLayer.from_geopandas(
    cat_amenities, get_fill_color=cat_dot_color,
    get_radius=80, radius_min_pixels=4, radius_max_pixels=12, pickable=True
)

m_cat = Map(
    layers=[cat_bldg_layer, ring_layer, cat_amenity_layer, station_layer],
    height=700, **map_kwargs
)
m_cat.set_view_state(longitude=-122.419, latitude=37.775, zoom=9, pitch=55, bearing=-15)

header = W.HTML(
    f'<div style="background:#111827;color:#eee;padding:8px 14px;border-radius:8px;'
    f'font-family:system-ui;font-size:13px;margin-bottom:6px">'
    f'Buildings near: <b>{FILTER_CATEGORY}</b> '
    f'({(cat_vals>0).sum():,} buildings lit · {len(cat_amenities)} amenity points)</div>'
)
W.VBox([header, m_cat])


