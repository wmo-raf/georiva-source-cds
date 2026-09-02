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

from datetime import date
from django import forms
from django.db import models
from django_countries.fields import CountryField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.snippets.models import register_snippet

from georiva.sources.collection_definitions import CollectionDefinition, parse_collection_defs
from georiva.sources.models import DataFeedCollectionLink, DataFeed

from . import CMIP6DataFeed
from .cmip6 import DEFAULT_CDS_URL
from .constants.era5 import COLLECTIONS, PERIOD_CHOICES


class ERA5DataFeedCollectionLink(DataFeedCollectionLink):
    """Per-collection config for a ERA5 DataFeed."""

    # Baked in from definition_key — set automatically, never shown in forms
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES)

    default_start_date = models.DateField(
        default=date(2020, 1, 1),
        help_text="Default backfill start date for this collection.",
    )

    class Meta:
        verbose_name = "ERA5 Collection Link"

    @classmethod
    def get_panels(cls):
        # 'period' is baked in from definition_key — not operator-configurable
        return [
            FieldPanel("default_start_date"),
        ]

    @property
    def config(self) -> dict:
        return {
            "period": self.period,
            "default_start_date": self.default_start_date,
        }

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keep Collection.time_resolution in sync for code that reads it directly
        if self.collection_id:
            type(self.collection).objects.filter(pk=self.collection_id).update(
                time_resolution=self.period
            )


@register_snippet
class ERA5DataFeed(CMIP6DataFeed):
    """Operator configuration for a georiva-source-era5 acquisition."""

    PRODUCT_TYPES = [
        ("r", "monthly_averaged_reanalysis"),
        ("rph", "monthly_averaged_reanalysis_by_hour_of_day"),
        # ("em", "monthly_averaged_ensemble_members"),
        # ("emph", "monthly_averaged_ensemble_members_by_hour_of_day"),
    ]

    product_type = models.CharField(
        max_length=40,
        choices=PRODUCT_TYPES,
        default="r",
    )

    panels = [
        *DataFeed.base_panels,
        FieldPanel("product_type"),
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
        MultiFieldPanel(
            [
                FieldPanel("cds_url"),
                FieldPanel("cds_key", widget=forms.PasswordInput(render_value=True)),
            ],
            heading="CDS credentials",
        ),
    ]

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
    def data_source_cls(self, source=None):
        from ..sources import ERA5DataSource
        return ERA5DataSource
    #
    # def get_loader_config(self) -> dict:
    #     """Feed-wide settings merged into the data source's config dict."""
    #     return {}

    # =========================================================================
    # Collection link
    # =========================================================================

    @classmethod
    def get_collection_link_model(cls):
        return ERA5DataFeedCollectionLink

    @classmethod
    def get_link_config_for_definition(cls, definition) -> dict:
        """Derive period from the definition key so it's never shown as an editable field."""
        periods_list = zip(*PERIOD_CHOICES)[0]
        for period in periods_list:
            if period in definition.key:
                return {'period': period}
        return {}
