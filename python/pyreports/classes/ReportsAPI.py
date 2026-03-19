"""ReportsAPI — Python client for the Riverscapes Reports GraphQL API.

This module provides ``ReportsAPI``, a high-level wrapper that handles
authentication, query execution, and response parsing.  All communication
with the backend happens over a single GraphQL endpoint; this module hides
that complexity behind ordinary Python method calls.

Typical usage::

    from pyreports import ReportsAPI

    with ReportsAPI(stage='production') as api:
        report_types = api.list_report_types()
        report = api.create_report(
            name='My Report',
            report_type_id=report_types[0].id,
        )
        report = api.start_report(report.id)
        report = api.poll_report(report.id)
        print(report.status)  # 'COMPLETE'

Authentication modes
--------------------
Interactive (browser)
    The default mode.  Opens a browser tab for the user to log in via
    Auth0 PKCE flow.  The resulting access token is cached and
    automatically renewed in a background thread before it expires.

Machine credentials
    Pass ``machine_auth={'clientId': ..., 'secretId': ...}`` for headless
    environments (CI, server scripts).  Credentials are exchanged for a
    short-lived access token via the OAuth 2.0 client-credentials flow.
"""
import os
import time
import json
import threading
import hashlib
import base64
import logging
from pathlib import Path
from typing import Dict, List, Generator, Tuple
from termcolor import colored
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode, urlparse, urlunparse

try:
    import inquirer
except ImportError:
    inquirer = None

import requests
from rsxml import Logger, ProgressBar

from pyreports.classes.reports_helpers import RSReport, RSReportType
from pyreports.classes.Spinner import Spinner

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("urllib3").propagate = False

CHARSET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
LOCAL_PORT = 4721
ALT_PORT = 4723
LOGIN_SCOPE = 'openid'

AUTH_DETAILS = {
    "domain": "auth.riverscapes.net",
    "clientId": "Vhse6GZoU6vlJ9fcbrdmAAK6b4J9sjtT",
}


class ReportsAPIException(Exception):
    """Raised when the Reports API returns an error or an unexpected HTTP status.

    The ``message`` attribute contains a human-readable description that
    includes any GraphQL ``errors`` array returned by the server, making it
    easy to surface the root cause to the user.
    """

    def __init__(self, message="ReportsAPI encountered an error"):
        self.message = message
        super().__init__(self.message)


class ReportsAPI:
    """Client for the Riverscapes Reports GraphQL API.

    All network communication goes through a single GraphQL endpoint.  The
    class handles authentication, token refresh, query loading, and response
    parsing so callers can work with plain Python objects.

    Always use ``ReportsAPI`` as a context manager so the background
    token-refresh timer is cleaned up on exit::

        with ReportsAPI(stage='production') as api:
            reports, total = api.list_reports()

    Parameters
    ----------
    stage : str
        One of ``'production'``, ``'staging'``, or ``'local'``.  Controls
        which API endpoint is used.  If ``None``, an interactive prompt is
        shown (requires the ``inquirer`` package).
    machine_auth : dict, optional
        Supply ``{'clientId': '...', 'secretId': '...'}`` to authenticate
        via the OAuth 2.0 client-credentials flow instead of the browser.
    dev_headers : dict, optional
        Raw HTTP headers injected into every request.  Useful for local
        development where you want to bypass Auth0 entirely.

    Raises
    ------
    ReportsAPIException
        If ``stage`` is not a recognised value, or if authentication fails.
    """

    def __init__(self, stage: str = None, machine_auth: Dict[str, str] = None, dev_headers: Dict[str, str] = None):
        self.log = Logger('ReportsAPI')
        self.stage = stage.upper() if stage else self._get_stage_interactive()
        self.machine_auth = machine_auth
        self.dev_headers = dev_headers
        self.access_token = None
        self.token_timeout = None
        self.auth_port = LOCAL_PORT if not os.environ.get('RSAPI_ALTPORT') else ALT_PORT

        if self.stage == 'PRODUCTION':
            self.uri = 'https://api.reports.riverscapes.net'
        elif self.stage == 'STAGING':
            self.uri = 'https://api.reports.riverscapes.net/staging'
        elif self.stage == 'LOCAL':
            self.uri = 'http://localhost:7016'
        else:
            raise ReportsAPIException(f'Unknown stage: {stage!r}. Must be "production" or "staging".')

    def _get_stage_interactive(self) -> str:
        if not inquirer:
            raise ReportsAPIException("inquirer is not installed; pass stage= explicitly.")
        answers = inquirer.prompt([
            inquirer.List('stage', message="Which Reports API stage?", choices=['production', 'staging'], default='production'),
        ])
        return answers['stage'].upper()

    def __enter__(self) -> 'ReportsAPI':
        """Authenticate and return self so the instance can be used in a ``with`` block."""
        self.refresh_token()
        return self

    def __exit__(self, _type, _value, _traceback):
        """Cancel any background token-refresh timer and release resources."""
        self.shutdown()

    # -------------------------------------------------------------------------
    # Authentication
    # -------------------------------------------------------------------------

    def _generate_challenge(self, code: str) -> str:
        return self._base64_url(hashlib.sha256(code.encode('utf-8')).digest())

    def _base64_url(self, string: bytes) -> str:
        return base64.urlsafe_b64encode(string).decode('utf-8').replace('=', '').replace('+', '-').replace('/', '_')

    def _generate_random(self, size: int) -> str:
        buffer = os.urandom(size)
        return ''.join(CHARSET[b % len(CHARSET)] for b in buffer)

    def shutdown(self):
        """Cancel the background token-refresh timer.

        Called automatically by ``__exit__`` when the ``with`` block ends.
        Safe to call multiple times.
        """
        self.log.debug("Shutting down Reports API client")
        if self.token_timeout:
            self.token_timeout.cancel()

    def refresh_token(self, force: bool = False):
        """Obtain or renew the access token.

        In **interactive mode** this opens a browser tab for the user to log
        in via the Auth0 PKCE flow.  A temporary local HTTP server on
        ``localhost:{auth_port}`` captures the authorization code that Auth0
        redirects back to after a successful login.

        In **machine-auth mode** this calls the ``/token`` endpoint with the
        client credentials and stores the resulting bearer token.

        After a successful interactive login a ``threading.Timer`` is started
        to call this method again 20 seconds before the token expires, keeping
        long-running scripts authenticated without user interaction.

        Parameters
        ----------
        force : bool
            Re-fetch the token even if one is already cached.
        """
        self.log.info(colored(f"🔐 Authenticating on Reports API: {self.uri}", 'cyan'))
        if self.token_timeout:
            self.token_timeout.cancel()
        if self.dev_headers and len(self.dev_headers) > 0:
            return self
        if self.access_token and not force:
            self.log.debug("Token already exists. Not refreshing.")
            return self

        if self.machine_auth:
            token_uri = self.uri.rstrip('/') + '/token'
            try:
                result = requests.post(
                    token_uri,
                    headers={'content-type': 'application/x-www-form-urlencoded'},
                    data={
                        'audience': 'https://api.riverscapes.net',
                        'grant_type': 'client_credentials',
                        'scope': 'machine:admin',
                        'client_id': self.machine_auth['clientId'],
                        'client_secret': self.machine_auth['secretId'],
                    },
                    timeout=30,
                ).json()
                self.access_token = result['access_token']
                self.log.info(colored("✅ SUCCESSFUL Machine Authentication", 'green'))
            except Exception as error:
                raise ReportsAPIException(str(error)) from error
        else:
            import webbrowser
            code_verifier = self._generate_random(128)
            code_challenge = self._generate_challenge(code_verifier)
            state = self._generate_random(32)
            redirect_url = f"http://localhost:{self.auth_port}/rs-reports"
            login_url = urlparse(f"https://{AUTH_DETAILS['domain']}/authorize")
            query_params = {
                "client_id": AUTH_DETAILS["clientId"],
                "response_type": "code",
                "scope": LOGIN_SCOPE,
                "state": state,
                "audience": "https://api.riverscapes.net",
                "redirect_uri": redirect_url,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
            login_url = login_url._replace(query=urlencode(query_params))
            webbrowser.open_new_tab(urlunparse(login_url))
            auth_code = self._wait_for_auth_code()
            authentication_url = f"https://{AUTH_DETAILS['domain']}/oauth/token"
            response = requests.post(
                authentication_url,
                headers={"content-type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "authorization_code",
                    "client_id": AUTH_DETAILS["clientId"],
                    "code_verifier": code_verifier,
                    "code": auth_code,
                    "redirect_uri": redirect_url,
                },
                timeout=30,
            )
            response.raise_for_status()
            res = response.json()
            self.token_timeout = threading.Timer(res["expires_in"] - 20, self.refresh_token)
            self.token_timeout.start()
            self.access_token = res["access_token"]
            self.log.info(colored("✅ SUCCESSFUL Browser Authentication", 'green'))

    def _wait_for_auth_code(self) -> str:
        auth_port = self.auth_port

        class AuthServer(ThreadingHTTPServer):
            auth_code: str | None = None

        class AuthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                url = "https://reports.riverscapes.net/login_success"
                body = (
                    f"<html><head><title>Reports API: Auth successful</title>"
                    f"<script>window.onload=function(){{window.location.replace('{url}');}}</script>"
                    f"</head><body><p>Authentication successful. Redirecting...</p></body></html>"
                )
                self.wfile.write(body.encode('utf-8'))
                query = urlparse(self.path).query
                if "code" in query:
                    params = dict(x.split("=") for x in query.split("&") if "=" in x)
                    self.server.auth_code = params.get("code")
                    threading.Thread(target=self.server.shutdown).start()

            def log_message(self, format, *args):  # noqa: A002
                pass

        server = AuthServer(("localhost", auth_port), AuthHandler)
        try:
            print("Waiting for browser authentication (Ctrl-C to cancel)...")
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        if not hasattr(server, "auth_code"):
            raise ReportsAPIException("Authentication failed or was cancelled")
        return server.auth_code

    # -------------------------------------------------------------------------
    # GraphQL helpers
    # -------------------------------------------------------------------------

    def load_query(self, query_name: str) -> str:
        """Read a ``.graphql`` file from the ``graphql/queries/`` directory.

        Parameters
        ----------
        query_name : str
            File name without the ``.graphql`` extension, e.g. ``'listReports'``.

        Returns
        -------
        str
            The raw GraphQL query string ready to pass to ``run_query()``.
        """
        path = Path(__file__).parent.parent / 'graphql' / 'queries' / f'{query_name}.graphql'
        return path.read_text(encoding='utf-8')

    def load_mutation(self, mutation_name: str) -> str:
        """Read a ``.graphql`` file from the ``graphql/mutations/`` directory.

        Also accepts an absolute or relative path to a ``.graphql`` file
        outside the package for ad-hoc mutations.

        Parameters
        ----------
        mutation_name : str
            File name without the ``.graphql`` extension, e.g. ``'createReport'``,
            or a full file path.

        Returns
        -------
        str
            The raw GraphQL mutation string ready to pass to ``run_query()``.
        """
        candidate = Path(mutation_name)
        if candidate.exists():
            return candidate.read_text(encoding='utf-8')
        path = Path(__file__).parent.parent / 'graphql' / 'mutations' / f'{mutation_name}.graphql'
        return path.read_text(encoding='utf-8')

    def run_query(self, query: str, variables: dict) -> dict:
        """Execute a GraphQL query or mutation against the API endpoint.

        Adds the ``Authorization: Bearer <token>`` header automatically.  If
        the server responds with an authentication error the token is refreshed
        once and the request is retried.

        Under the hood every GraphQL request is a plain HTTP POST to the API
        URL with a JSON body of ``{"query": "...", "variables": {...}}``.
        The server always returns HTTP 200 — errors are reported inside the
        ``errors`` key of the JSON response body, not via HTTP status codes
        (this is standard GraphQL behaviour).

        Parameters
        ----------
        query : str
            A GraphQL query or mutation string, typically loaded from a
            ``.graphql`` file via ``load_query()`` or ``load_mutation()``.
        variables : dict
            Variable values for the operation, matching the ``$variable``
            placeholders declared in the query string.  Pass ``{}`` for
            queries that have no variables.

        Returns
        -------
        dict
            The full deserialized JSON response, e.g.
            ``{'data': {'report': {...}}}``.  Callers typically index into
            ``result['data']`` to get the payload.

        Raises
        ------
        ReportsAPIException
            If the server returns a non-200 HTTP status, or if the GraphQL
            ``errors`` array is non-empty.
        """
        headers = {"authorization": "Bearer " + self.access_token} if self.access_token else {}
        if self.dev_headers:
            headers.update(self.dev_headers)
        with Spinner("Running GraphQL query", complete_message="GraphQL query complete") as spinner:
            request = requests.post(self.uri, json={'query': query, 'variables': variables}, headers=headers, timeout=30)
        if request.status_code == 200:
            resp_json = request.json()
            if 'errors' in resp_json and len(resp_json['errors']) > 0:
                if any('You must be authenticated' in e['message'] for e in resp_json['errors']):
                    self.log.debug("🔄 Auth expired — refreshing token and retrying...")
                    self.refresh_token(force=True)
                    return self.run_query(query, variables)
                raise ReportsAPIException(f"❌ Query failed: {resp_json['errors']}. Variables: {json.dumps(variables)}")
            return resp_json
        raise ReportsAPIException(f"❌ HTTP {request.status_code} from API. Variables: {json.dumps(variables)}")

    # -------------------------------------------------------------------------
    # Profile
    # -------------------------------------------------------------------------

    def get_profile(self) -> dict:
        """Get the profile of the currently authenticated user."""
        qry = self.load_query('getProfile')
        return self.run_query(qry, {})['data']['profile']

    # -------------------------------------------------------------------------
    # Report Types
    # -------------------------------------------------------------------------

    def list_report_types(self) -> List[RSReportType]:
        """Return all available report types."""
        qry = self.load_query('listReportTypes')
        items = self.run_query(qry, {})['data']['reportTypes']['items']
        return [RSReportType(item) for item in items]

    def get_report_type(self, report_type_id: str) -> RSReportType:
        """Get a single report type by ID."""
        qry = self.load_query('getReportType')
        return RSReportType(self.run_query(qry, {'id': report_type_id})['data']['reportType'])

    # -------------------------------------------------------------------------
    # Reports
    # -------------------------------------------------------------------------

    def get_report(self, report_id: str) -> RSReport:
        """Get a single report by its UUID."""
        qry = self.load_query('getReport')
        return RSReport(self.run_query(qry, {'reportId': report_id})['data']['report'])

    def list_reports(self, limit: int = 50, offset: int = 0) -> Tuple[List[RSReport], int]:
        """Return a page of the current user's reports.

        Returns:
            (list of RSReport, total count)
        """
        qry = self.load_query('listReports')
        pagination = self.run_query(qry, {'limit': limit, 'offset': offset})['data']['profile']['reports']
        return [RSReport(item) for item in pagination['items']], pagination['total']

    def iter_reports(self, page_size: int = 50) -> Generator[RSReport, None, None]:
        """Yield every report for the current user, handling pagination automatically."""
        offset = 0
        total = -1
        while total < 0 or offset < total:
            page, total = self.list_reports(limit=page_size, offset=offset)
            for report in page:
                yield report
            offset += len(page)
            if not page:
                break

    def global_reports(self, limit: int = 50, offset: int = 0) -> Tuple[List[RSReport], int]:
        """Return a page of all reports across all users (admin).

        Returns:
            (list of RSReport, total count)
        """
        qry = self.load_query('globalReports')
        pagination = self.run_query(qry, {'limit': limit, 'offset': offset})['data']['globalReports']
        return [RSReport(item) for item in pagination['items']], pagination['total']

    def create_report(self, name: str, report_type_id: str, description: str = None, parameters: dict = None, extent=None) -> RSReport:
        """Create a new report (status: CREATED).

        After creating, upload any required input files then call start_report().

        Args:
            name:           Human-readable name.
            report_type_id: ID of the RSReportType to run.
            description:    Optional description.
            parameters:     Optional JSON parameters consumed by the report engine.
            extent:         Optional GeoJSON geometry for the report extent.
        """
        report_input: dict = {'name': name, 'reportTypeId': report_type_id}
        if description:
            report_input['description'] = description
        if parameters:
            report_input['parameters'] = parameters
        if extent:
            report_input['extent'] = extent
        mut = self.load_mutation('createReport')
        return RSReport(self.run_query(mut, {'report': report_input})['data']['createReport'])

    def attach_picker_option(self, report_id: str, picker_layer: str, picker_item_id: str) -> RSReport:
        """Attach a picker layer item to a report."""
        mut = self.load_mutation('attachPickerOptionToReport')
        return RSReport(self.run_query(mut, {
            'reportId': report_id,
            'pickerLayer': picker_layer,
            'pickerItemId': picker_item_id,
        })['data']['attachPickerOptionToReport'])

    def start_report(self, report_id: str) -> RSReport:
        """Start a report (moves to QUEUED or RUNNING)."""
        mut = self.load_mutation('startReport')
        return RSReport(self.run_query(mut, {'reportId': report_id})['data']['startReport'])

    def stop_report(self, report_id: str) -> RSReport:
        """Stop a running report."""
        mut = self.load_mutation('stopReport')
        return RSReport(self.run_query(mut, {'reportId': report_id})['data']['stopReport'])

    def delete_report(self, report_id: str) -> RSReport:
        """Delete a report and its S3 files."""
        mut = self.load_mutation('deleteReport')
        return RSReport(self.run_query(mut, {'reportId': report_id})['data']['deleteReport'])

    # -------------------------------------------------------------------------
    # File Operations
    # -------------------------------------------------------------------------

    def get_upload_urls(self, report_id: str, file_paths: List[str], file_type: str = None) -> List[dict]:
        """Get pre-signed S3 upload URLs.

        Args:
            report_id:   UUID of the report.
            file_paths:  Relative paths within the report's S3 folder.
            file_type:   Optional FileTypeEnum (INDEX, INPUTS, LOG, OUTPUTS, ZIP).
        """
        qry = self.load_query('uploadUrls')
        variables: dict = {'reportId': report_id, 'filePaths': file_paths}
        if file_type:
            variables['fileType'] = file_type
        return self.run_query(qry, variables)['data']['uploadUrls']

    def get_download_urls(self, report_id: str, file_types: List[str] = None) -> List[dict]:
        """Get pre-signed S3 download URLs.

        Args:
            report_id:   UUID of the report.
            file_types:  Optional FileTypeEnum filter list.
        """
        qry = self.load_query('downloadUrls')
        variables: dict = {'reportId': report_id}
        if file_types:
            variables['fileTypes'] = file_types
        return self.run_query(qry, variables)['data']['downloadUrls']

    def upload_file(self, report_id: str, local_path: str, remote_path: str, file_type: str = 'INPUTS') -> bool:
        """Upload a local file to the report's S3 folder.

        Args:
            report_id:    UUID of the report.
            local_path:   Path to the local file.
            remote_path:  Destination within the report's S3 folder (e.g. "inputs/data.csv").
            file_type:    FileTypeEnum (default INPUTS).
        """
        urls = self.get_upload_urls(report_id, [remote_path], file_type)
        if not urls:
            raise ReportsAPIException(f"No upload URL returned for: {remote_path}")
        upload_url = urls[0]['url']
        self.log.info(colored(f"📤 Uploading {local_path} -> {remote_path}", 'cyan'))
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(local_path, 'rb') as f:
                    response = requests.put(upload_url, data=f, timeout=120)
                if response.status_code in (200, 201):
                    self.log.info(colored(f"  ✅ Upload successful: {remote_path}", 'green'))
                    return True
                self.log.warning(colored(f"  ⚠️  HTTP {response.status_code} on attempt {attempt + 1}: {response.text[:200]}", 'yellow'))
            except requests.RequestException as e:
                self.log.warning(colored(f"  ⚠️  Network error on attempt {attempt + 1}: {e}", 'yellow'))
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        raise ReportsAPIException(f"❌ Upload failed for {remote_path} after {max_retries} attempts")

    def download_file(self, url: str, local_path: str, force: bool = False) -> bool:
        """Download a file from a pre-signed S3 URL.

        Args:
            url:         Pre-signed URL.
            local_path:  Destination file path.
            force:       Re-download if file already exists.
        """
        if not force and os.path.exists(local_path):
            self.log.debug(f"  Skipping (already exists): {local_path}")
            return False
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        self.log.info(colored(f"  📥 Downloading: {local_path}", 'cyan'))
        max_retries = 3
        for attempt in range(max_retries):
            try:
                r = requests.get(url, allow_redirects=True, stream=True, timeout=60)
                r.raise_for_status()
                total_length = r.headers.get('content-length')
                dl = 0
                with open(local_path, 'wb') as f:
                    if total_length is None:
                        f.write(r.content)
                    else:
                        prg = ProgressBar(int(total_length), 50, local_path, byte_format=True)
                        for chunk in r.iter_content(chunk_size=4096):
                            dl += len(chunk)
                            f.write(chunk)
                            prg.update(dl)
                        prg.erase()
                return True
            except requests.RequestException as e:
                self.log.warning(colored(f"  ⚠️  Error on attempt {attempt + 1}: {e}", 'yellow'))
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise
        return False

    def poll_report(self, report_id: str, interval: int = 10, timeout: int = 3600) -> RSReport:
        """Poll a report until it reaches a terminal state (COMPLETE, ERROR, STOPPED).

        Args:
            report_id:  UUID of the report.
            interval:   Seconds between status checks (default 10).
            timeout:    Max seconds to wait (default 3600).
        """
        terminal = {'COMPLETE', 'ERROR', 'STOPPED', 'DELETED'}
        status_icons = {
            'CREATED': '📝', 'QUEUED': '⏳', 'RUNNING': '🔄',
            'COMPLETE': '✅', 'ERROR': '❌', 'STOPPED': '🛑', 'DELETED': '🗑️',
        }
        elapsed = 0
        while elapsed < timeout:
            report = self.get_report(report_id)
            icon = status_icons.get(report.status, '❓')
            status_color = 'green' if report.status == 'COMPLETE' else 'red' if report.status in ('ERROR', 'STOPPED') else 'cyan'
            self.log.info(colored(f"  {icon} [{report.status}] {report.progress}% — {report.status_message or ''}", status_color))
            if report.status in terminal:
                return report
            time.sleep(interval)
            elapsed += interval
        raise ReportsAPIException(f"⏰ Timed out after {timeout}s waiting for report {report_id}")


if __name__ == '__main__':
    log = Logger('ReportsAPI')
    with ReportsAPI(stage='staging') as api:
        profile = api.get_profile()
        log.info(colored(f"👤 Logged in as: {profile['name']}", 'green'))
        for rt in api.list_report_types():
            log.info(f"  📋 {rt.id}: {rt.name} v{rt.version}")
