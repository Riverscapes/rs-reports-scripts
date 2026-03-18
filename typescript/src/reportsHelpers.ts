/**
 * Data classes and utility functions for the Riverscapes Reports API.
 *
 * RSReportType — lightweight wrapper around the raw reportType dict from the API.
 * RSReport     — wrapper around the raw report dict with lifecycle helper methods.
 */

/**
 * Format a Date as an ISO 8601 string suitable for the API.
 * The API expects millisecond precision in UTC, e.g. '2024-01-15T09:30:00.000Z'.
 */
export function formatDate(date: Date): string {
  return date.toISOString()
}

/**
 * Return true if `guid` looks like a valid UUID / GUID string.
 * The API uses UUID v4 strings (36 characters, lower-case hex + hyphens).
 */
export function verifyGuid(guid: string): boolean {
  return /^[a-f0-9-]{36}$/.test(guid)
}

/** Raw API response dict for a report type. */
export interface RSReportTypeJson {
  id?: string
  name?: string
  shortName?: string
  description?: string
  subHeader?: string
  version?: string
  parameters?: Record<string, unknown>
  [key: string]: unknown
}

/**
 * A report type returned by the Riverscapes Reports API.
 *
 * Report types are defined by the Riverscapes team. They describe what
 * a report does, what inputs it requires, and what parameters it accepts.
 */
export class RSReportType {
  json: RSReportTypeJson
  id: string | undefined
  name: string | undefined
  shortName: string | undefined
  description: string | undefined
  subHeader: string | undefined
  version: string | undefined
  parameters: Record<string, unknown> | undefined

  constructor(obj: RSReportTypeJson) {
    this.json = obj
    this.id = obj.id
    this.name = obj.name
    this.shortName = obj.shortName
    this.description = obj.description
    this.subHeader = obj.subHeader
    this.version = obj.version
    this.parameters = obj.parameters as Record<string, unknown> | undefined
  }

  toString(): string {
    return `RSReportType(id=${this.id}, name=${this.name}, version=${this.version})`
  }
}

/** Raw API response dict for a report. */
export interface RSReportJson {
  id?: string
  name?: string
  description?: string
  status?: string
  statusMessage?: string
  progress?: number
  outputs?: unknown[]
  parameters?: Record<string, unknown>
  extent?: Record<string, unknown>
  centroid?: Record<string, unknown>
  createdAt?: string
  updatedAt?: string
  reportType?: RSReportTypeJson
  createdBy?: { id?: string; name?: string }
  [key: string]: unknown
}

/**
 * A single report record returned by the Riverscapes Reports API.
 *
 * Reports move through a defined lifecycle:
 *   CREATED → QUEUED → RUNNING → COMPLETE
 * or they may end in ERROR (processing failed) or STOPPED (manually cancelled).
 */
export class RSReport {
  json: RSReportJson
  id: string | undefined
  name: string | undefined
  description: string | undefined
  status: string | undefined
  statusMessage: string | undefined
  progress: number
  outputs: unknown[]
  parameters: Record<string, unknown> | undefined
  extent: Record<string, unknown> | undefined
  centroid: Record<string, unknown> | undefined
  createdAt: Date | null
  updatedAt: Date | null
  reportType: RSReportType | null
  createdById: string | undefined
  createdByName: string | undefined

  constructor(obj: RSReportJson) {
    this.json = obj
    this.id = obj.id
    this.name = obj.name
    this.description = obj.description
    this.status = obj.status
    this.statusMessage = obj.statusMessage
    this.progress = obj.progress ?? 0
    this.outputs = obj.outputs ?? []
    this.parameters = obj.parameters as Record<string, unknown> | undefined
    this.extent = obj.extent as Record<string, unknown> | undefined
    this.centroid = obj.centroid as Record<string, unknown> | undefined

    this.createdAt = obj.createdAt ? new Date(obj.createdAt) : null
    this.updatedAt = obj.updatedAt ? new Date(obj.updatedAt) : null

    this.reportType = obj.reportType ? new RSReportType(obj.reportType) : null

    this.createdById = obj.createdBy?.id
    this.createdByName = obj.createdBy?.name
  }

  /** Return true if the report finished successfully. */
  isComplete(): boolean {
    return this.status === 'COMPLETE'
  }

  /** Return true if the report is queued or actively processing. */
  isRunning(): boolean {
    return this.status === 'QUEUED' || this.status === 'RUNNING'
  }

  /** Return true if the report ended in an error or was stopped. */
  isFailed(): boolean {
    return this.status === 'ERROR' || this.status === 'STOPPED'
  }

  toString(): string {
    return `RSReport(id=${this.id}, name=${this.name}, status=${this.status})`
  }
}
