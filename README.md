# Riverscapes Reports Scripts

Python client scripts for creating, managing, and monitoring reports via the
[Riverscapes Reports GraphQL API](https://api.reports.riverscapes.net).

---

## Table of Contents

1. [What is this project?](#what-is-this-project)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Authentication](#authentication)
6. [GraphQL Primer](#graphql-primer)
7. [Project Layout](#project-layout)
8. [API Reference](#api-reference)
9. [Writing Your Own Script](#writing-your-own-script)
10. [Troubleshooting](#troubleshooting)

---

## What is this project?

The Riverscapes Reports platform generates map-based reports for river
and watershed science. This repository gives you:

| Component | Purpose |
|---|---|
| `pyreports/` | Installable Python package wrapping the Reports GraphQL API |
| `scripts/create_report.py` | Interactive command-line tool to create and run a report end-to-end |

You interact with the platform entirely through a **GraphQL API** — no manual
HTTP wrangling required. The `ReportsAPI` class takes care of authentication,
query execution, and error handling so your scripts can focus on business logic.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.12 | Use `python --version` to check |
| [uv](https://docs.astral.sh/uv/) | latest | Required package manager |
| Internet access | — | Required for API calls and browser login |

> **No GraphQL experience required.** The `ReportsAPI` class wraps every
> query and mutation so you call ordinary Python methods. See the
> [GraphQL Primer](#graphql-primer) section if you want to understand what
> is happening under the hood.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Riverscapes/rs-reports-scripts.git
cd rs-reports-scripts
```

### 2. Install uv (if you don't have it)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows use the PowerShell installer from [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/).

### 3. Create the virtual environment and install dependencies

```bash
uv sync
```

`uv sync` reads `pyproject.toml`, creates a `.venv` folder, and installs
everything in one step.  Run it again any time you pull new changes.

### 4. Verify the install

```bash
uv run python -c "from pyreports import ReportsAPI; print('OK')"
```

---

## Quick Start

Run the interactive report-creation script against the **staging** environment:

```bash
uv run python scripts/create_report.py staging
```

The script will:

1. Open a browser tab for you to log in with your Riverscapes account.
2. Present an interactive menu to select a report type.
3. Prompt for a report name, picker layer, and unit system.
4. Create the report, attach inputs, start it, and poll until it finishes.
5. Print a direct link to the finished report.

Use `production` instead of `staging` to target the live platform.

---

## Authentication

The `ReportsAPI` class supports two authentication modes.

### Interactive (browser) login — for personal use

When you use `ReportsAPI` without providing `machine_auth`, it starts a
temporary local web server, opens your browser to the Riverscapes Auth0 login
page, and captures the authorization code automatically via the OAuth 2.0
PKCE flow.

```python
with ReportsAPI(stage='production') as api:
    # You will be prompted to log in via the browser once.
    # The access token is refreshed automatically in the background.
    profile = api.get_profile()
    print(profile['name'])
```

**Why PKCE?**  
PKCE (Proof Key for Code Exchange, pronounced "pixie") is the recommended
OAuth 2.0 flow for public clients (scripts, CLIs) that cannot safely store a
client secret. Instead of a fixed secret, it generates a random one-time
`code_verifier` and sends only a SHA-256 hash of it (`code_challenge`) to the
auth server. This prevents interception attacks.

> **Port note:** The callback server listens on port `4721` by default.
> If that port is already in use, set the environment variable
> `RSAPI_ALTPORT=1` to use port `4723` instead.

### Machine (client-credentials) auth — for automated pipelines

For CI/CD or server-side scripts where no browser is available, pass a
`machine_auth` dict with a client ID and secret issued by the Riverscapes team:

```python
with ReportsAPI(
    stage='production',
    machine_auth={
        'clientId': 'YOUR_CLIENT_ID',
        'secretId': 'YOUR_CLIENT_SECRET',
    }
) as api:
    report = api.create_report(name='My Report', report_type_id='...')
```

Keep your credentials out of source code — load them from environment
variables or a secrets manager:

```python
import os

with ReportsAPI(
    stage='production',
    machine_auth={
        'clientId': os.environ['RS_CLIENT_ID'],
        'secretId': os.environ['RS_CLIENT_SECRET'],
    }
) as api:
    ...
```

---

## GraphQL Primer

> Skip this section if you only want to run the scripts. Come back when you
> want to write your own queries or understand what is happening under the hood.

### What is GraphQL?

GraphQL is a query language for APIs created by Meta. Instead of many REST
endpoints (`GET /reports`, `POST /reports/{id}/start`, …), a GraphQL API
exposes **a single endpoint** (e.g. `https://api.reports.riverscapes.net`).
Every request is a POST with a JSON body containing a `query` string and an
optional `variables` object.

### Queries vs. Mutations

| Type | Purpose | Analogy |
|---|---|---|
| **Query** | Read data | HTTP GET |
| **Mutation** | Create / update / delete data | HTTP POST / PATCH / DELETE |

### What does a raw request look like?

```
POST https://api.reports.riverscapes.net
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "query": "query listReportTypes { reportTypes { items { id name version } } }",
  "variables": {}
}
```

The server returns JSON:

```json
{
  "data": {
    "reportTypes": {
      "items": [
        { "id": "abc123", "name": "Watershed Summary", "version": "1.0.0" }
      ]
    }
  }
}
```

### How does this library make it easier?

1. **Query files** — GraphQL strings live in `pyreports/graphql/` so they are
   readable and reusable, not buried in Python strings.
2. **`run_query()`** — handles setting the `Authorization` header, JSON
   encoding, error parsing, and automatic token refresh.
3. **Data classes** — raw dicts from the API are wrapped in `RSReport` and
   `RSReportType`, giving you typed attributes (`report.status`,
   `report.is_complete()`) instead of string indexing.

### Exploring the schema

The full schema is at `pyreports/graphql/rs-reports.schema.graphql`. You can
also introspect the live API with any GraphQL client (e.g.
[Altair](https://altairgraphql.dev/), [Insomnia](https://insomnia.rest/)) by
pointing it at the API URL and adding an `Authorization: Bearer <token>` header.

---

## Project Layout

```
rs-reports-scripts/
├── pyproject.toml               # Package metadata and dependencies
├── requirements.txt             # Pinned runtime dependencies
│
├── pyreports/                   # Installable Python package
│   ├── __init__.py              # Public exports: ReportsAPI, RSReport, RSReportType
│   ├── __version__.py           # Package version string
│   │
│   ├── classes/
│   │   ├── ReportsAPI.py        # Main API client class
│   │   └── reports_helpers.py   # Data classes (RSReport, RSReportType) + utils
│   │
│   └── graphql/
│       ├── rs-reports.schema.graphql   # Full API schema (for reference / IDE support)
│       ├── queries/             # Read-only GraphQL operations
│       │   ├── getProfile.graphql
│       │   ├── getReport.graphql
│       │   ├── getReportType.graphql
│       │   ├── listReports.graphql
│       │   ├── listReportTypes.graphql
│       │   ├── globalReports.graphql
│       │   ├── uploadUrls.graphql
│       │   └── downloadUrls.graphql
│       └── mutations/          # Write GraphQL operations
│           ├── createReport.graphql
│           ├── startReport.graphql
│           ├── stopReport.graphql
│           ├── deleteReport.graphql
│           └── attachPickerOptionToReport.graphql
│
└── scripts/
    └── create_report.py         # Interactive CLI script
```

### Key design decisions

- **GraphQL files are separate** from Python code. This keeps queries readable,
  allows editor syntax highlighting, and means you can copy-paste them
  directly into a GraphQL client for testing.
- **Context manager (`with` statement)** — `ReportsAPI` implements `__enter__`
  and `__exit__` so it authenticates on entry and cleanly cancels any
  background token-refresh timers on exit. Always use the `with` form.
- **`RSReport` and `RSReportType` data classes** — wrap raw API dicts and add
  helper methods like `is_complete()`, `is_running()`, and `is_failed()`.

---

## API Reference

### `ReportsAPI(stage, machine_auth=None, dev_headers=None)`

The main client class. Always use as a context manager:

```python
with ReportsAPI(stage='production') as api:
    ...
```

| Parameter | Type | Description |
|---|---|---|
| `stage` | `str` | `'production'`, `'staging'`, or `'local'` |
| `machine_auth` | `dict \| None` | `{'clientId': ..., 'secretId': ...}` for non-browser auth |
| `dev_headers` | `dict \| None` | Raw headers to inject (for local development / testing) |

---

### Profile

#### `api.get_profile() -> dict`

Returns the authenticated user's profile (`id`, `name`, `email`, etc.).

```python
profile = api.get_profile()
print(profile['name'])
```

---

### Report Types

Report types define what a report does (e.g. "Watershed Summary",
"Fish Passage Assessment"). They are managed by the Riverscapes team.

#### `api.list_report_types() -> list[RSReportType]`

Returns all available report types.

```python
for rt in api.list_report_types():
    print(rt.id, rt.name, rt.version)
```

#### `api.get_report_type(report_type_id: str) -> RSReportType`

Fetch a single report type by its UUID.

---

### Reports

#### `api.list_reports(limit=50, offset=0) -> tuple[list[RSReport], int]`

Returns a page of the current user's reports plus the total count.
Use `offset` to paginate.

```python
reports, total = api.list_reports(limit=10, offset=0)
print(f"Showing {len(reports)} of {total}")
```

#### `api.iter_reports(page_size=50) -> Generator[RSReport]`

Yields every report for the current user, handling pagination automatically.
Prefer this over calling `list_reports` in a loop.

```python
for report in api.iter_reports():
    print(report.id, report.status)
```

#### `api.get_report(report_id: str) -> RSReport`

Fetch a single report by its UUID.

#### `api.global_reports(limit=50, offset=0) -> tuple[list[RSReport], int]`

Admin method — returns reports across all users.

---

### Creating and Running a Report

The typical lifecycle is: **create → (attach inputs) → start → poll**.

#### `api.create_report(name, report_type_id, description=None, parameters=None, extent=None) -> RSReport`

Creates a new report with status `CREATED`. The report is not running yet —
this step just registers it and returns an `id` you can use for subsequent calls.

```python
report = api.create_report(
    name='My Watershed Report',
    report_type_id='<uuid-of-report-type>',
    parameters={'units': 'imperial'},
)
print(report.id)   # UUID you will use for everything else
```

#### `api.attach_picker_option(report_id, picker_layer, picker_item_id) -> RSReport`

Some report types require you to select a geographic feature (a "picker item")
before starting. This call links that selection to the report.

```python
api.attach_picker_option(report.id, 'huc', '1302020710')
```

#### `api.start_report(report_id: str) -> RSReport`

Submits the report to the processing queue. After this call the status moves
to `QUEUED` and then `RUNNING`.

#### `api.stop_report(report_id: str) -> RSReport`

Cancels a running report. Sets status to `STOPPED`.

#### `api.delete_report(report_id: str) -> RSReport`

Permanently deletes a report and its stored files from S3.

---

### Polling

#### `api.poll_report(report_id, interval=10, timeout=3600) -> RSReport`

Blocks until the report reaches a terminal state (`COMPLETE`, `ERROR`,
`STOPPED`, or `DELETED`), then returns the final `RSReport`. Raises
`ReportsAPIException` if `timeout` seconds elapse first.

```python
report = api.poll_report(report.id, interval=10)
if report.is_complete():
    print("Done!")
```

---

### File Operations

#### `api.upload_file(report_id, local_path, remote_path, file_type='INPUTS') -> bool`

Uploads a local file to the report's S3 storage. Retries up to 3 times with
exponential back-off.

```python
api.upload_file(report.id, '/tmp/data.csv', 'inputs/data.csv')
```

`file_type` is one of: `INDEX`, `INPUTS`, `LOG`, `OUTPUTS`, `ZIP`.

#### `api.get_upload_urls(report_id, file_paths, file_type=None) -> list[dict]`

Returns raw pre-signed S3 `PUT` URLs. Use this when you need more control over
the upload (e.g. chunked upload, non-default headers).

#### `api.get_download_urls(report_id, file_types=None) -> list[dict]`

Returns pre-signed S3 `GET` URLs for a report's files.

#### `api.download_file(url, local_path, force=False) -> bool`

Downloads from a pre-signed URL to a local path. Skips if the file already
exists unless `force=True`.

---

### Report Status Values

| Status | Meaning |
|---|---|
| `CREATED` | Report exists but has not been started |
| `QUEUED` | Submitted, waiting for a processing slot |
| `RUNNING` | Currently being processed |
| `COMPLETE` | Finished successfully |
| `ERROR` | Processing failed — check `status_message` |
| `STOPPED` | Manually stopped by the user |
| `DELETED` | Report has been deleted |

---

### `RSReport` attributes

| Attribute | Type | Description |
|---|---|---|
| `id` | `str` | UUID |
| `name` | `str` | Human-readable name |
| `description` | `str \| None` | Optional description |
| `status` | `str` | See [Status Values](#report-status-values) |
| `status_message` | `str \| None` | Human-readable status detail |
| `progress` | `int` | 0–100 percentage |
| `parameters` | `dict \| None` | Input parameters |
| `outputs` | `list` | Output file metadata |
| `extent` | `dict \| None` | GeoJSON geometry of the report area |
| `centroid` | `dict \| None` | GeoJSON point centroid |
| `created_at` | `datetime \| None` | Creation timestamp |
| `updated_at` | `datetime \| None` | Last-updated timestamp |
| `report_type` | `RSReportType \| None` | Embedded report type info |
| `created_by_id` | `str \| None` | Owner user ID |
| `created_by_name` | `str \| None` | Owner display name |

Helper methods: `is_complete()`, `is_running()`, `is_failed()`

---

## Writing Your Own Script

Here is a minimal end-to-end example you can adapt:

```python
import os
from pyreports import ReportsAPI

with ReportsAPI(stage='production') as api:

    # 1. Pick a report type
    report_types = api.list_report_types()
    rt = next(r for r in report_types if r.short_name == 'watershed-summary')

    # 2. Create the report
    report = api.create_report(
        name='My Test Report',
        report_type_id=rt.id,
        parameters={'units': 'imperial'},
    )

    # 3. Attach a picker selection (if the report type requires it)
    api.attach_picker_option(report.id, 'huc', '1302020710')

    # 4. Start it
    report = api.start_report(report.id)
    print(f"Started: {report.id} ({report.status})")

    # 5. Wait for completion
    report = api.poll_report(report.id, interval=10)

    if report.is_complete():
        print("Report complete!")
        # 6. Download the outputs
        for item in api.get_download_urls(report.id, file_types=['OUTPUTS']):
            api.download_file(item['url'], f"/tmp/{item['filePath']}")
    else:
        print(f"Report failed: {report.status_message}")
```

### Calling a custom GraphQL query

If you need data that isn't exposed by a `ReportsAPI` method, you can call
`run_query()` directly with any GraphQL string:

```python
with ReportsAPI(stage='production') as api:
    result = api.run_query(
        """
        query MyCustomQuery($reportId: ID!) {
          report(reportId: $reportId) {
            id
            status
            outputs { filePath url }
          }
        }
        """,
        variables={'reportId': 'YOUR-REPORT-UUID'},
    )
    print(result['data']['report'])
```

---

## Troubleshooting

### `Port 4721 is already in use`

Another process is using the OAuth callback port. Set the environment variable
to switch to the alternate port:

```bash
export RSAPI_ALTPORT=1
python scripts/create_report.py staging
```

### `ReportsAPIException: You must be authenticated`

Your token expired and the library failed to refresh it. Try running the
script again — a fresh browser login will be triggered automatically.

### `ModuleNotFoundError: No module named 'pyreports'`

The package is not installed in the active Python environment. Run:

```bash
uv sync
```

Then check you are using the correct interpreter (the one in `.venv/`).
You can also prefix any command with `uv run` and uv will use the project
environment automatically without needing to activate it first.

### GraphQL errors in the response

`ReportsAPIException` includes the raw `errors` array from the API in its
message. The most useful fields are `message` and `extensions.code`.

### Debugging raw HTTP traffic

Set the `logging` level to `DEBUG` before creating the `ReportsAPI` instance:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will print every HTTP request/response including headers (but not the
bearer token value) to stderr.
