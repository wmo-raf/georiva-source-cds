
# =============================================================================
# ERA5 (CDS, ECMWF reanalysis) data source
# =============================================================================

from __future__ import annotations

import cdsapi
import logging
from datetime import datetime, timezone, timedelta, date
from dateutil.relativedelta import relativedelta
from typing import Iterator, Optional

from georiva.sources.fetch import FileRequest
from . import CDSDataSource, CDSFetchStrategy
from ..models.constants import era5 as era5_constants

logger = logging.getLogger(__name__)


def _extract_pressure_levels(collection):
    pressure_levels = set()
    for item in collection.variables.all():
        chunks = item.slug.rsplit("_")
        pressure_levels.add(chunks[1])
    return list(pressure_levels)


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
        logger.info(f"ERA5 config keys: {config}")
        # TODO: find out how to get the pressure levels list. ECMWF supposedly gets it at this stage, but how ?
        self.product_type = config.get("product_type", "monthly_averaged_reanalysis")
        if "default_start_date" in config.keys():
            dt = config.get("default_start_date")
            if isinstance(dt, datetime):
                self.default_start_date = dt
            elif isinstance(dt, date):
                self.default_start_date = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
            else:
                logger.warning(f"Invalid default start date: {dt} ({type(dt)})")


    def get_default_start_date(self, *, collection=None) -> datetime:
        return self.default_start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    def get_default_end_date(self, *, collection=None) -> datetime:
        """
        Data is available only until previous month (at first day of the month
        """
        n = datetime.now(timezone.utc)
        return datetime(year=n.year, month=n.month-1, day=1, tzinfo=timezone.utc)

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
            cur = cur + relativedelta(months=+1)

    def advance_start_from_latest(self, latest: datetime, *, collection=None) -> datetime:
        """
        Avoid refetching same period when using db latest.
        Very simple for now since we only support monthly data

        Called by BaseDataSource.get_time_window()
        Uses collection.time_resolution to move to the NEXT period.
        """
        latest = _as_utc(latest)
        return datetime(year=latest.year, month=latest.month+1, day=1, tzinfo=timezone.utc)

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

        pressure_levels = []
        if "pressure-levels" in collection.slug:
            pressure_levels = _extract_pressure_levels(collection)
            logger.info(f"ERA5 pressure_levels: {pressure_levels}")

        return self.generate_requests(
            start_time=start_time,
            end_time=end_time,
            variables=data_variables,
            collection_id=collection.slug,
            pressure_levels=pressure_levels,
            **kwargs,
        )

    def generate_requests(
            self,
            start_time: datetime,
            end_time: datetime,
            variables: Optional[list[str]] = None,
            **kwargs,
    ) -> Iterator[FileRequest]:
        """
        Generates the requests for the CDS services.

        In the case when we are dealing with the pressure-levels collection, we have to split the variable ids to extract:
        - pressure level
        - variable name

        TODO: try to keep it as a single request including
                - time range (years, months)
                - variables range
                - pressure levels if dealing with pressure levels collection
            But since FileRequest declares specific `"variable_key": code,` and `valid_time=dt,`
            this might require quite some changes in cds_data_source `post_process_fetched_file` function

        """
        variables = variables or self.requested_variables
        if not variables:
            self.logger.warning(f"{self.label}: no variables requested; nothing to fetch")
            return
        logger.debug(f"&&&&&&&&&&&&&& collectionid: {kwargs.get('collection_id')}")
        ds = kwargs.get("collection_id", self.DEFAULT_DATASET)

        start_time = _as_utc(start_time)
        end_time = _as_utc(end_time)
        logger.debug("ERA5 request: %s %s %s", variables, (start_time, end_time), kwargs)
        desired_dates = [dt for dt in self._iter_months(start_time, end_time)]
        logger.debug(f"Desired dates: {desired_dates}")
        years = set(dt.year for dt in desired_dates)
        months = set(dt.month for dt in desired_dates)

        # Extract and add the pressure-level var for pressure collection
        # If not relevant, pressure_levels=[] and will be skipped later
        pressure_levels = kwargs.get("pressure_levels", [])
        if pressure_levels:
            logger.debug(f" Gen requests pressure level is {pressure_levels}")

        for dt in self._iter_months(start_time, end_time):
            for code in set(variables):
                logger.debug("ERA5 atomic request: %s %s", code, dt)
                cds_request = {
                    "product_type": [self.product_type],
                    # "variable": variables,
                    "variable": [ _get_source_variable_from_key(ds, code) ],
                    "data_format": "netcdf",
                    # "download_format": "unarchived",
                    "download_format": "zip",
                    "year": list(years),
                    "month": list(months),
                    "time": ["00:00"],
                }
                logger.debug("&&&&&&&&&&ERA5 request: %s", cds_request)

                if self.area:
                    cds_request["area"] = list(self.area)

                if pressure_levels:
                    cds_request["pressure_level"] = pressure_levels

                ts = _ts_for_filename(dt)
                identifier = f"{ds}_{code}_{ts}"

                logging.info(FileRequest(
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
                ))

                yield FileRequest(
                    identifier=identifier,
                    filename=f"{identifier}.zip",
                    valid_time=dt,
                    reference_time=None,  # static / derived, not a forecast
                    params={
                        "cds_dataset": ds,
                        "cds_request": cds_request,
                        "variable_key": _get_key_from_source_variable(ds, code),
                    },
                    expected_format="netcdf",
                    variables=[code],
                )
                # yield None


def _as_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _ts_for_filename(dt: datetime) -> str:
    # Your GeoTIFFFormatPlugin parses "YYYY-MM-DDTHH:MM:SS" (no trailing Z)
    dt = _as_utc(dt)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

def _get_source_variable_from_key(dataset:str, key: str) -> str:
    try:
        variables_dict = era5_constants.COLLECTIONS[dataset]["variables"]
        res = next((v for v in variables_dict if v['key'] == key), None)
        if res:
            return res['source_variable']
    except KeyError:
        pass
    return key


def _get_key_from_source_variable(dataset:str, code: str) -> str:
    try:
        variables_dict = era5_constants.COLLECTIONS[dataset]["variables"]
        res = next((v for v in variables_dict if v['source_variable'] == code), None)
        if res:
            return res['key']
    except KeyError:
        pass
    return code
