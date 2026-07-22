
PERIOD_CHOICES = [
    ("monthly", "Monthly"),
    # ("hourly", "Hourly"),
]

# ---------------------------------------------------------------------------
# Collections this plugin can create — the canonical spec for the plugin.
# One entry per collection; each lists the variables it exposes.
#
#   time_resolution : one of sub_hourly, hourly, 3hourly, 6hourly, 12hourly,
#                     daily, pentadal, dekadal, monthly, seasonal, annual, ...
#   variables[].source : how the variable is located in the raw file, e.g. a
#                     GeoTIFF band name ("band_1"), or a GRIB short-name / level
#                     dict. See the georiva-source-* reference plugins.
# ---------------------------------------------------------------------------

from .era5_single_levels import collection_era5_single_levels_monthly
from .era5_land import collection_era5_land_monthly
from .era5_pressure_levels import collection_era5_pressure_levels_monthly

COLLECTIONS = {
    ds["dataset_id"]: ds for ds in [collection_era5_single_levels_monthly, collection_era5_land_monthly, collection_era5_pressure_levels_monthly]
}
