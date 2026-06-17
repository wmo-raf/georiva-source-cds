"""
CMIP6 (C3S Interactive Climate Atlas) DataFeed for GeoRiva.

Modelling choices
-----------------
* A **Collection** corresponds to one (experiment x time-resolution) pairing,
  e.g. "CMIP6 SSP2-4.5 (Monthly)". The experiment is baked into the collection
  via its definition key (the operator never edits it directly), mirroring how
  the CHIRPS plugin bakes in its period.
* The **DataFeed** holds the things common to a whole acquisition: the spatial
  subset (country preset or explicit bbox) and the bias-adjustment choice.
* Variables are the C3S Atlas climatic-impact-driver indices, grouped in the
  wizard by category (heat & cold, wet & dry, drought, ...).

The data itself is static (historical 1850-2014, scenarios 2015-2100), so this
feed is meant to be provisioned once and run as a backfill rather than on a
schedule.
"""

from dataclasses import dataclass

from django.db import models
from django_countries.fields import CountryField
from django_countries_geoextent import get_country_extent
from django_extensions.db.models import TimeStampedModel
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.snippets.models import register_snippet

from georiva.sources.collection_definitions import CollectionDefinition, parse_collection_defs
from georiva.sources.models import DataFeed, DataFeedCollectionLink


# ---------------------------------------------------------------------------
# Variable catalogue — C3S Atlas v2.5 (CMIP6 origin)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VariableDef:
    code: str  # CDS variable name (also the in-file var name after rename)
    label: str  # Human-readable
    units: str  # Best-known units (actual units are read from the file at ingest)
    cid: str  # Climatic Impact Driver category
    resolution: str  # "monthly" | "yearly" (derived from the code prefix)


def _res(code: str) -> str:
    return "yearly" if code.startswith("annual_") else "monthly"


def _v(code, label, units, cid) -> VariableDef:
    return VariableDef(code, label, units, cid, _res(code))


VARIABLES: list[VariableDef] = [
    # Heat and cold
    _v("monthly_temperature", "Mean temperature", "degC", "heat_cold"),
    _v("monthly_daily_minimum_temperature", "Min temperature", "degC", "heat_cold"),
    _v("monthly_daily_maximum_temperature", "Max temperature", "degC", "heat_cold"),
    _v("monthly_daily_temperature_range", "Temperature range", "degC", "heat_cold"),
    _v("monthly_maximum_of_daily_maximum_temperature", "Max of max temperature", "degC", "heat_cold"),
    _v("monthly_extreme_hot_days", "Extreme hot days (>35C)", "days", "heat_cold"),
    _v("monthly_very_extreme_hot_days", "Very extreme hot days (>40C)", "days", "heat_cold"),
    _v("monthly_tropical_nights", "Tropical nights (>20C)", "days", "heat_cold"),
    _v("annual_cooling_degree_days", "Cooling degree-days", "degC day", "heat_cold"),
    _v("monthly_minimum_of_daily_minimum_temperature", "Min of min temperature", "degC", "heat_cold"),
    _v("monthly_frost_days", "Frost days (<0C)", "days", "heat_cold"),
    _v("annual_heating_degree_days", "Heating degree-days", "degC day", "heat_cold"),
    # Wet and dry
    _v("monthly_precipitation", "Precipitation", "mm", "wet_dry"),
    _v("monthly_wet_days", "Wet days (>1mm)", "days", "wet_dry"),
    _v("monthly_precipitation_intensity", "Precipitation intensity", "mm", "wet_dry"),
    _v("monthly_maximum_1_day_precipitation", "Max 1-day precipitation", "mm", "wet_dry"),
    _v("monthly_maximum_5_day_precipitation", "Max 5-day precipitation", "mm", "wet_dry"),
    _v("monthly_heavy_precipitation_days", "Heavy precip days (>10mm)", "days", "wet_dry"),
    _v("monthly_very_heavy_precipitation_days", "Very heavy precip days (>20mm)", "days", "wet_dry"),
    _v("monthly_near_surface_specific_humidity", "Near-surface specific humidity", "g kg-1", "wet_dry"),
    _v("monthly_evaporation", "Evaporation", "mm", "wet_dry"),
    _v("monthly_runoff", "Runoff", "mm", "wet_dry"),
    # Drought
    _v("monthly_soil_moisture_in_upper_soil_portion", "Soil moisture", "kg m-2", "drought"),
    _v("annual_maximum_consecutive_dry_days", "Consecutive dry days", "days", "drought"),
    _v("monthly_standardised_precipitation_index_for_6_months_cumulation_period", "SPI-6", "Dimensionless", "drought"),
    _v("monthly_standardised_precipitation_evapotranspiration_index_for_6_months_cumulation_period", "SPEI-6",
       "Dimensionless", "drought"),
    _v("monthly_daily_accumulated_potential_evapotranspiration", "Potential evapotranspiration", "mm", "drought"),
    # Wind and radiation
    _v("monthly_wind_speed", "Wind speed", "m s-1", "wind_radiation"),
    _v("monthly_cloud_cover_percentage", "Cloud cover", "%", "wind_radiation"),
    _v("monthly_surface_solar_radiation_downwards", "Surface solar radiation", "W m-2", "wind_radiation"),
    _v("monthly_surface_thermal_radiation_downwards", "Surface thermal radiation", "W m-2", "wind_radiation"),
    # Snow and ice
    _v("monthly_snowfall_precipitation", "Snowfall", "mm", "snow_ice"),
    _v("monthly_sea_ice_area_percentage", "Sea ice area", "%", "snow_ice"),
    # Ocean
    _v("monthly_sea_surface_temperature", "Sea surface temperature", "degC", "ocean"),
    # Circulation
    _v("monthly_sea_level_pressure", "Sea level pressure", "hPa", "circulation"),
]

# Optional sensible display ranges (others left unset so palettes auto-scale).
_VALUE_RANGES = {
    "monthly_temperature": (-20.0, 45.0),
    "monthly_daily_minimum_temperature": (-25.0, 35.0),
    "monthly_daily_maximum_temperature": (-15.0, 55.0),
    "monthly_precipitation": (0.0, 500.0),
    "monthly_sea_surface_temperature": (-2.0, 35.0),
}

_CID_LABELS = {
    "heat_cold": "Heat & Cold",
    "wet_dry": "Wet & Dry",
    "drought": "Drought",
    "wind_radiation": "Wind & Radiation",
    "snow_ice": "Snow & Ice",
    "ocean": "Ocean",
    "circulation": "Circulation",
}
_CID_ORDER = list(_CID_LABELS.keys())

# Experiments (CDS value, display label). Periods are resolved in source.py.
EXPERIMENTS = [
    ("historical", "Historical"),
    ("ssp1_1_9", "SSP1-1.9"),
    ("ssp1_2_6", "SSP1-2.6"),
    ("ssp2_4_5", "SSP2-4.5"),
    ("ssp3_7_0", "SSP3-7.0"),
    ("ssp5_8_5", "SSP5-8.5"),
]

# (definition-key slug, display label, Collection.time_resolution value)
_RESOLUTIONS = [
    ("monthly", "Monthly", "monthly"),
    ("annual", "Annual", "yearly"),
]


def _build_collections() -> dict:
    """Build one collection per (experiment x resolution)."""
    collections: dict = {}
    for exp_code, exp_label in EXPERIMENTS:
        for res_slug, res_label, res_value in _RESOLUTIONS:
            vars_in = [v for v in VARIABLES if v.resolution == res_value]
            if not vars_in:
                continue
            
            variables = []
            for v in vars_in:
                var = {
                    "key": v.code,
                    "name": v.label,
                    "units": v.units,
                    "source": v.code,  # post-processing renames the in-file var to this
                }
                if v.code in _VALUE_RANGES:
                    var["value_range"] = _VALUE_RANGES[v.code]
                variables.append(var)
            
            groups = []
            for cid in _CID_ORDER:
                keys = [v.code for v in vars_in if v.cid == cid]
                if keys:
                    groups.append({
                        "key": f"{cid}",
                        "name": _CID_LABELS[cid],
                        "variable_keys": keys,
                    })
            
            collections[f"cmip6-{exp_code}-{res_slug}"] = {
                "name": f"CMIP6 {exp_label} ({res_label})",
                "time_resolution": res_value,
                "description": f"CMIP6 {exp_label} climate indices ({res_label.lower()}), "
                               f"C3S Interactive Climate Atlas, ensemble mean.",
                "variables": variables,
                "groups": groups,
            }
    return collections


COLLECTIONS = _build_collections()

BIAS_ADJUSTMENT_CHOICES = [
    ("none", "None (raw)"),
    ("ls", "Linear scaling"),
    ("isimip", "ISIMIP method"),
]


# ---------------------------------------------------------------------------
# Per-collection link — bakes in the experiment (not operator-editable)
# ---------------------------------------------------------------------------

class CMIP6DataFeedCollectionLink(DataFeedCollectionLink):
    """Per-collection config: the CMIP6 experiment, derived from the definition key."""
    
    experiment = models.CharField(max_length=20)
    
    class Meta:
        verbose_name = "CMIP6 Collection Link"
    
    @classmethod
    def get_panels(cls):
        # Experiment is baked in from the definition key — nothing to configure.
        return []
    
    @property
    def config(self) -> dict:
        return {"experiment": self.experiment}


# ---------------------------------------------------------------------------
# DataFeed
# ---------------------------------------------------------------------------

@register_snippet
class CMIP6DataFeed(DataFeed, TimeStampedModel):
    """
    CMIP6 (C3S Atlas) loader profile.

    Spatial subset and bias-adjustment are feed-level; the experiment is chosen
    by which collections the operator provisions in the wizard.
    """
    
    country = CountryField(
        blank=True,
        help_text="Country to subset to. Its bounding box is resolved automatically "
                  "via django-countries-geoextent. Leave blank to use a custom bounding "
                  "box below, or neither for the full global domain.",
    )
    north = models.FloatField(null=True, blank=True, help_text="North latitude (custom bbox; overrides country).")
    south = models.FloatField(null=True, blank=True, help_text="South latitude (custom bbox; overrides country).")
    west = models.FloatField(null=True, blank=True, help_text="West longitude (custom bbox; overrides country).")
    east = models.FloatField(null=True, blank=True, help_text="East longitude (custom bbox; overrides country).")
    
    bias_adjustment = models.CharField(
        max_length=10,
        choices=BIAS_ADJUSTMENT_CHOICES,
        default="none",
        help_text="Bias-adjustment variant. 'None' (raw) is recommended and supported by all variables.",
    )
    
    panels = [
        *DataFeed.base_panels,
        MultiFieldPanel(
            [FieldPanel("country")],
            heading="Spatial subset — country",
        ),
        MultiFieldPanel(
            [
                FieldPanel("north"),
                FieldPanel("south"),
                FieldPanel("west"),
                FieldPanel("east"),
            ],
            heading="Spatial subset — custom bounding box (optional, overrides country)",
        ),
        # Not shown for now.
        # MultiFieldPanel(
        #     [FieldPanel("bias_adjustment")],
        #     heading="Bias adjustment",
        # ),
    ]
    
    class Meta:
        verbose_name = "CMIP6 Data Feed"
    
    # -- spatial subset -----------------------------------------------------
    
    @property
    def bbox(self) -> dict | None:
        """
        Resolve the spatial subset, in priority order:
          1. an explicit custom bounding box (all four fields set), then
          2. the selected country's extent via django-countries-geoextent, else
          3. None (full global domain).
        """
        if None not in (self.north, self.south, self.west, self.east):
            return {"north": self.north, "south": self.south, "west": self.west, "east": self.east}
        if self.country:
            extent = get_country_extent(self.country.alpha3)  # [west, south, east, north]
            if extent:
                w, s, e, n = extent
                return {"north": n, "south": s, "west": w, "east": e}
        return None
    
    @property
    def area(self) -> list[float] | None:
        """CDS 'area' order: [north, west, south, east]."""
        b = self.bbox
        if not b:
            return None
        return [b["north"], b["west"], b["south"], b["east"]]
    
    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        # A partial custom bbox is ambiguous — require all four or none.
        provided = [v is not None for v in (self.north, self.south, self.west, self.east)]
        if any(provided) and not all(provided):
            raise ValidationError(
                "A custom bounding box requires all four of north, south, west and east "
                "(or leave them all blank to use the selected country)."
            )
    
    # -- framework hooks ----------------------------------------------------
    
    @classmethod
    def get_collection_definitions(cls) -> list[CollectionDefinition]:
        return parse_collection_defs(COLLECTIONS)
    
    @classmethod
    def get_collection_link_model(cls):
        return CMIP6DataFeedCollectionLink
    
    @classmethod
    def get_link_config_for_definition(cls, definition) -> dict:
        """Derive the experiment from the definition key (cmip6-<experiment>-<res>)."""
        key = definition.key
        for exp_code, _label in EXPERIMENTS:
            if key.startswith(f"cmip6-{exp_code}-"):
                return {"experiment": exp_code}
        return {}
    
    @classmethod
    def get_catalog_defaults(cls) -> dict:
        return {
            "name": "CMIP6 (C3S Atlas)",
            "file_format": "netcdf",
            "description": "CMIP6 climate projections from the Copernicus Interactive "
                           "Climate Atlas (ensemble mean), subset to the configured area.",
        }
    
    @classmethod
    def get_wizard_defaults(cls) -> dict:
        return {"country": "KE", "bias_adjustment": "none"}
    
    @property
    def data_source_cls(self):
        from .source import CMIP6DataSource
        return CMIP6DataSource
    
    def get_loader_config(self) -> dict:
        return {
            "area": self.area,
            "bias_adjustment": self.bias_adjustment,
        }
