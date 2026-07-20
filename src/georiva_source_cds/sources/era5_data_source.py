
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
from . import CDSDataSource, CDSFetchStrategy

logger = logging.getLogger(__name__)

class ERA5DataSource(CDSDataSource):
    """
    ERA5 monthly/annual climate indices.

    Static data: ignores the (start, end) time window the Loader passes and
    instead emits one request per requested variable for a single experiment.
    """

    type = "cds-era5"
    label = "CDS ERA5"
    DATASET = "reanalysis-era5-single-levels-monthly-means"
    # Set default start to now -5 years. Should not be used if the corresponding Field is displayed in the form
    default_start_date = datetime(datetime.now().year - 5, 1, 1, tzinfo=timezone.utc)

    def __init__(self, config: dict, fetch_strategy=CDSFetchStrategy):
        super().__init__(config, fetch_strategy)
        # area as [north, west, south, east] (CDS order); built by the feed.
        self.area = config.get("area")
        self.requested_variables = config.get("variables", [])
        if "default_start_date" in config.keys():
            self.default_start_date = config.get("default_start_date")

    def get_default_start_date(self, *, collection=None) -> datetime:
        default_start_date = self.default_start_date

        if default_start_date:
            return datetime.combine(default_start_date, datetime.min.time())

        # 2 months before today
        now = datetime.now(timezone.utc)
        default_start_date = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=60)

        return default_start_date

    @property
    def name(self) -> str:
        return self.label

    def _month_start(self, dt: datetime) -> datetime:
        dt = _as_utc(dt)
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _iter_months(self, start: datetime, end: datetime) -> Iterator[datetime]:
        cur = self._month_start(start)
        end_m = self._month_start(end)
        while cur <= end_m:
            yield cur
            y, m = cur.year, cur.month
            cur = cur.replace(year=y + 1, month=1) if m == 12 else cur.replace(month=m + 1)

    def get_latest_available(self) -> Optional[datetime]:
        """
        Try to discover latest file by probing backwards.
        Prefer pentadal if enabled, fall back to monthly.
        """
        return datetime(year=2026, month=6, day=1, tzinfo=timezone.utc)

    def generate_requests(
            self,
            start_time: datetime,
            end_time: datetime,
            variables: Optional[list[str]] = None,
            **kwargs,
    ) -> Iterator[FileRequest]:
        variables = variables or self.requested_variables
        if not variables:
            self.logger.warning(f"{self.label}: no variables requested; nothing to fetch")
            return

        start_time = _as_utc(start_time)
        end_time = _as_utc(end_time)
        logger.info("ERA5 request: %s %s", variables, (start_time, end_time))
        for code in variables:
            for dt in self._iter_months(start_time, end_time):
                logger.info("ERA5 request: %s %s", code, dt)
                cds_request = {
                    "variable": code,
                    "data_format": "netcdf",
                    "download_format": "zip",
                    "year": [dt.year],
                    "month": [dt.month],
                    "time": [dt.strftime("%H:%M")],
                }
                if self.area:
                    cds_request["area"] = list(self.area)

                ts = _ts_for_filename(dt)
                identifier = f"{self.DATASET}_{code}_{ts}"

                yield FileRequest(
                    identifier=identifier,
                    filename=f"{identifier}.zip",
                    valid_time=dt,
                    reference_time=None,  # static / derived, not a forecast
                    params={
                        "cds_dataset": self.DATASET,
                        "cds_request": cds_request,
                        "variable_key": code,
                    },
                    expected_format="netcdf",
                    variables=[code],
                )


def _as_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _ts_for_filename(dt: datetime) -> str:
    # Your GeoTIFFFormatPlugin parses "YYYY-MM-DDTHH:MM:SS" (no trailing Z)
    dt = _as_utc(dt)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")
