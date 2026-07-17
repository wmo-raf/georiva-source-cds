
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
COLLECTIONS = {
    "era5_monthly_single_levels": {
        "name": "ERA5 monthly data on single levels",
        "time_resolution": "monthly",
        # "default_interval_minutes": 1440,   # pre-fills the collection's schedule
        "variables": [
            {
                "key": "2t",
                "name": "2m Temperature",
                "source_units": "K",
                "output_units": "degC",
                "source_variable": "2m_temperature",
            },
            {
                "key": "2d",
                "name": "2m Dewpoint Temperature",
                "source_units": "K",
                "output_units": "degC",
                "source_variable": "2m_dewpoint_temperature",
            },
            {
                "key": "mx2t",
                "name": "Maximum 2m Temperature Since Previous Post-processing",
                "source_units": "K",
                "output_units": "degC",
                "source_variable": "maximum_2m_temperature_since_previous_post_processing",
            },
            {
                "key": "mn2t",
                "name": "Minimum 2m Temperature Since Previous Post-processing",
                "source_units": "K",
                "output_units": "degC",
                "source_variable": "minimum_2m_temperature_since_previous_post_processing",
            },
            {
                "key": "sst",
                "name": "Sea Surface Temperature",
                "source_units": "K",
                "output_units": "degC",
                "source_variable": "sea_surface_temperature",
            },
            {
                "key": "skt",
                "name": "Skin Temperature",
                "source_units": "K",
                "output_units": "degC",
                "source_variable": "skin_temperature",
            },
            # Ice temperature layers 1–4
            *[{
                "key": f"istl{i}",
                "name": f"Ice Temperature Layer {i}",
                "source_units": "K",
                "output_units": "degC",
                "source_variable": f"ice_temperature_layer_{i}",
            } for i in range(1, 5)],
            {
                "key": "msl",
                "name": "Mean Sea Level Pressure",
                "source_units": "Pa",
                "output_units": "hPa",
                "source_variable": "mean_sea_level_pressure",
            },
            {
                "key": "sp",
                "name": "Surface Pressure",
                "source_units": "Pa",
                "output_units": "hPa",
                "source_variable": "surface_pressure",
            },
            {
                "key": "100u",
                "name": "100m U-Component of Wind",
                "source_units": "m s**-1",
                "source_variable": "100m_u_component_of_wind",
            },
            {
                "key": "100v",
                "name": "100m V-Component of Wind",
                "source_units": "m s**-1",
                "source_variable": "100m_v_component_of_wind",
            },
            {
                "key": "10u",
                "name": "10m U-Component of Wind",
                "source_units": "m s**-1",
                "source_variable": "10m_u_component_of_wind",
            },
            {
                "key": "10v",
                "name": "10m V-Component of Wind",
                "source_units": "m s**-1",
                "source_variable": "10m_v_component_of_wind",
            },
            {
                "key": "u10n",
                "name": "10m U-Component of Neutral Wind",
                "source_units": "m s**-1",
                "source_variable": "10m_u_component_of_neutral_wind",
            },
            {
                "key": "v10n",
                "name": "10m V-Component of Neutral Wind",
                "source_units": "m s**-1",
                "source_variable": "10m_v_component_of_neutral_wind",
            },
            {
                "key": "10fg",
                "name": "10m Wind Gust Since Previous Post-processing",
                "source_units": "m s**-1",
                "source_variable": "10m_wind_gust_since_previous_post_processing",
            },
            {
                "key": "i10fg",
                "name": "Instantaneous 10m Wind Gust",
                "source_units": "m s**-1",
                "source_variable": "instantaneous_10m_wind_gust",
            },
        ],
        "groups": [
            {
                "key": "temperature",
                "name": "Temperature and pressure",
                "variable_keys": ["2t", "2d", "mx2t", "mn2t", "sst", "skt",
                                   "istl1", "istl2", "istl3", "istl4", "msl", "sp"],
            },
            {
                "key": "wind",
                "name": "Wind",
                "variable_keys": ["100u", "100v", "10u", "10v", "u10n", "v10n",
                                   "10fg", "i10fg"],
            },
        ],
    },
}