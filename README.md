# Bay Area Transit Equity

CP 255 Final Project — Spring 2026  
Sonya Kiskachi, Destiny Ogu, Donjhai Holland

## Setup

```bash
pip install -r requirements.txt
```

## Running the notebooks

Notebooks must be run in this order:

1. `notebooks/data_collection.ipynb` — pulls OSM and Census data
2. `notebooks/processing.ipynb` — cleans and joins datasets  
3. `transit_equity_book/transit_equity_visualization.ipynb` — Station Access Explorer
4. `transit_equity_book/findings.ipynb` — Findings page
5. `transit_equity_book/statistical_results.ipynb` — Methods & Results

## Building the book

```bash
jupyter book build transit_equity_book/
```

## Data

Raw data is in `data/raw/` and is read-only. Processed data is in 
`data/processed/`. Do not overwrite raw files programmatically.

Datasets larger than 50MB are not committed. See `data/raw/README.md` 
for download instructions.

## Live site

https://sonyak28.github.io/City_Planning_255/