_PRESSURE_LEVELS =  [
        "1", "2", "3",
        "5", "7", "10",
        "20", "30", "50",
        "70", "100", "125",
        "150", "175", "200",
        "225", "250", "300",
        "350", "400", "450",
        "500", "550", "600",
        "650", "700", "750",
        "775", "800", "825",
        "850", "875", "900",
        "925", "950", "975",
        "1000"
    ]

def _pl_source(name, level):
    """Source dict for a pressure level."""
    return {
        "name": name,
        "level": {
            "type": "pressure",
            "value": level,
            "dimension": "isobaricInhPa",
            "unit": "hPa"
        }
    }

def _pl_vars(base_key, base_name, source_units, value_range=None, output_units=None):
    """Generate one variable dict per pressure level."""
    v = [
        {
            "key": f"{base_key}_{lv}",
            "name": f"{base_name} at {lv} hPa",
            "source_units": source_units,
            "source_variable": _pl_source(base_key, lv),
            **({"output_units": output_units} if output_units else {}),
            **({"value_range": value_range} if value_range else {}),
        }
        for lv in _PRESSURE_LEVELS
    ]
    return v

_PL_VARS = [
    ("d",    "Divergence",                       "s**-1",              None,       None,       "divergence"),
    ("cc",   "Fraction of Cloud Cover",          "(0 - 1)",            None,       None,       "fraction_of_cloud_cover"),
    ("z",    "Geopotential",                     "m**2 s**-2",         None,       None,       "geopotential"),
    ("o3",   "Ozone Mass Mixing Ratio",          "kg kg**-1",          None,       None,       "ozone_mass_mixing_ratio"),
    ("pv",   "Potential Vorticity",              "K m**2 kg**-1 s**-1",None,       None,       "potential_vorticity"),
    ("r",    "Relative Humidity",                "%",                  None,       None,       "relative_humidity"),
    ("ciwc", "Specific Cloud Ice Water Content", "kg kg**-1",          None,       None,       "specific_cloud_ice_water_content"),
    ("clwc", "Specific Cloud Liquid Water Content","kg kg**-1",        None,       None,       "specific_cloud_liquid_water_content"),
    ("q",    "Specific Humidity",                "kg kg**-1",          None,       "g kg**-1", "specific_humidity"),
    ("crwc", "Specific Rain Water Content",      "kg kg**-1",          None,       None,       "specific_rain_water_content"),
    ("cswc", "Specific Snow Water Content",      "kg kg**-1",          None,       None,       "specific_snow_water_content"),
    ("t",    "Temperature",                      "K",                  None,       "degC",     "temperature"),
    ("u",    "U-Component of Wind",              "m s**-1",            None,       None,       "u_component_of_wind"),
    ("v",    "V-Component of Wind",              "m s**-1",            None,       None,       "v_component_of_wind"),
    ("w",    "Vertical Velocity",                "Pa s**-1",           None,       None,       "vertical_velocity"),
    ("vo",   "Vorticity",                        "s**-1",              None,       None,       "vorticity"),
]

collection_era5_pressure_levels_monthly = {
    "name": "ERA5 monthly averaged data on pressure levels from 1940 to present",
    "time_resolution": "monthly",
    "variables": [
        # dynamically added below
    ],
    "groups": [
        {
            "key": f"pl-{lv}",
            "name": f"{lv} hPa",
            "variable_keys": [f"{base_key}_{lv}" for base_key, *_ in _PL_VARS],
        }
        for lv in _PRESSURE_LEVELS
    ],
}

variables = []
for base_key, base_name, source_units, value_range, output_units, _ in _PL_VARS:
    v = _pl_vars(base_key, base_name, source_units, value_range, output_units)
    variables += v
collection_era5_pressure_levels_monthly["variables"] = variables

