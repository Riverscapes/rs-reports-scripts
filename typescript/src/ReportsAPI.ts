/**
 * ReportsAPI — TypeScript client for the Riverscapes Reports GraphQL API.
 *
 * Handles authentication (browser PKCE or machine credentials), query execution,
 * and response parsing. All communication goes through a single GraphQL endpoint.
 *
 * Usage:
 *   const api = new ReportsAPI({ stage: 'production' });
 *   await api.open();
 *   try {
 *     const reportTypes = await api.listReportTypes();
 *     const report = await api.createReport({ name: 'My Report', reportTypeId: reportTypes[0].id! });
 *     await api.startReport(report.id!);
 *     const final = await api.pollReport(report.id!);
 *     console.log(final.status);
 *   } finally {
 *     api.close();
 *   }
 */

import * as fs from 'node:fs'
import * as path from 'node:path'
import * as http from 'node:http'
import * as crypto from 'node:crypto'
import { URL, URLSearchParams } from 'node:url'
import { RSReport, RSReportType, type RSReportJson, type RSReportTypeJson } from './reportsHelpers.js'

const LOCAL_PORT = 4721
const ALT_PORT = 4723
const LOGIN_SCOPE = 'openid'

const AUTH_DETAILS = {
  domain: 'auth.riverscapes.net',
  clientId: 'Vhse6GZoU6vlJ9fcbrdmAAK6b4J9sjtT',
}

export interface MachineAuth {
  clientId: string
  secretId: string
}

export interface ReportsAPIOptions {
  /** 'production', 'staging', or 'local' */
  stage: string
  /** Machine credentials for headless environments */
  machineAuth?: MachineAuth
  /** Raw headers injected into every request (for local dev) */
  devHeaders?: Record<string, string>
}

/**
 * Raised when the Reports API returns an error or unexpected HTTP status.
 */
export class ReportsAPIException extends Error {
  constructor(message = 'ReportsAPI encountered an error') {
    super(message)
    this.name = 'ReportsAPIException'
  }
}

/**
 * Client for the Riverscapes Reports GraphQL API.
 *
 * Call open() to authenticate and close() to release resources.
 */
export class ReportsAPI {
  private stage: string
  private machineAuth?: MachineAuth
  private devHeaders?: Record<string, string>
  private accessToken: string | null = null
  private refreshTimer: ReturnType<typeof setTimeout> | null = null
  private authPort: number
  private uri: string

  constructor(options: ReportsAPIOptions) {
    this.stage = options.stage.toUpperCase()
    this.machineAuth = options.machineAuth
    this.devHeaders = options.devHeaders
    this.authPort = process.env['RSAPI_ALTPORT'] ? ALT_PORT : LOCAL_PORT

    if (this.stage === 'PRODUCTION') {
      this.uri = 'https://api.reports.riverscapes.net'
    } else if (this.stage === 'STAGING') {
      this.uri = 'https://api.reports.riverscapes.net/staging'
    } else if (this.stage === 'LOCAL') {
      this.uri = 'http://localhost:7016'
    } else {
      throw new ReportsAPIException(`Unknown stage: '${options.stage}'. Must be "production", "staging", or "local".`)
    }
  }

  /** Authenticate and prepare the client for use. */
  async open(): Promise<ReportsAPI> {
    await this.refreshToken()
    return this
  }

  /** Cancel background token-refresh timer and release resources. */
  close(): void {
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer)
      this.refreshTimer = null
    }
  }

  // ---------------------------------------------------------------------------
  // Authentication
  // ---------------------------------------------------------------------------

  private generateRandom(size: number): string {
    const charset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
    const bytes = crypto.randomBytes(size)
    return Array.from(bytes, (b) => charset[b % charset.length]).join('')
  }

  private generateChallenge(codeVerifier: string): string {
    const hash = crypto.createHash('sha256').update(codeVerifier, 'utf8').digest()
    return hash.toString('base64url')
  }

  async refreshToken(force = false): Promise<void> {
    console.log(`Authenticating on Reports API: ${this.uri}`)

    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer)
      this.refreshTimer = null
    }

    if (this.devHeaders && Object.keys(this.devHeaders).length > 0) {
      return
    }

    if (this.accessToken && !force) {
      return
    }

    if (this.machineAuth) {
      const tokenUri = this.uri.replace(/\/+$/, '') + '/token'
      const body = new URLSearchParams({
        audience: 'https://api.riverscapes.net',
        grant_type: 'client_credentials',
        scope: 'machine:admin',
        client_id: this.machineAuth.clientId,
        client_secret: this.machineAuth.secretId,
      })

      const response = await fetch(tokenUri, {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      })

      const result = (await response.json()) as { access_token: string }
      this.accessToken = result.access_token
      console.log('SUCCESSFUL Machine Authentication')
    } else {
      const open = (await import('open')).default
      const codeVerifier = this.generateRandom(128)
      const codeChallenge = this.generateChallenge(codeVerifier)
      const state = this.generateRandom(32)
      const redirectUrl = `http://localhost:${this.authPort}/rs-reports`

      const loginParams = new URLSearchParams({
        client_id: AUTH_DETAILS.clientId,
        response_type: 'code',
        scope: LOGIN_SCOPE,
        state,
        audience: 'https://api.riverscapes.net',
        redirect_uri: redirectUrl,
        code_challenge: codeChallenge,
        code_challenge_method: 'S256',
      })

      const loginUrl = `https://${AUTH_DETAILS.domain}/authorize?${loginParams}`
      await open(loginUrl)

      const authCode = await this.waitForAuthCode()

      const tokenBody = new URLSearchParams({
        grant_type: 'authorization_code',
        client_id: AUTH_DETAILS.clientId,
        code_verifier: codeVerifier,
        code: authCode,
        redirect_uri: redirectUrl,
      })

      const tokenResponse = await fetch(`https://${AUTH_DETAILS.domain}/oauth/token`, {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body: tokenBody.toString(),
      })

      if (!tokenResponse.ok) {
        throw new ReportsAPIException(`Authentication failed: HTTP ${tokenResponse.status}`)
      }

      const res = (await tokenResponse.json()) as { access_token: string; expires_in: number }
      this.accessToken = res.access_token

      // Schedule token refresh 20 seconds before expiry
      const refreshMs = (res.expires_in - 20) * 1000
      this.refreshTimer = setTimeout(() => {
        this.refreshToken(true).catch((err) => console.error('Token refresh failed:', err))
      }, refreshMs)

      console.log('SUCCESSFUL Browser Authentication')
    }
  }

  private waitForAuthCode(): Promise<string> {
    return new Promise((resolve, reject) => {
      const server = http.createServer((req, res) => {
        res.writeHead(200, { 'Content-Type': 'text/html' })
        const redirectTarget = 'https://reports.riverscapes.net/login_success'
        res.end(
          `<html><head><title>Reports API: Auth successful</title>` +
            `<script>window.onload=function(){window.location.replace('${redirectTarget}');}</script>` +
            `</head><body><p>Authentication successful. Redirecting...</p></body></html>`
        )

        const parsed = new URL(req.url ?? '/', `http://localhost:${this.authPort}`)
        const code = parsed.searchParams.get('code')
        if (code) {
          server.close()
          resolve(code)
        }
      })

      server.listen(this.authPort, 'localhost', () => {
        console.log('Waiting for browser authentication (Ctrl-C to cancel)...')
      })

      server.on('error', (err) => {
        reject(new ReportsAPIException(`Auth server error: ${err.message}`))
      })
    })
  }

  // ---------------------------------------------------------------------------
  // GraphQL helpers
  // ---------------------------------------------------------------------------

  /** Read a .graphql file from the graphql/queries/ directory. */
  loadQuery(queryName: string): string {
    const filePath = path.resolve(import.meta.dirname, 'graphql', 'queries', `${queryName}.graphql`)
    return fs.readFileSync(filePath, 'utf-8')
  }

  /** Read a .graphql file from the graphql/mutations/ directory. */
  loadMutation(mutationName: string): string {
    // Allow absolute/relative paths as well
    if (fs.existsSync(mutationName)) {
      return fs.readFileSync(mutationName, 'utf-8')
    }
    const filePath = path.resolve(import.meta.dirname, 'graphql', 'mutations', `${mutationName}.graphql`)
    return fs.readFileSync(filePath, 'utf-8')
  }

  /**
   * Execute a GraphQL query or mutation against the API endpoint.
   *
   * Adds the Authorization header automatically. If the server responds
   * with an authentication error the token is refreshed once and retried.
   */
  async runQuery(query: string, variables: Record<string, unknown>): Promise<Record<string, unknown>> {
    const headers: Record<string, string> = {}
    if (this.accessToken) {
      headers['authorization'] = `Bearer ${this.accessToken}`
    }
    if (this.devHeaders) {
      Object.assign(headers, this.devHeaders)
    }
    headers['content-type'] = 'application/json'

    const response = await fetch(this.uri, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query, variables }),
    })

    if (response.ok) {
      const respJson = (await response.json()) as {
        data?: Record<string, unknown>
        errors?: Array<{ message: string }>
      }

      if (respJson.errors && respJson.errors.length > 0) {
        const authError = respJson.errors.some((e) => e.message.includes('You must be authenticated'))
        if (authError) {
          await this.refreshToken(true)
          return this.runQuery(query, variables)
        }
        throw new ReportsAPIException(
          `Query failed: ${JSON.stringify(respJson.errors)}. Variables: ${JSON.stringify(variables)}`
        )
      }

      return respJson as Record<string, unknown>
    }

    throw new ReportsAPIException(`HTTP ${response.status} from API. Variables: ${JSON.stringify(variables)}`)
  }

  // ---------------------------------------------------------------------------
  // Profile
  // ---------------------------------------------------------------------------

  /** Get the profile of the currently authenticated user. */
  async getProfile(): Promise<Record<string, unknown>> {
    const qry = this.loadQuery('getProfile')
    const result = (await this.runQuery(qry, {})) as { data: { profile: Record<string, unknown> } }
    return result.data.profile
  }

  // ---------------------------------------------------------------------------
  // Report Types
  // ---------------------------------------------------------------------------

  /** Return all available report types. */
  async listReportTypes(): Promise<RSReportType[]> {
    const qry = this.loadQuery('listReportTypes')
    const result = (await this.runQuery(qry, {})) as {
      data: { reportTypes: { items: RSReportTypeJson[] } }
    }
    return result.data.reportTypes.items.map((item) => new RSReportType(item))
  }

  /** Get a single report type by ID. */
  async getReportType(reportTypeId: string): Promise<RSReportType> {
    const qry = this.loadQuery('getReportType')
    const result = (await this.runQuery(qry, { id: reportTypeId })) as {
      data: { reportType: RSReportTypeJson }
    }
    return new RSReportType(result.data.reportType)
  }

  // ---------------------------------------------------------------------------
  // Reports
  // ---------------------------------------------------------------------------

  /** Get a single report by its UUID. */
  async getReport(reportId: string): Promise<RSReport> {
    const qry = this.loadQuery('getReport')
    const result = (await this.runQuery(qry, { reportId })) as {
      data: { report: RSReportJson }
    }
    return new RSReport(result.data.report)
  }

  /** Return a page of the current user's reports. */
  async listReports(limit = 50, offset = 0): Promise<{ reports: RSReport[]; total: number }> {
    const qry = this.loadQuery('listReports')
    const result = (await this.runQuery(qry, { limit, offset })) as {
      data: { profile: { reports: { items: RSReportJson[]; total: number } } }
    }
    const pagination = result.data.profile.reports
    return {
      reports: pagination.items.map((item) => new RSReport(item)),
      total: pagination.total,
    }
  }

  /** Yield every report for the current user, handling pagination automatically. */
  async *iterReports(pageSize = 50): AsyncGenerator<RSReport> {
    let offset = 0
    let total = -1
    while (total < 0 || offset < total) {
      const page = await this.listReports(pageSize, offset)
      total = page.total
      for (const report of page.reports) {
        yield report
      }
      offset += page.reports.length
      if (page.reports.length === 0) break
    }
  }

  /** Return a page of all reports across all users (admin). */
  async globalReports(limit = 50, offset = 0): Promise<{ reports: RSReport[]; total: number }> {
    const qry = this.loadQuery('globalReports')
    const result = (await this.runQuery(qry, { limit, offset })) as {
      data: { globalReports: { items: RSReportJson[]; total: number } }
    }
    const pagination = result.data.globalReports
    return {
      reports: pagination.items.map((item) => new RSReport(item)),
      total: pagination.total,
    }
  }

  /** Create a new report (status: CREATED). */
  async createReport(options: {
    name: string
    reportTypeId: string
    description?: string
    parameters?: Record<string, unknown>
    extent?: Record<string, unknown>
  }): Promise<RSReport> {
    const reportInput: Record<string, unknown> = {
      name: options.name,
      reportTypeId: options.reportTypeId,
    }
    if (options.description) reportInput['description'] = options.description
    if (options.parameters) reportInput['parameters'] = options.parameters
    if (options.extent) reportInput['extent'] = options.extent

    const mut = this.loadMutation('createReport')
    const result = (await this.runQuery(mut, { report: reportInput })) as {
      data: { createReport: RSReportJson }
    }
    return new RSReport(result.data.createReport)
  }

  /** Attach a picker layer item to a report. */
  async attachPickerOption(reportId: string, pickerLayer: string, pickerItemId: string): Promise<RSReport> {
    const mut = this.loadMutation('attachPickerOptionToReport')
    const result = (await this.runQuery(mut, { reportId, pickerLayer, pickerItemId })) as {
      data: { attachPickerOptionToReport: RSReportJson }
    }
    return new RSReport(result.data.attachPickerOptionToReport)
  }

  /** Start a report (moves to QUEUED or RUNNING). */
  async startReport(reportId: string): Promise<RSReport> {
    const mut = this.loadMutation('startReport')
    const result = (await this.runQuery(mut, { reportId })) as {
      data: { startReport: RSReportJson }
    }
    return new RSReport(result.data.startReport)
  }

  /** Stop a running report. */
  async stopReport(reportId: string): Promise<RSReport> {
    const mut = this.loadMutation('stopReport')
    const result = (await this.runQuery(mut, { reportId })) as {
      data: { stopReport: RSReportJson }
    }
    return new RSReport(result.data.stopReport)
  }

  /** Delete a report and its S3 files. */
  async deleteReport(reportId: string): Promise<RSReport> {
    const mut = this.loadMutation('deleteReport')
    const result = (await this.runQuery(mut, { reportId })) as {
      data: { deleteReport: RSReportJson }
    }
    return new RSReport(result.data.deleteReport)
  }

  // ---------------------------------------------------------------------------
  // File Operations
  // ---------------------------------------------------------------------------

  /** Get pre-signed S3 upload URLs. */
  async getUploadUrls(
    reportId: string,
    filePaths: string[],
    fileType?: string
  ): Promise<Array<{ fileType: string; url: string; fields: Record<string, unknown> }>> {
    const qry = this.loadQuery('uploadUrls')
    const variables: Record<string, unknown> = { reportId, filePaths }
    if (fileType) variables['fileType'] = fileType
    const result = (await this.runQuery(qry, variables)) as {
      data: { uploadUrls: Array<{ fileType: string; url: string; fields: Record<string, unknown> }> }
    }
    return result.data.uploadUrls
  }

  /** Get pre-signed S3 download URLs. */
  async getDownloadUrls(
    reportId: string,
    fileTypes?: string[]
  ): Promise<Array<{ fileType: string; url: string; fields: Record<string, unknown> }>> {
    const qry = this.loadQuery('downloadUrls')
    const variables: Record<string, unknown> = { reportId }
    if (fileTypes) variables['fileTypes'] = fileTypes
    const result = (await this.runQuery(qry, variables)) as {
      data: { downloadUrls: Array<{ fileType: string; url: string; fields: Record<string, unknown> }> }
    }
    return result.data.downloadUrls
  }

  /** Upload a local file to the report's S3 folder with retry. */
  async uploadFile(reportId: string, localPath: string, remotePath: string, fileType = 'INPUTS'): Promise<boolean> {
    const urls = await this.getUploadUrls(reportId, [remotePath], fileType)
    if (!urls.length) {
      throw new ReportsAPIException(`No upload URL returned for: ${remotePath}`)
    }

    const uploadUrl = urls[0].url
    console.log(`Uploading ${localPath} -> ${remotePath}`)

    const maxRetries = 3
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const fileData = fs.readFileSync(localPath)
        const response = await fetch(uploadUrl, {
          method: 'PUT',
          body: fileData,
        })

        if (response.status === 200 || response.status === 201) {
          console.log(`  Upload successful: ${remotePath}`)
          return true
        }

        const text = await response.text()
        console.warn(`  HTTP ${response.status} on attempt ${attempt + 1}: ${text.slice(0, 200)}`)
      } catch (err) {
        console.warn(`  Network error on attempt ${attempt + 1}: ${err}`)
      }

      if (attempt < maxRetries - 1) {
        await this.sleep(2 ** attempt * 1000)
      }
    }

    throw new ReportsAPIException(`Upload failed for ${remotePath} after ${maxRetries} attempts`)
  }

  /** Download a file from a pre-signed S3 URL. */
  async downloadFile(url: string, localPath: string, force = false): Promise<boolean> {
    if (!force && fs.existsSync(localPath)) {
      console.log(`  Skipping (already exists): ${localPath}`)
      return false
    }

    const dir = path.dirname(path.resolve(localPath))
    fs.mkdirSync(dir, { recursive: true })

    console.log(`  Downloading: ${localPath}`)

    const maxRetries = 3
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const response = await fetch(url, { redirect: 'follow' })
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        const buffer = Buffer.from(await response.arrayBuffer())
        fs.writeFileSync(localPath, buffer)
        return true
      } catch (err) {
        console.warn(`  Error on attempt ${attempt + 1}: ${err}`)
        if (attempt < maxRetries - 1) {
          await this.sleep(2 ** attempt * 1000)
        } else {
          throw err
        }
      }
    }

    return false
  }

  /**
   * Poll a report until it reaches a terminal state (COMPLETE, ERROR, STOPPED, DELETED).
   */
  async pollReport(reportId: string, interval = 10, timeout = 3600): Promise<RSReport> {
    const terminal = new Set(['COMPLETE', 'ERROR', 'STOPPED', 'DELETED'])
    let elapsed = 0

    while (elapsed < timeout) {
      const report = await this.getReport(reportId)
      console.log(`  [${report.status}] ${report.progress}% — ${report.statusMessage ?? ''}`)

      if (terminal.has(report.status!)) {
        return report
      }

      await this.sleep(interval * 1000)
      elapsed += interval
    }

    throw new ReportsAPIException(`Timed out after ${timeout}s waiting for report ${reportId}`)
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }
}
