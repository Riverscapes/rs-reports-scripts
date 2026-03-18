# Riverscapes Reports Scripts

Client libraries for creating, managing, and monitoring reports via the
[Riverscapes Reports GraphQL API](https://api.reports.riverscapes.net).

Available in **Python** and **TypeScript/JavaScript**.

---

## Table of Contents

1. [What is this project?](#what-is-this-project)
2. [Prerequisites](#prerequisites)
3. [Python — Installation & Quick Start](#python--installation--quick-start)
4. [TypeScript — Installation & Quick Start](#typescript--installation--quick-start)
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
| `python/pyreports/` | Installable Python package wrapping the Reports GraphQL API |
| `python/scripts/create_report.py` | Interactive Python CLI to create and run a report end-to-end |
| `typescript/src/` | TypeScript/JavaScript package wrapping the Reports GraphQL API |
| `typescript/scripts/createReport.ts` | Interactive TypeScript CLI to create and run a report end-to-end |

You interact with the platform entirely through a **GraphQL API** — no manual
HTTP wrangling required. The client classes take care of authentication,
query execution, and error handling so your scripts can focus on business logic.

---

## Prerequisites

### Python

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.12 | Use `python --version` to check |
| [uv](https://docs.astral.sh/uv/) | latest | Required package manager |
| Internet access | — | Required for API calls and browser login |

### TypeScript

| Requirement | Version | Notes |
|---|---|---|
| Node.js | ≥ 18 | Use `node --version` to check |
| npm | ≥ 9 | Bundled with Node.js |
| Internet access | — | Required for API calls and browser login |

> **No GraphQL experience required.** The client classes wrap every
> query and mutation so you call ordinary methods. See the
> [GraphQL Primer](#graphql-primer) section if you want to understand what
> is happening under the hood.

---

## Python — Installation & Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/Riverscapes/rs-reports-scripts.git
cd rs-reports-scripts/python
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
everything in one step. Run it again any time you pull new changes.

### 4. Verify the install

```bash
uv run python -c "from pyreports import ReportsAPI; print('OK')"
```

### 5. Run the interactive report-creation script

```bash
uv run python scripts/create_report.py staging
```

Use `production` instead of `staging` to target the live platform.

---

## TypeScript — Installation & Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/Riverscapes/rs-reports-scripts.git
cd rs-reports-scripts/typescript
```

### 2. Install dependencies

```bash
npm install
```

### 3. Build the library

```bash
npm run build
```

### 4. Format code (optional)

The TypeScript code follows the same formatting conventions as the
[rs-web-monorepo](https://github.com/Riverscapes/rs-web-monorepo): no
semicolons, single quotes, trailing commas (es5), 120-char line width.

```bash
npm run format
```

### 5. Run the interactive report-creation script

```bash
npx tsx scripts/createReport.ts staging
```

Or using the package.json script:

```bash
npm run create-report -- staging
```

Use `production` instead of `staging` to target the live platform.

---

## Authentication

Both the Python and TypeScript clients support two authentication modes.

### Interactive (browser) login — for personal use

Opens a browser tab for you to log in via the Auth0 PKCE flow.
The access token is refreshed automatically in the background.

**Python:**
```python
with ReportsAPI(stage='production') as api:
    profile = api.get_profile()
    print(profile['name'])
```

**TypeScript:**
```typescript
import { ReportsAPI } from 'rs-reports'

const api = new ReportsAPI({ stage: 'production' })
await api.open()
try {
  const profile = await api.getProfile()
  console.log(profile.name)
} finally {
  api.close()
}
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

For CI/CD or server-side scripts where no browser is available, pass
machine credentials:

**Python:**
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

**TypeScript:**
```typescript
const api = new ReportsAPI({
  stage: 'production',
  machineAuth: {
    clientId: 'YOUR_CLIENT_ID',
    secretId: 'YOUR_CLIENT_SECRET',
  },
})
await api.open()
```

Keep your credentials out of source code — load them from environment
variables or a secrets manager:

**Python:**
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

**TypeScript:**
```typescript
const api = new ReportsAPI({
  stage: 'production',
  machineAuth: {
    clientId: process.env.RS_CLIENT_ID!,
    secretId: process.env.RS_CLIENT_SECRET!,
  },
})
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

### How do the client libraries make it easier?

1. **Query files** — GraphQL strings live in dedicated `graphql/` directories so they are
   readable and reusable, not buried in code strings.
2. **`run_query()` / `runQuery()`** — handles setting the `Authorization` header, JSON
   encoding, error parsing, and automatic token refresh.
3. **Data classes** — raw dicts/objects from the API are wrapped in `RSReport` and
   `RSReportType`, giving you typed attributes (`report.status`,
   `report.isComplete()`) instead of string indexing.

### Exploring the schema

The full schema is at `python/pyreports/graphql/rs-reports.schema.graphql`
(also mirrored in `typescript/src/graphql/`). You can
also introspect the live API with any GraphQL client (e.g.
[Altair](https://altairgraphql.dev/), [Insomnia](https://insomnia.rest/)) by
pointing it at the API URL and adding an `Authorization: Bearer <token>` header.

---

## Project Layout

```
rs-reports-scripts/
├── README.md
├── graphql.config.json
│
├── python/                         # Python client
│   ├── pyproject.toml              # Package metadata and dependencies
│   ├── requirements.txt            # Pinned runtime dependencies
│   │
│   ├── pyreports/                  # Installable Python package
│   │   ├── __init__.py             # Public exports
│   │   ├── __version__.py          # Package version string
│   │   │
│   │   ├── classes/
│   │   │   ├── ReportsAPI.py       # Main API client class
│   │   │   └── reports_helpers.py  # Data classes + utils
│   │   │
│   │   └── graphql/
│   │       ├── rs-reports.schema.graphql
│   │       ├── queries/            # Read-only GraphQL operations
│   │       └── mutations/          # Write GraphQL operations
│   │
│   └── scripts/
│       └── create_report.py        # Interactive Python CLI script
│
└── typescript/                     # TypeScript/JavaScript client
    ├── package.json                # Package metadata and dependencies
    ├── tsconfig.json               # TypeScript config (type-checking, VS Code)
    ├── tsconfig.build.json         # TypeScript config (build / emit)
    ├── .prettierrc.cjs             # Prettier formatting rules
    │
    ├── src/
    │   ├── index.ts                # Public exports
    │   ├── ReportsAPI.ts           # Main API client class
    │   ├── reportsHelpers.ts       # Data classes + utils
    │   │
    │   └── graphql/
    │       ├── rs-reports.schema.graphql
    │       ├── queries/            # Read-only GraphQL operations
    │       └── mutations/          # Write GraphQL operations
    │
    └── scripts/
        └── createReport.ts         # Interactive TypeScript CLI script
```

### Key design decisions

- **GraphQL files are separate** from source code. This keeps queries readable,
  allows editor syntax highlighting, and means you can copy-paste them
  directly into a GraphQL client for testing.
- **Python uses a context manager (`with` statement)** — `ReportsAPI` implements
  `__enter__` and `__exit__` so it authenticates on entry and cleanly cancels
  any background token-refresh timers on exit.
- **TypeScript uses `open()` / `close()`** — call `await api.open()` to
  authenticate and `api.close()` to clean up. Use a `try/finally` block.
- **`RSReport` and `RSReportType` data classes** — wrap raw API responses and add
  helper methods like `isComplete()` / `is_complete()`, `isRunning()` / `is_running()`,
  and `isFailed()` / `is_failed()`.

---

## API Reference

### Python: `ReportsAPI(stage, machine_auth=None, dev_headers=None)`
### TypeScript: `new ReportsAPI({ stage, machineAuth?, devHeaders? })`

| Parameter | Python Type | TypeScript Type | Description |
|---|---|---|---|
| `stage` | `str` | `string` | `'production'`, `'staging'`, or `'local'` |
| `machine_auth` / `machineAuth` | `dict \| None` | `MachineAuth \| undefined` | `{clientId, secretId}` for non-browser auth |
| `dev_headers` / `devHeaders` | `dict \| None` | `Record<string, string> \| undefined` | Raw headers for local dev |

---

### Profile

#### `get_profile()` / `getProfile()`

Returns the authenticated user's profile (`id`, `name`, `email`, etc.).

**Python:**
```python
profile = api.get_profile()
print(profile['name'])
```

**TypeScript:**
```typescript
const profile = await api.getProfile()
console.log(profile.name)
```

---

### Report Types

Report types define what a report does. They are managed by the Riverscapes team.

#### `list_report_types()` / `listReportTypes()`

Returns all available report types.

**Python:**
```python
for rt in api.list_report_types():
    print(rt.id, rt.name, rt.version)
```

**TypeScript:**
```typescript
for (const rt of await api.listReportTypes()) {
  console.log(rt.id, rt.name, rt.version)
}
```

#### `get_report_type(id)` / `getReportType(id)`

Fetch a single report type by its UUID.

---

### Reports

#### `list_reports(limit, offset)` / `listReports(limit, offset)`

Returns a page of the current user's reports plus the total count.

**Python:**
```python
reports, total = api.list_reports(limit=10, offset=0)
print(f"Showing {len(reports)} of {total}")
```

**TypeScript:**
```typescript
const { reports, total } = await api.listReports(10, 0)
console.log(`Showing ${reports.length} of ${total}`)
```

#### `iter_reports(page_size)` / `iterReports(pageSize)`

Yields every report for the current user, handling pagination automatically.

**Python:**
```python
for report in api.iter_reports():
    print(report.id, report.status)
```

**TypeScript:**
```typescript
for await (const report of api.iterReports()) {
  console.log(report.id, report.status)
}
```

#### `get_report(report_id)` / `getReport(reportId)`

Fetch a single report by its UUID.

#### `global_reports(limit, offset)` / `globalReports(limit, offset)`

Admin method — returns reports across all users.

---

### Creating and Running a Report

The typical lifecycle is: **create → (attach inputs) → start → poll**.

#### `create_report(...)` / `createReport(...)`

Creates a new report with status `CREATED`. The report is not running yet —
this step just registers it and returns an `id` you can use for subsequent calls.

**Python:**
```python
report = api.create_report(
    name='My Watershed Report',
    report_type_id='<uuid-of-report-type>',
    parameters={'units': 'imperial'},
)
```

**TypeScript:**
```typescript
const report = await api.createReport({
  name: 'My Watershed Report',
  reportTypeId: '<uuid-of-report-type>',
  parameters: { units: 'imperial' },
})
```

#### `attach_picker_option(...)` / `attachPickerOption(...)`

Links a geographic picker selection to the report.

#### `start_report(report_id)` / `startReport(reportId)`

Submits the report to the processing queue.

#### `stop_report(report_id)` / `stopReport(reportId)`

Cancels a running report. Sets status to `STOPPED`.

#### `delete_report(report_id)` / `deleteReport(reportId)`

Permanently deletes a report and its stored files from S3.

---

### Polling

#### `poll_report(report_id, interval, timeout)` / `pollReport(reportId, interval, timeout)`

Blocks until the report reaches a terminal state (`COMPLETE`, `ERROR`,
`STOPPED`, or `DELETED`), then returns the final report. Raises
`ReportsAPIException` if `timeout` seconds elapse.

**Python:**
```python
report = api.poll_report(report.id, interval=10)
if report.is_complete():
    print("Done!")
```

**TypeScript:**
```typescript
const report = await api.pollReport(report.id!, 10)
if (report.isComplete()) {
  console.log('Done!')
}
```

---

### File Operations

#### `upload_file(...)` / `uploadFile(...)`

Uploads a local file to the report's S3 storage. Retries up to 3 times with
exponential back-off.

#### `get_upload_urls(...)` / `getUploadUrls(...)`

Returns raw pre-signed S3 `PUT` URLs for more control over uploads.

#### `get_download_urls(...)` / `getDownloadUrls(...)`

Returns pre-signed S3 `GET` URLs for a report's files.

#### `download_file(...)` / `downloadFile(...)`

Downloads from a pre-signed URL to a local path. Skips if file already exists
unless `force=True` / `force: true`.

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

| Python Attribute | TypeScript Property | Type | Description |
|---|---|---|---|
| `id` | `id` | `str` / `string` | UUID |
| `name` | `name` | `str` / `string` | Human-readable name |
| `description` | `description` | `str \| None` / `string \| undefined` | Optional description |
| `status` | `status` | `str` / `string` | See [Status Values](#report-status-values) |
| `status_message` | `statusMessage` | `str \| None` / `string \| undefined` | Status detail |
| `progress` | `progress` | `int` / `number` | 0–100 percentage |
| `parameters` | `parameters` | `dict` / `Record` | Input parameters |
| `outputs` | `outputs` | `list` / `unknown[]` | Output file metadata |
| `extent` | `extent` | `dict` / `Record` | GeoJSON geometry |
| `centroid` | `centroid` | `dict` / `Record` | GeoJSON point |
| `created_at` | `createdAt` | `datetime` / `Date` | Creation timestamp |
| `updated_at` | `updatedAt` | `datetime` / `Date` | Last-updated timestamp |
| `report_type` | `reportType` | `RSReportType` | Embedded report type info |
| `created_by_id` | `createdById` | `str` / `string` | Owner user ID |
| `created_by_name` | `createdByName` | `str` / `string` | Owner display name |

Helper methods: `is_complete()` / `isComplete()`, `is_running()` / `isRunning()`, `is_failed()` / `isFailed()`

---

## Writing Your Own Script

### Python

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

    # 5. Wait for completion
    report = api.poll_report(report.id, interval=10)

    if report.is_complete():
        print("Report complete!")
        for item in api.get_download_urls(report.id, file_types=['OUTPUTS']):
            api.download_file(item['url'], f"/tmp/{item['filePath']}")
    else:
        print(f"Report failed: {report.status_message}")
```

### TypeScript

```typescript
import { ReportsAPI } from 'rs-reports'

const api = new ReportsAPI({ stage: 'production' })
await api.open()

try {
  // 1. Pick a report type
  const reportTypes = await api.listReportTypes()
  const rt = reportTypes.find((r) => r.shortName === 'watershed-summary')!

  // 2. Create the report
  let report = await api.createReport({
    name: 'My Test Report',
    reportTypeId: rt.id!,
    parameters: { units: 'imperial' },
  })

  // 3. Attach a picker selection
  await api.attachPickerOption(report.id!, 'huc', '1302020710')

  // 4. Start it
  report = await api.startReport(report.id!)

  // 5. Wait for completion
  report = await api.pollReport(report.id!, 10)

  if (report.isComplete()) {
    console.log('Report complete!')
    const urls = await api.getDownloadUrls(report.id!, ['OUTPUTS'])
    for (const item of urls) {
      await api.downloadFile(item.url, `/tmp/${(item as any).filePath}`)
    }
  } else {
    console.log(`Report failed: ${report.statusMessage}`)
  }
} finally {
  api.close()
}
```

### Calling a custom GraphQL query

**Python:**
```python
with ReportsAPI(stage='production') as api:
    result = api.run_query(
        """
        query MyCustomQuery($reportId: ID!) {
          report(reportId: $reportId) {
            id
            status
          }
        }
        """,
        variables={'reportId': 'YOUR-REPORT-UUID'},
    )
    print(result['data']['report'])
```

**TypeScript:**
```typescript
const result = await api.runQuery(
  `query MyCustomQuery($reportId: ID!) {
    report(reportId: $reportId) {
      id
      status
    }
  }`,
  { reportId: 'YOUR-REPORT-UUID' }
)
console.log((result as any).data.report)
```

---

## Troubleshooting

### `Port 4721 is already in use`

Another process is using the OAuth callback port. Set the environment variable
to switch to the alternate port:

```bash
export RSAPI_ALTPORT=1
# Python
cd python && python scripts/create_report.py staging
# TypeScript
cd typescript && npx tsx scripts/createReport.ts staging
```

### `ReportsAPIException: You must be authenticated`

Your token expired and the library failed to refresh it. Try running the
script again — a fresh browser login will be triggered automatically.

### Python: `ModuleNotFoundError: No module named 'pyreports'`

The package is not installed in the active Python environment. From `python/` run:

```bash
uv sync
```

Then check you are using the correct interpreter (the one in `python/.venv/`).
You can also prefix any command with `uv run` and uv will use the project
environment automatically without needing to activate it first.

### TypeScript: `Cannot find module`

Make sure you've run `npm install` and `npm run build` in the `typescript/` directory.

### GraphQL errors in the response

`ReportsAPIException` includes the raw `errors` array from the API in its
message. The most useful fields are `message` and `extensions.code`.

### Debugging raw HTTP traffic

**Python:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will print every HTTP request/response including headers (but not the
bearer token value) to stderr.

**TypeScript:**
Add console logging to your script or use the `NODE_DEBUG=http` environment variable.
