"""Data classes and utility functions for the Riverscapes Reports API.

This module defines:

``RSReportType``
    A lightweight wrapper around the raw ``reportType`` dict returned by the
    API.  Report types are defined by the Riverscapes team and describe what
    a report does (e.g. *Watershed Summary*, *Fish Passage Assessment*).

``RSReport``
    A wrapper around the raw ``report`` dict.  A report is a single run of a
    report type for a specific geographic area.  It has a lifecycle:
    ``CREATED`` → ``QUEUED`` → ``RUNNING`` → ``COMPLETE`` (or ``ERROR`` /
    ``STOPPED``).

Both classes store the original API dict in ``.json`` so you always have
access to any fields not yet exposed as typed attributes.
"""
import re
from datetime import datetime
from dateutil.parser import parse as dateparse
from rsxml import Logger


def format_date(date: datetime) -> str:
    """Format a ``datetime`` as an ISO 8601 string suitable for the API.

    The API expects millisecond precision in UTC, e.g.
    ``'2024-01-15T09:30:00.000Z'``.

    Parameters
    ----------
    date : datetime
        A timezone-aware or naïve ``datetime`` instance.

    Returns
    -------
    str
        ISO 8601 string with millisecond precision and a ``Z`` suffix.
    """
    return date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')[:-3]


def verify_guid(guid: str) -> bool:
    """Return ``True`` if *guid* looks like a valid UUID / GUID string.

    The API uses UUID v4 strings (36 characters, lower-case hex + hyphens) as
    primary keys for reports and report types.  Use this helper to validate
    user-supplied IDs before making API calls.

    Parameters
    ----------
    guid : str
        The string to test.

    Returns
    -------
    bool
        ``True`` if the string matches the pattern ``xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx``.

    Examples
    --------
    >>> verify_guid('550e8400-e29b-41d4-a716-446655440000')
    True
    >>> verify_guid('not-a-guid')
    False
    """
    return bool(re.match(r'^[a-f0-9-]{36}$', guid))


class RSReportType:
    """A report type returned by the Riverscapes Reports API.

    Report types are defined by the Riverscapes team.  They describe *what*
    a report does, *what inputs it requires*, and *what parameters it accepts*.
    You cannot create or modify report types through this API — you can only
    list them and select one when creating a report.

    Attributes
    ----------
    json : dict
        The raw API response dict, useful for accessing fields that are not
        yet exposed as attributes.
    id : str
        UUID primary key.  Pass this to ``ReportsAPI.create_report()``.
    name : str
        Human-readable full name, e.g. ``'Watershed Summary'``.
    short_name : str
        Slug-style identifier, e.g. ``'watershed-summary'``.
    description : str
        Longer description of what the report produces.
    sub_header : str
        Optional subtitle shown in the UI.
    version : str
        Semantic version string (``'1.2.3'``).  The platform may run an
        older version than what appears here if a report was created before
        the type was updated.
    parameters : dict
        JSON object describing accepted parameters, including
        ``validPickerLayers``, ``validUnitSystems``, and ``tools``.
        The structure varies by report type; inspect this dict to know
        what inputs a particular type requires.
    """

    def __init__(self, obj: dict):
        self.json = obj
        self.id = obj.get('id')
        self.name = obj.get('name')
        self.short_name = obj.get('shortName')
        self.description = obj.get('description')
        self.sub_header = obj.get('subHeader')
        self.version = obj.get('version')
        self.parameters = obj.get('parameters')

    def __repr__(self):
        return f"RSReportType(id={self.id!r}, name={self.name!r}, version={self.version!r})"


class RSReport:
    """A single report record returned by the Riverscapes Reports API.

    A report is one execution of a ``RSReportType`` for a specific geographic
    area.  Reports move through a defined lifecycle:

    ``CREATED`` → ``QUEUED`` → ``RUNNING`` → ``COMPLETE``

    or they may end in ``ERROR`` (processing failed) or ``STOPPED`` (manually
    cancelled).

    This class wraps the raw dict from the API and exposes the most-used fields
    as typed attributes.  The underlying dict is always available via ``.json``.

    Attributes
    ----------
    json : dict
        The raw API response dict.
    id : str
        UUID primary key.
    name : str
        Human-readable name given at creation time.
    description : str or None
        Optional longer description.
    status : str
        Current lifecycle state.  One of ``CREATED``, ``QUEUED``,
        ``RUNNING``, ``COMPLETE``, ``ERROR``, ``STOPPED``, ``DELETED``.
    status_message : str or None
        Human-readable detail about the current status.  Contains an error
        description when ``status == 'ERROR'``.
    progress : int
        Processing progress from 0 to 100.  Only meaningful when ``status``
        is ``RUNNING``.
    outputs : list
        Metadata for output files produced by the report.  Each item
        contains at least ``filePath`` and may contain a ``url`` field.
    parameters : dict or None
        The input parameters the report was created with (e.g. units).
    extent : dict or None
        GeoJSON geometry representing the geographic area of the report.
    centroid : dict or None
        GeoJSON point geometry at the centre of the report extent.
    created_at : datetime or None
        UTC timestamp when the report was created.
    updated_at : datetime or None
        UTC timestamp of the last status change.
    report_type : RSReportType or None
        The embedded report type snapshot at creation time.
    created_by_id : str or None
        UUID of the user who created the report.
    created_by_name : str or None
        Display name of the user who created the report.
    """

    def __init__(self, obj: dict):
        log = Logger('RSReport')
        try:
            self.json = obj
            self.id = obj.get('id')
            self.name = obj.get('name')
            self.description = obj.get('description')
            self.status = obj.get('status')
            self.status_message = obj.get('statusMessage')
            self.progress = obj.get('progress', 0)
            self.outputs = obj.get('outputs', [])
            self.parameters = obj.get('parameters')
            self.extent = obj.get('extent')
            self.centroid = obj.get('centroid')

            self.created_at = dateparse(obj['createdAt']) if obj.get('createdAt') else None
            self.updated_at = dateparse(obj['updatedAt']) if obj.get('updatedAt') else None

            report_type_raw = obj.get('reportType')
            self.report_type = RSReportType(report_type_raw) if report_type_raw else None

            created_by_raw = obj.get('createdBy')
            self.created_by_id = created_by_raw.get('id') if created_by_raw else None
            self.created_by_name = created_by_raw.get('name') if created_by_raw else None

        except Exception as e:
            log.error(f"Error parsing RSReport: {e}")
            raise

    def is_complete(self) -> bool:
        """Return ``True`` if the report finished successfully."""
        return self.status == 'COMPLETE'

    def is_running(self) -> bool:
        """Return ``True`` if the report is queued or actively processing."""
        return self.status in ('QUEUED', 'RUNNING')

    def is_failed(self) -> bool:
        """Return ``True`` if the report ended in an error or was stopped."""
        return self.status in ('ERROR', 'STOPPED')

    def __repr__(self):
        return f"RSReport(id={self.id!r}, name={self.name!r}, status={self.status!r})"
