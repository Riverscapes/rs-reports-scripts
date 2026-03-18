/**
 * Interactive CLI script: create and run a Riverscapes Report end-to-end.
 *
 * Workflow:
 * 1. Authenticate — a browser tab opens for you to log in (OAuth 2.0 PKCE).
 * 2. Pick a report type — only types with the PICK input tool are shown.
 * 3. Name the report.
 * 4. Select a picker layer (if the report type defines any).
 * 5. Enter a picker item ID.
 * 6. Choose a unit system (if the report type supports multiple).
 * 7. Create the report.
 * 8. Attach the picker option.
 * 9. Start the report.
 * 10. Poll for completion.
 * 11. Print a link to the finished report.
 *
 * Usage:
 *   npx tsx scripts/createReport.ts staging
 *   npx tsx scripts/createReport.ts production
 */

import { select, input } from '@inquirer/prompts'
import { ReportsAPI, type RSReportType } from '../src/index.js'

function layerLabel(layerId: string): string {
  return layerId.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

async function main(): Promise<void> {
  const stage = process.argv[2]
  if (!stage || !['staging', 'production', 'local'].includes(stage)) {
    console.error('Usage: npx tsx scripts/createReport.ts <staging|production|local>')
    process.exit(1)
  }

  const api = new ReportsAPI({ stage })
  await api.open()

  try {
    console.log(`\n=== Creating report on ${stage.toUpperCase()} ===\n`)

    // ---- List report types and pick one ----
    const reportTypes = await api.listReportTypes()

    // Filter to types with PICK tool
    const filtered = reportTypes.filter((rt) => {
      const tools = (rt.parameters as Record<string, unknown> | undefined)?.['tools'] as string[] | undefined
      return tools?.includes('PICK')
    })

    const reportType: RSReportType = await select({
      message: 'Select report type:',
      choices: filtered.map((rt) => ({
        name: `${rt.name}  (v${rt.version})`,
        value: rt,
      })),
    })

    // ---- Enter a report name ----
    const defaultName = `${reportType.name} - ${new Date().toISOString().replace('T', ' ').slice(0, 19)}`
    const name = await input({
      message: 'Report name:',
      default: defaultName,
      validate: (v) => (v.trim() ? true : 'Name cannot be empty'),
    })

    // ---- Pick a picker layer ----
    const params = (reportType.parameters ?? {}) as Record<string, unknown>
    const validLayers = (params['validPickerLayers'] ?? []) as string[]

    let pickerLayer: string | null = null
    if (validLayers.length > 0) {
      pickerLayer = await select({
        message: 'Select picker layer:',
        choices: validLayers.map((layer) => ({
          name: layerLabel(layer),
          value: layer,
        })),
      })
    }

    // ---- Enter a picker item ID ----
    let pickerId: string | null = null
    if (pickerLayer) {
      pickerId = await input({
        message: `Enter ID for ${layerLabel(pickerLayer)}:`,
        default: '1302020710',
      })
    }

    // ---- Choose a unit system ----
    const parameters: Record<string, unknown> = {}
    const validUnitSystems = (params['validUnitSystems'] ?? []) as string[]
    if (validUnitSystems.length > 0) {
      parameters['units'] = await select({
        message: 'Select unit system:',
        choices: validUnitSystems.map((u) => ({
          name: u.toUpperCase(),
          value: u,
        })),
      })
    }

    // ---- Create report ----
    let report = await api.createReport({
      name: name.trim(),
      reportTypeId: reportType.id!,
      parameters,
    })

    console.log(`\x1b[32mReport created: ${report.id}\x1b[0m`)
    console.log(`  Name:   ${report.name}`)
    console.log(`  Status: ${report.status}`)
    console.log(`  Type:   ${report.reportType?.name ?? reportType.id}`)

    // ---- Attach picker option ----
    if (pickerLayer && pickerId) {
      console.log(`Attaching picker option: ${layerLabel(pickerLayer)} = ${pickerId}`)
      await api.attachPickerOption(report.id!, pickerLayer, pickerId)
      console.log(`\x1b[32mPicker option attached.\x1b[0m`)
    }

    // ---- Start report ----
    console.log('Starting report...')
    report = await api.startReport(report.id!)
    console.log(`\x1b[36mReport started (status: ${report.status})\x1b[0m`)

    // ---- Poll for completion ----
    console.log('Polling for completion every 10 seconds...')
    report = await api.pollReport(report.id!, 10)

    console.log()
    if (report.isComplete()) {
      console.log(`\x1b[32mReport COMPLETE!\x1b[0m`)
      const frontendUrls: Record<string, string> = {
        production: 'https://reports.riverscapes.net',
        staging: 'https://staging.reports.riverscapes.net',
      }
      const base = frontendUrls[stage]
      if (base && report.createdById) {
        console.log(`\x1b[32m  View report: ${base}/reports/${report.createdById}/${report.id}/report.html\x1b[0m`)
      } else if (base) {
        console.log(`\x1b[32m  View your reports: ${base}/my\x1b[0m`)
      }
    } else {
      console.error(`\x1b[31mReport ended with status: ${report.status}\x1b[0m`)
      if (report.statusMessage) {
        console.error(`  Message: ${report.statusMessage}`)
      }
    }
    console.log(`  Report ID: ${report.id}`)
    console.log()
  } finally {
    api.close()
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
