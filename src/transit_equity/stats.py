"""
transit_equity.stats
====================
Statistical helper functions used in the transit equity analysis.

Public API
----------
calculate_gini(values) -> float
    Gini coefficient of a 1-D array (0 = equality, 1 = inequality).

bootstrap_gini(values, n_bootstrap, ci) -> tuple[float, float]
    Bootstrap confidence interval for the Gini coefficient.

add_unmet_need_index(df) -> pd.DataFrame
    Append ``need_pct``, ``supply_pct``, ``supply_gap``, and
    ``unmet_need_index`` columns to the station DataFrame.

amenity_entropy(row) -> float
    Shannon entropy of the amenity-type distribution for one station row.
"""

import numpy as np
import pandas as pd
from scipy.stats import entropy, rankdata


# Gini coefficient

def calculate_gini(values: np.ndarray) -> float:
    """
    Compute the Gini coefficient for a 1-D array of non-negative values.

    The Gini coefficient measures inequality:
    * 0 → perfect equality (all stations have the same count)
    * 1 → perfect inequality (one station has everything)

    Parameters
    ----------
    values : array-like
        Non-negative numeric values (e.g. amenity counts per station).

    Returns
    -------
    float
        Gini coefficient, or ``nan`` if *values* is empty.
    """
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return np.nan
    sorted_values = np.sort(values)
    cumsum = np.cumsum(sorted_values)
    return (
        (2 * np.sum(np.arange(1, n + 1) * sorted_values)) / (n * cumsum[-1])
        - (n + 1) / n
    )


def bootstrap_gini(
    values: np.ndarray,
    n_bootstrap: int = 1_000,
    ci: float = 95,
) -> tuple[float, float]:
    """
    Bootstrap confidence interval for the Gini coefficient.

    Parameters
    ----------
    values : array-like
        Non-negative numeric values.
    n_bootstrap : int
        Number of bootstrap resamples.  Default ``1000``.
    ci : float
        Confidence level as a percentage (e.g. ``95`` for 95 % CI).

    Returns
    -------
    tuple[float, float]
        (lower bound, upper bound) of the bootstrap CI.
    """
    values = np.asarray(values, dtype=float)
    bootstrapped = [
        calculate_gini(
            np.random.choice(values, size=len(values), replace=True)
        )
        for _ in range(n_bootstrap)
    ]
    alpha = (100 - ci) / 2
    lower = np.percentile(bootstrapped, alpha)
    upper = np.percentile(bootstrapped, 100 - alpha)
    return lower, upper


# Unmet-need index

def add_unmet_need_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append unmet-need columns to the station DataFrame.

    The unmet-need index is the product of:
    * **need_pct** – percentile rank of ``pct_no_vehicle`` (high = more need)
    * **supply_gap** – 1 minus the percentile rank of ``total_amenities``
      (high = fewer amenities)

    A station scores high only when it has *both* high car-free rates *and*
    low amenity access.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns ``pct_no_vehicle`` and ``total_amenities``.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with four new columns appended:
        ``need_pct``, ``supply_pct``, ``supply_gap``, ``unmet_need_index``.
    """
    df = df.copy()
    n = len(df)
    df["need_pct"]   = rankdata(df["pct_no_vehicle"].fillna(0)) / n
    df["supply_pct"] = rankdata(df["total_amenities"]) / n
    df["supply_gap"] = 1 - df["supply_pct"]
    df["unmet_need_index"] = df["need_pct"] * df["supply_gap"]
    return df


# Amenity diversity (entropy)

def amenity_entropy(row: pd.Series) -> float:
    """
    Compute the Shannon entropy of the amenity-type distribution for a
    single station row.

    A higher entropy means a more *diverse* mix of amenity types around
    the station (e.g. groceries + parks + clinics) rather than one dominant
    type.

    Parameters
    ----------
    row : pd.Series
        Must contain keys ``grocery``, ``park``, ``clinic``,
        ``pharmacy``, and ``childcare``.

    Returns
    -------
    float
        Shannon entropy (nats), or ``0.0`` if no amenities are present.
    """
    counts = [
        row["grocery"],
        row["park"],
        row["clinic"],
        row["pharmacy"],
        row["childcare"],
        row["convenience"],
        row['kindergarten'],
        row['hospital'],
        row['doctors']
    ]
    counts = [c for c in counts if c > 0]
    return float(entropy(counts)) if counts else 0.0