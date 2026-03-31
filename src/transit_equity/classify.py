"""
transit_equity.classify
=======================
Core / peripheral station classification methods based on ridership.

Public API
----------
classify_percentile(df, threshold) -> pd.Series
    Stations above the given percentile threshold are "core".

classify_kmeans(df, n_clusters, random_state) -> pd.Series
    K-means on log-transformed ridership; higher centroid cluster = core.

classify_jenks(df) -> pd.Series
    Natural-breaks (Jenks) split at the single largest gap in ridership.

run_all_classifications(df) -> pd.DataFrame
    Run all three methods, add a ``consensus`` column (majority vote),
    print a summary table, and return the augmented DataFrame.

NAME_CROSSWALK : dict
    Maps raw station names from ridership CSVs to the canonical station
    names used in the amenity / spatial dataset.
"""

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

# Station name crosswalk

NAME_CROSSWALK: dict[str, str] = {
    # BART
    "12th Street / Oakland City Center":   "12th St. Oakland City Center",
    "16th Street Mission":                 "16th St. Mission",
    "19th Street Oakland":                 "19th St. Oakland",
    "24th Street Mission":                 "24th St. Mission",
    "Antioch":                             "Antioch",
    "Ashby":                               "Ashby",
    "Balboa Park":                         "Balboa Park",
    "Bayfair":                             "Bay Fair",
    "Berkeley":                            "Downtown Berkeley",
    "Berryessa / North San Jos\x8e":       "Berryessa/North San Jose",
    "Castro Valley":                       "Castro Valley",
    "Civic Center":                        "Civic Center/UN Plaza",
    "Coliseum":                            "Coliseum",
    "Colma":                               "Colma",
    "Concord":                             "Concord",
    "Daly City":                           "Daly City",
    "Dublin/Pleasanton":                   "Dublin/Pleasanton",
    "El Cerrito Del Norte":                "El Cerrito del Norte",
    "El Cerrito Plaza":                    "El Cerrito Plaza",
    "Embarcadero":                         "Embarcadero",
    "Fremont":                             "Fremont",
    "Fruitvale":                           "Fruitvale",
    "Glen Park":                           "Glen Park",
    "Hayward":                             "Hayward",
    "Lafayette":                           "Lafayette",
    "Lake Merritt":                        "Lake Merritt",
    "MacArthur":                           "MacArthur",
    "Milpitas":                            "Milpitas",
    "Montgomery Street":                   "Montgomery St.",
    "North Berkeley":                      "North Berkeley",
    "North Concord":                       "North Concord/Martinez",
    "Oakland International Airport":       "Oakland International Airport",
    "Orinda":                              "Orinda",
    "Pittsburg Center":                    "Pittsburg Center",
    "Pittsburg/Bay Point":                 "Pittsburg/Bay Point",
    "Pleasant Hill":                       "Pleasant Hill/Contra Costa Centre",
    "Powell Street":                       "Powell St.",
    "Richmond":                            "Richmond",
    "Rockridge":                           "Rockridge",
    "San Francisco International Airport": "San Francisco International Airport",
    "San Leandro":                         "San Leandro",
    "South Hayward":                       "South Hayward",
    "Union City":                          "Union City",
    "Walnut Creek":                        "Walnut Creek",
    "Warm Springs":                        "Warm Springs/South Fremont",
    "West Dublin/Pleasanton":              "West Dublin/Pleasanton",
    "West Oakland":                        "West Oakland",
    # Caltrain
    "22nd Street":   "22nd Street",
    "Bayshore":      "Bayshore",
    "Belmont":       "Belmont",
    "Blossom Hill":  "Blossom Hill Caltrain Station",
    "Broadway":      "Broadway",
    "Burlingame":    "Burlingame",
    "California Ave": "California Avenue",
    "Capitol":       "Capitol Caltrain Station",
    "College Park":  "College Park",
    "Gilroy":        "Gilroy",
    "Hayward Park":  "Hayward Park",
    "Hillsdale":     "Hillsdale",
    "Lawrence":      "Lawrence",
    "Menlo Park":    "Menlo Park",
    "Morgan Hill":   "Morgan Hill",
    "Mountain View": "Mountain View",
    "Palo Alto":     "Palo Alto",
    "Redwood City":  "Redwood City",
    "San Antonio":   "San Antonio",
    "San Carlos":    "San Carlos",
    "San Francisco": "San Francisco Caltrain Station",
    "San Jose Diridon": "San Jose Diridon",
    "San Martin":    "San Martin",
    "San Mateo":     "San Mateo",
    "Santa Clara":   "Santa Clara Caltrain Station",
    "Sunnyvale":     "Sunnyvale",
    "Tamien":        "Tamien Caltrain Station",
}

# Stations shared across agencies need agency-aware name overrides
_DUPLICATE_OVERRIDES: list[tuple[str, str, str]] = [
    # (raw station name, agency, canonical name)
    ("Millbrae",           "BART",     "Millbrae"),
    ("Millbrae",           "Caltrain", "Millbrae"),
    ("South San Francisco","BART",     "South San Francisco"),
    ("South San Francisco","Caltrain", "South San Francisco Caltrain Station"),
    ("San Bruno",          "BART",     "San Bruno"),
    ("San Bruno",          "Caltrain", "San Bruno Caltrain Station"),
]


# Classification methods

def classify_percentile(df: pd.DataFrame, threshold: float = 0.50) -> pd.Series:
    """
    Classify stations at or above *threshold* percentile as ``"core"``.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain column ``avg_weekday_exits``.
    threshold : float
        Percentile cutoff in [0, 1].  Default ``0.50`` (median).

    Returns
    -------
    pd.Series
        String series with values ``"core"`` or ``"peripheral"``.
    """
    cutoff = df["avg_weekday_exits"].quantile(threshold)
    return (df["avg_weekday_exits"] >= cutoff).map({True: "core", False: "peripheral"})


def classify_kmeans(
    df: pd.DataFrame,
    n_clusters: int = 2,
    random_state: int = 255,
) -> pd.Series:
    """
    Classify stations using K-means on log-transformed ridership.

    The cluster with the higher centroid is labelled ``"core"``.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain column ``avg_weekday_exits``.
    n_clusters : int
        Number of clusters.  Default ``2``.
    random_state : int
        Random seed for reproducibility.  Default ``255``.

    Returns
    -------
    pd.Series
        String series with values ``"core"`` or ``"peripheral"``.
    """
    X = np.log1p(df["avg_weekday_exits"].values).reshape(-1, 1)
    km = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    labels = km.fit_predict(X)
    core_label = int(np.argmax(km.cluster_centers_.flatten()))
    return pd.Series(labels).map({core_label: "core"}).fillna("peripheral")


def classify_jenks(df: pd.DataFrame) -> pd.Series:
    """
    Classify stations using natural breaks (Jenks) on ridership.

    Splits at the single largest gap in the sorted ridership distribution.
    Uses ``jenkspy`` if available, otherwise falls back to a pure-NumPy
    implementation.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain column ``avg_weekday_exits``.

    Returns
    -------
    pd.Series
        String series with values ``"core"`` or ``"peripheral"``.
    """
    try:
        import jenkspy
        breaks = jenkspy.jenks_breaks(
            df["avg_weekday_exits"].values.tolist(), n_classes=2
        )
        cutoff = breaks[1]
    except ImportError:
        sorted_vals = np.sort(df["avg_weekday_exits"].values)
        gaps = np.diff(sorted_vals)
        cutoff = sorted_vals[np.argmax(gaps) + 1]

    return (df["avg_weekday_exits"] >= cutoff).map({True: "core", False: "peripheral"})


# Ensemble / consensus

def run_all_classifications(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run all three classification methods, compute a majority-vote
    ``consensus`` label, print a summary table, and return the augmented
    DataFrame.

    A station is ``"core"`` in the consensus if at least 2 of the 3 methods
    label it as core.

    Parameters
    ----------
    df : pd.DataFrame
        Ridership table with column ``avg_weekday_exits``.

    Returns
    -------
    pd.DataFrame
        Input DataFrame with additional columns:
        ``method_percentile``, ``method_kmeans``, ``method_jenks``,
        ``core_votes``, ``consensus``.
    """
    df = df.copy()
    df["method_percentile"] = classify_percentile(df).values
    df["method_kmeans"]     = classify_kmeans(df).values
    df["method_jenks"]      = classify_jenks(df).values

    method_cols = ["method_percentile", "method_kmeans", "method_jenks"]
    df["core_votes"] = df[method_cols].apply(
        lambda r: sum(v == "core" for v in r), axis=1
    )
    df["consensus"] = df["core_votes"].apply(
        lambda v: "core" if v >= 2 else "peripheral"
    )

    # Print summary
    print(f"\n{'Method':<26} {'Core':>6} {'Peripheral':>11} {'% Core':>8}")
    print("─" * 55)
    labels = [
        "Percentile (≥50th %ile)",
        "K-means (2 clusters)",
        "Jenks (natural break)",
        "Consensus (≥2/3 methods)",
    ]
    for col, label in zip(method_cols + ["consensus"], labels):
        n_core = (df[col] == "core").sum()
        n_peri = (df[col] == "peripheral").sum()
        print(
            f"  {label:<24} {n_core:>6} {n_peri:>11} "
            f"{100 * n_core / len(df):>7.1f}%"
        )

    return df


# Name-mapping helper

def apply_name_crosswalk(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply ``NAME_CROSSWALK`` and agency-specific duplicate overrides to a
    ridership DataFrame, adding a ``station_name`` column with canonical
    station names.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns ``station`` and ``agency``.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with a new ``station_name`` column.
    """
    df = df.copy()
    df["station_name"] = df["station"].map(NAME_CROSSWALK)

    for raw_name, agency, canonical in _DUPLICATE_OVERRIDES:
        mask = (df["station"] == raw_name) & (df["agency"] == agency)
        df.loc[mask, "station_name"] = canonical

    unmapped = df[df["station_name"].isna()]
    if len(unmapped) > 0:
        print(
            f"\nWARNING: {len(unmapped)} ridership stations could not be mapped:"
        )
        print(unmapped[["station", "agency"]].to_string(index=False))
    else:
        print("\nAll ridership stations mapped successfully")

    return df