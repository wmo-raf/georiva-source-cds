# GeoRiva CDS

A [GeoRiva](https://github.com/wmo-raf/georiva) source plugin for the
**Copernicus Climate Data Store (CDS)**.

It ships:

- **`CDSFetchStrategy`** — a reusable fetch strategy that wraps the official
  `cdsapi` client. CDS queues each request and downloads the result when ready;
  the strategy treats this as one blocking (synchronous) fetch.
- **`CDSDataSource`** — a base class that turns a CDS download (a `.zip`
  containing a `.nc`) into a single rasterizable NetCDF: it extracts the `.nc`,
  collapses the ensemble `member` dimension to the **ensemble mean**, and renames
  the data variable to a stable canonical name.
- **`CMIP6DataFeed`** — the first concrete dataset: CMIP6 monthly/annual climate
  indices from the C3S Interactive Climate Atlas (`multi-origin-c3s-atlas`).

Adding another CDS dataset (e.g. ERA5) later means subclassing `CDSDataSource`,
setting `DATASET`, and implementing `generate_requests()` — the fetch strategy
and the zip/ensemble post-processing are reused unchanged.

## Data model

| Concept | Maps to |
| --- | --- |
| Collection | one *experiment × resolution*, e.g. "CMIP6 SSP2-4.5 (Monthly)" |
| DataFeed | spatial subset (country or custom bbox) + bias-adjustment |
| Variable | a C3S Atlas climatic-impact-driver index |

The experiment is baked into each collection's definition key; the operator
chooses which experiments to ingest by selecting collections in the setup wizard.

## CMIP6 is static data

Historical (1850–2014) and SSP scenarios (2015–2100) do not change, so there is
no "latest" to poll. Provision the feed once and run it as a **backfill** — the
recurring scheduler/sweep machinery is intentionally not wired up.

## Configuration

This plugin needs Copernicus CDS credentials at fetch time (declared in
`georiva_plugin_info.json` under `requires_env`). `cdsapi.Client()` reads them
from the environment, so set them in the **GeoRiva stack's `.env`**:

| Variable | Required | Notes |
| --- | --- | --- |
| `CDSAPI_KEY` | yes | Get a key at <https://cds.climate.copernicus.eu/profile> and accept the *multi-origin-c3s-atlas* licence. |
| `CDSAPI_URL` | no | Defaults to `https://cds.climate.copernicus.eu/api`. |

(Equivalently, mount a `~/.cdsapirc` into the container.)

## Install

This plugin installs into a running GeoRiva instance — it is a Python package,
not a standalone service.

- **Production:** declare it in the operator's `plugins.toml`
  (`git = "https://github.com/wmo-raf/georiva-source-cds.git"`, with a release
  `tag`), set `CDSAPI_KEY` in the stack `.env`, rebuild, and run migrations.
- **Development:** bind-mount the package into the core GeoRiva dev stack — add
  `../plugins/georiva-source-cds/plugins/georiva_source_cds:/georiva/dev-plugins/georiva_source_cds`
  to the core repo's `docker-compose.override.yml` (see its
  `docker-compose.override.sample.yml`), then `make dev-up OV=1` and
  `make dev-makemigrations && make dev-migrate`.

Then in the GeoRiva admin, open **Automated Sources → Set up wizard**, choose
**CMIP6 Data Feed**, pick a country (its bounding box is resolved automatically
via `django-countries-geoextent`) or enter a custom bounding box, and select the
collections (experiments × resolutions) to provision. Run the feed once to
backfill.

The spatial subset resolves in priority order: an explicit custom bounding box
(all four of north/south/west/east) wins; otherwise the selected country's
extent is used; if neither is set, the full global domain is requested.

## Ensemble handling

C3S Atlas files carry a `member` dimension (~30 GCMs). This plugin reduces it to
the **ensemble mean** in `post_process_fetched_file` before ingestion. To change
that (e.g. median, or per-model collections), adjust `CDSDataSource`.
