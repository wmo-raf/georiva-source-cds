
# =============================================================================
# ERA5 (CDS, ECMWF reanalysis) data source
# =============================================================================

from __future__ import annotations

import cdsapi
import logging
from datetime import datetime, timezone, timedelta
from typing import Iterator, Optional

from georiva.sources.fetch import FileRequest
from . import CDSDataSource, CDSFetchStrategy

logger = logging.getLogger(__name__)

class ERA5DataSource(CDSDataSource):
    """
    ERA5 monthly climate indices.
    ERA5 also provides hourly datasets, but they are not implemented yet.
    """

    type = "cds-era5"
    label = "CDS ERA5"
    # TODO: determine dynamically for each variable being requested. Can be any of the 3 collections
    # Maybe georiva should pass the collection id to generate_requests function
    DEFAULT_DATASET = "reanalysis-era5-single-levels-monthly-means"
    # Set default start to now -5 years. Should not be used if the corresponding Field is displayed in the form
    default_start_date: datetime = datetime(datetime.now().year - 5, 1, 1, tzinfo=timezone.utc)
    MAX_LOOKBACK_MONTHS = 5

    def __init__(self, config: dict, fetch_strategy=CDSFetchStrategy):
        super().__init__(config, fetch_strategy)
        # area as [north, west, south, east] (CDS order); built by the feed.
        self.area = config.get("area")
        self.requested_variables = config.get("variables", [])
        self.product_type = config.get("product_type", "monthly_averaged_reanalysis")
        if "default_start_date" in config.keys():
            logger.info(f"ERA5: default_start_date: {config.get('default_start_date')}")
            dt = config.get("default_start_date")
            if isinstance(dt, datetime):
                self.default_start_date = dt

    def get_default_start_date(self, *, collection=None) -> datetime:
        return self.default_start_date.replace(hour=0, minute=0, second=0, microsecond=0)

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
        Try to discover most recent dataset available online by probing backwards.
        The resource fetched for this exploration is hardcoded.
        """
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        for i in range(self.MAX_LOOKBACK_MONTHS):
            dt = current_month - timedelta(days=i*31)
            dataset = "reanalysis-era5-single-levels-monthly-means"
            request = {
                "product_type": ["monthly_averaged_reanalysis"],
                "variable": ["mean_sea_level_pressure"],
                "year": [dt.year],
                "month": [dt.month],
                "time": ["00:00"],
                "data_format": "netcdf",
                "download_format": "zip"
            }
            client = cdsapi.Client()
            response = client.retrieve(dataset, request)
            if response.status_code == 200:
                return datetime(year=dt.year, month=dt.month, day=1, tzinfo=timezone.utc)
        return None

    def generate_requests_for_collection(
            self,
            collection,
            **kwargs,
    ) -> Iterator[FileRequest]:
        start_time, end_time = self.get_time_window(collection=collection)
        data_variables = collection.source_variables_list()
        logger.info(f"############ERA5 collection: {collection.to_json()}")
        return self.generate_requests(
            start_time=start_time,
            end_time=end_time,
            variables=data_variables,
            collection_id=collection.slug,
            **kwargs,
        )

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
        logger.info(f"&&&&&&&&&&&&&& collectionid: {kwargs.get('collection_id')}")
        ds = kwargs.get("collection_id", self.DEFAULT_DATASET)

        start_time = _as_utc(start_time)
        end_time = _as_utc(end_time)
        logger.info("ERA5 request: %s %s %s", variables, (start_time, end_time), kwargs)
        # TODO: extract and add the pressure-level var for pressure collection
        for code in variables:
            for dt in self._iter_months(start_time, end_time):
                logger.info("ERA5 request: %s %s", code, dt)
                cds_request = {
                    "product_type": [self.product_type],
                    "variable": code,
                    "data_format": "netcdf",
                    # "download_format": "unarchived",
                    "download_format": "zip",
                    "year": [dt.year],
                    "month": [dt.month],
                    "time": [dt.strftime("%H:%M")],
                }
                logger.info("&&&&&&&&&&ERA5 request: %s", cds_request)

                if self.area:
                    cds_request["area"] = list(self.area)

                ts = _ts_for_filename(dt)
                identifier = f"{ds}_{code}_{ts}"

                yield FileRequest(
                    identifier=identifier,
                    filename=f"{identifier}.zip",
                    valid_time=dt,
                    reference_time=None,  # static / derived, not a forecast
                    params={
                        "cds_dataset": ds,
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
