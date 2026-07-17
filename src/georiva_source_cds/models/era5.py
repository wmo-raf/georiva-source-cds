"""
DataFeed for georiva-source-era5.

A `DataFeed` is the operator-facing model (registered as a Wagtail snippet).
GeoRiva auto-discovers every `DataFeed` subclass and builds its admin form and
setup wizard — you do NOT register anything in apps.py.

The plugin contract a DataFeed must satisfy:
  * get_collection_definitions() — which collections and variables this plugin
    can create (declared below as the COLLECTIONS dict).
  * get_catalog_defaults() — pre-fills the wizard's catalog step.
  * data_source_cls — the BaseDataSource (source.py) that fetches the data.
  * get_loader_config() — feed-wide settings merged into the source's config.

Optionally, a feed can declare **derived products** — layers computed from its
collections by a registered recipe (anomaly, climatology, promotion, …):
  * get_derived_products() — the list of DerivedProductDefinitions this feed
    offers (ADR-0008/0009). It is an *instance* method (a product's inputs bind
    to this feed's actual collections). See the commented skeleton at the bottom
    of the DataFeed below, and docs/plugins/derived-products.md for the full
    contract. In the chain DAG, products are edges and collections are nodes.
"""

from django import forms
from django.db import models
from django_extensions.db.models import TimeStampedModel
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.snippets.models import register_snippet
from wagtail.admin.forms import WagtailAdminModelForm

from georiva.sources.collection_definitions import CollectionDefinition, parse_collection_defs
from georiva.sources.models import DataFeed

from . import CMIP6DataFeed
from .era5_constants import COLLECTIONS


@register_snippet
class ERA5DataFeed(CMIP6DataFeed):
    """Operator configuration for a georiva-source-era5 acquisition."""

    # Add feed-wide configuration fields here (credentials, timeouts, bbox...).
    # Example:
    # head_timeout = models.IntegerField(
    #     default=20,
    #     help_text="HTTP timeout (seconds) for source requests.",
    # )

    class Meta:
        verbose_name = "ERA5 Data Feed"

    # -- plugin contract ----------------------------------------------------

    @classmethod
    def get_collection_definitions(cls) -> list[CollectionDefinition]:
        return parse_collection_defs(COLLECTIONS)

    @classmethod
    def get_catalog_defaults(cls) -> dict:
        return {
            "name": "ERA5",
            "file_format": "netcdf",   # geotiff | grib2 | netcdf
            "description": "ERA5 reanalysis over ECMWF models, from the Copernicus Climate Data Store",
        }

    @property
    def data_source_cls(self):
        from ..source import ERA5DataSource
        return ERA5DataSource
    #
    # def get_loader_config(self) -> dict:
    #     """Feed-wide settings merged into the data source's config dict."""
    #     return {}