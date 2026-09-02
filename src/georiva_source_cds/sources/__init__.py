"""
Copernicus CDS data sources for GeoRiva.

This package ships two reusable pieces plus two concrete datasets:

  CDSFetchStrategy
      A fetch strategy that wraps the official `cdsapi` client. `cdsapi`
      submits a request to the CDS queue and blocks until the result is ready,
      then downloads it — so from GeoRiva's point of view this behaves as a
      (slow) synchronous fetch. Credentials are read by `cdsapi.Client()` from
      ~/.cdsapirc or the CDSAPI_URL / CDSAPI_KEY environment variables.

  CDSDataSource
      Base class for any CDS-backed source. Knows how to turn a CDS download
      (which usually arrives as a .zip containing one .nc) into a single
      rasterizable NetCDF: it extracts the .nc, collapses any ensemble `member`
      dimension to the ensemble mean, and renames the data variable to a stable
      canonical name so downstream provisioning/ingestion is deterministic.

  CMIP6DataSource
      The C3S Interactive Climate Atlas CMIP6 dataset (`multi-origin-c3s-atlas`,
      origin=cmip6). Static climate projections — there is no "latest" to poll;
      it emits one request per (variable, experiment) and is intended to be run
      once as a backfill.

  ERA5DataSource
      The ERA5 dataset. ERA5 is produced using 4D-Var data assimilation and
      model forecasts in CY41R2 of the ECMWF Integrated Forecast System (IFS),
      with 137 hybrid sigma/pressure (model) levels.
      https://confluence.ecmwf.int/spaces/CKB/pages/76414402/ERA5+data+documentation#heading-Introduction

To add another CDS dataset later (e.g. ERA5), subclass CDSDataSource, set the
dataset name, and implement generate_requests(); the fetch strategy and the
zip/ensemble post-processing are reused unchanged.
"""

from .cds_data_source import CDSFetchStrategy, CDSDataSource
from .cmip6_data_source import CMIP6DataSource
from .era5_data_source import ERA5DataSource