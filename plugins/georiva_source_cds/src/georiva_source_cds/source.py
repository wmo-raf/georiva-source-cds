"""
Copernicus CDS data sources for GeoRiva.

This module ships two reusable pieces plus one concrete dataset:

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

To add another CDS dataset later (e.g. ERA5), subclass CDSDataSource, set the
dataset name, and implement generate_requests(); the fetch strategy and the
zip/ensemble post-processing are reused unchanged.
"""

from __future__ import annotations

import functools
import logging
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Tuple

from georiva.sources.fetch import FileRequest
from georiva.sources.fetch.base import BaseFetchStrategy, FetchMode, FetchResult
from georiva.sources.source import BaseDataSource, DataSourceType

logger = logging.getLogger(__name__)


# =============================================================================
# Fetch strategy (reusable across all CDS datasets)
# =============================================================================

class CDSFetchStrategy(BaseFetchStrategy):
    """
    Fetch strategy backed by the Copernicus `cdsapi` client.

    Expects each FileRequest to carry, in `request.params`:
        cds_dataset : str  — the CDS dataset name (e.g. "multi-origin-c3s-atlas")
        cds_request : dict — the request body passed to client.retrieve()

    cdsapi.Client().retrieve() queues the request, waits for it to complete and
    downloads the result to the given path. That call blocks, so we report
    FetchMode.SYNC even though CDS is a queue behind the scenes — the GeoRiva
    Loader treats the whole thing as one blocking fetch, which is exactly what a
    one-off backfill wants.
    """

    type = "cds"
    label = "Copernicus CDS"

    def __init__(self, config: dict = None):
        super().__init__(config or {})
        # Allow overriding credentials via config; otherwise cdsapi reads
        # ~/.cdsapirc or the CDSAPI_URL / CDSAPI_KEY environment variables.
        self.cds_url = self.config.get("cds_url")
        self.cds_key = self.config.get("cds_key")
        self.quiet = bool(self.config.get("quiet", True))
        self._client = None

    @property
    def mode(self) -> FetchMode:
        return FetchMode.SYNC

    def connect(self) -> None:
        import cdsapi

        client_kwargs = {"quiet": self.quiet, "wait_until_complete": True}
        if self.cds_url and self.cds_key:
            client_kwargs.update(url=self.cds_url, key=self.cds_key)
        self._client = cdsapi.Client(**client_kwargs)
        self.logger.debug("CDS client initialised")

    def disconnect(self) -> None:
        self._client = None

    def fetch(self, request: FileRequest, local_path: Path) -> FetchResult:
        result = FetchResult(request=request, local_path=local_path)

        dataset = request.params.get("cds_dataset")
        cds_request = request.params.get("cds_request")
        if not dataset or not cds_request:
            result.success = False
            result.status = "failed"
            result.error = "Request is missing 'cds_dataset' or 'cds_request' params"
            return result

        if self._client is None:
            self.connect()

        local_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        try:
            self.logger.info("CDS retrieve: %s %s", dataset, request.identifier)
            self._client.retrieve(dataset, cds_request, str(local_path))

            if not local_path.exists() or local_path.stat().st_size == 0:
                result.success = False
                result.status = "failed"
                result.error = "CDS returned no data (empty file)"
                return result

            result.success = True
            result.status = "complete"
            result.bytes_transferred = local_path.stat().st_size
            result.duration_seconds = time.time() - start
            self.logger.info(
                "CDS retrieved %.1f MB in %.0fs for %s",
                result.bytes_transferred / 1024 / 1024,
                result.duration_seconds,
                request.identifier,
            )
        except Exception as exc:  # noqa: BLE001 - surface any cdsapi error
            result.success = False
            result.status = "failed"
            result.error = str(exc)
            self.logger.error("CDS retrieve failed for %s: %s", request.identifier, exc)
            if local_path.exists():
                local_path.unlink(missing_ok=True)

        return result


# =============================================================================
# Base CDS data source (reusable post-processing)
# =============================================================================

class CDSDataSource(BaseDataSource):
    """
    Base class for CDS-backed data sources.

    Subclasses set `type`, `label`, `DATASET`, and implement generate_requests().
    The download -> single-NetCDF post-processing is handled here.
    """

    DATASET: str = ""  # CDS dataset name, e.g. "multi-origin-c3s-atlas"

    # Names we treat as the ensemble dimension to collapse (mean) before raster.
    MEMBER_DIMS = ("member", "realization", "model", "gcm")

    def __init__(self, config: dict, fetch_strategy=CDSFetchStrategy):
        super().__init__(config, fetch_strategy)
        # The Loader instantiates the fetch strategy bare (no config), so bind
        # the feed-level CDS credentials here. The feed requires cds_key and
        # supplies a default cds_url, so both are normally present.
        self.fetch_strategy = functools.partial(
            fetch_strategy,
            {
                "cds_url": config.get("cds_url"),
                "cds_key": config.get("cds_key"),
            },
        )

    @property
    def source_type(self) -> DataSourceType:
        # CMIP6 projections / reanalyses from CDS are derived gridded products.
        return DataSourceType.DERIVED

    def get_latest_available(self) -> Optional[datetime]:
        # CDS climate datasets are static archives — nothing to poll.
        return None

    # -------------------------------------------------------------------------
    # Post-fetch: CDS .zip -> single rasterizable .nc (ensemble-mean)
    # -------------------------------------------------------------------------

    def post_process_fetched_file(self, request, local_path: Path) -> Tuple[Path, Optional[str]]:
        """
        Turn a raw CDS download into a clean (time, lat, lon) NetCDF:

          1. If the download is a .zip (the usual case for the C3S Atlas), extract
             the single .nc inside it.
          2. Collapse any ensemble `member` dimension to its mean (keep_attrs).
          3. Rename the main data variable to the canonical key carried in
             request.params['variable_key'] so the variable name is deterministic
             and matches the GeoRiva Variable 'source'.
          4. Drop bounds/aux variables (keep CRS) and write a fresh .nc.

        Returns (processed_path, new_filename). new_filename keeps request.filename
        (already a canonical "<key>_<experiment>.nc").
        """
        import xarray as xr

        work_dir = local_path.parent
        nc_path = self._ensure_netcdf(local_path, work_dir)

        variable_key = request.params.get("variable_key")
        out_path = work_dir / f"_processed_{request.filename}"

        ds = xr.open_dataset(nc_path, decode_coords="all")
        try:
            main_var = self._main_data_var(ds)
            da = ds[main_var]

            # 1. ensemble mean over the member dimension, if present
            member_dim = next((d for d in da.dims if d in self.MEMBER_DIMS), None)
            if member_dim:
                self.logger.info(
                    "Reducing ensemble dim '%s' (%d members) to mean for %s",
                    member_dim, da.sizes[member_dim], request.identifier,
                )
                da = da.mean(dim=member_dim, keep_attrs=True)

            # 2. canonical variable name
            if variable_key and da.name != variable_key:
                da = da.rename(variable_key)

            out = da.to_dataset()
            # preserve CRS if the source declared one (helps NetCDF plugin CRS detection)
            if "crs" in ds.variables:
                out["crs"] = ds["crs"]
                out[da.name].attrs.setdefault("grid_mapping", "crs")

            out.to_netcdf(out_path)
        finally:
            ds.close()

        # Replace the temp file the Loader will store with our processed one.
        return out_path, request.filename

    def _ensure_netcdf(self, local_path: Path, work_dir: Path) -> Path:
        """Return a path to a .nc file, extracting it from a CDS .zip if needed."""
        if zipfile.is_zipfile(local_path):
            with zipfile.ZipFile(local_path, "r") as zf:
                nc_names = [n for n in zf.namelist() if n.endswith(".nc")]
                if not nc_names:
                    raise RuntimeError(
                        f"No .nc inside CDS archive {local_path.name}: {zf.namelist()}"
                    )
                extracted = work_dir / Path(nc_names[0]).name
                with zf.open(nc_names[0]) as src, open(extracted, "wb") as dst:
                    dst.write(src.read())
                return extracted
        # Already a NetCDF
        return local_path

    @staticmethod
    def _main_data_var(ds) -> str:
        """
        Pick the primary data variable: the one with both a time-like and two
        horizontal dims (and the most dims, to prefer the science var over bnds).
        """
        candidates = []
        for name, var in ds.data_vars.items():
            dims = {d.lower() for d in var.dims}
            has_time = any("time" in d for d in dims)
            has_y = any(d in ("lat", "latitude", "y") for d in dims)
            has_x = any(d in ("lon", "longitude", "x") for d in dims)
            if has_time and has_y and has_x:
                candidates.append((len(var.dims), name))
        if not candidates:
            raise RuntimeError(
                f"No (time, lat, lon) data variable found in CDS file; "
                f"data_vars={list(ds.data_vars)}"
            )
        candidates.sort(reverse=True)
        return candidates[0][1]


# =============================================================================
# CMIP6 (C3S Interactive Climate Atlas) data source
# =============================================================================

# Period covered by each experiment, as the CDS request expects it, plus the
# valid_time we stamp on generated files (the start of the series).
_EXPERIMENT_PERIODS = {
    "historical": ("1850-2014", datetime(1850, 1, 1, tzinfo=timezone.utc)),
    "ssp1_1_9": ("2015-2100", datetime(2015, 1, 1, tzinfo=timezone.utc)),
    "ssp1_2_6": ("2015-2100", datetime(2015, 1, 1, tzinfo=timezone.utc)),
    "ssp2_4_5": ("2015-2100", datetime(2015, 1, 1, tzinfo=timezone.utc)),
    "ssp3_7_0": ("2015-2100", datetime(2015, 1, 1, tzinfo=timezone.utc)),
    "ssp5_8_5": ("2015-2100", datetime(2015, 1, 1, tzinfo=timezone.utc)),
}

_BIAS_ADJUSTMENT_MAP = {
    "none": "no_bias_adjustment",
    "ls": "linear_scaling",
    "isimip": "isimip_method",
}


class CMIP6DataSource(CDSDataSource):
    """
    CMIP6 monthly/annual climate indices from the C3S Interactive Climate Atlas.

    Static data: ignores the (start, end) time window the Loader passes and
    instead emits one request per requested variable for a single experiment.
    The experiment, area, bias-adjustment and period are supplied via config
    (the DataFeed + per-collection link).
    """

    type = "cds-cmip6"
    label = "CDS CMIP6 (C3S Atlas)"
    DATASET = "multi-origin-c3s-atlas"

    def __init__(self, config: dict, fetch_strategy=CDSFetchStrategy):
        super().__init__(config, fetch_strategy)
        self.experiment = config.get("experiment", "historical")
        self.bias_adjustment = config.get("bias_adjustment", "none")
        # area as [north, west, south, east] (CDS order); built by the feed.
        self.area = config.get("area")
        self.requested_variables = config.get("variables", [])

    @property
    def name(self) -> str:
        return "CDS CMIP6 (C3S Atlas)"

    def generate_requests(
            self,
            *_,
            variables: Optional[list[str]] = None,
            **kwargs,
    ) -> Iterator[FileRequest]:
        variables = variables or self.requested_variables
        if not variables:
            self.logger.warning("CMIP6: no variables requested; nothing to fetch")
            return

        if self.experiment not in _EXPERIMENT_PERIODS:
            raise ValueError(f"Unknown CMIP6 experiment: {self.experiment!r}")
        period, valid_time = _EXPERIMENT_PERIODS[self.experiment]
        ba_value = _BIAS_ADJUSTMENT_MAP.get(self.bias_adjustment, "no_bias_adjustment")
        ba_suffix = "" if self.bias_adjustment == "none" else f"_{self.bias_adjustment}"

        for code in variables:
            cds_request = {
                "origin": "cmip6",
                "experiment": self.experiment,
                "domain": "global",
                "period": period,
                "variable": code,
                "bias_adjustment": ba_value,
            }
            if self.area:
                cds_request["area"] = list(self.area)

            filename = f"cmip6_{code}_{self.experiment}{ba_suffix}.nc"

            yield FileRequest(
                identifier=f"cmip6-{code}-{self.experiment}{ba_suffix}",
                filename=filename,
                valid_time=valid_time,
                reference_time=None,  # static / derived, not a forecast
                params={
                    "cds_dataset": self.DATASET,
                    "cds_request": cds_request,
                    "variable_key": code,
                    "experiment": self.experiment,
                    "bias_adjustment": self.bias_adjustment,
                },
                expected_format="netcdf",
                variables=[code],
            )
