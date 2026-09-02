
# =============================================================================
# CMIP6 (C3S Interactive Climate Atlas) data source
# =============================================================================

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator, Optional

from georiva.sources.fetch import FileRequest
from . import CDSFetchStrategy, CDSDataSource

logger = logging.getLogger(__name__)

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
