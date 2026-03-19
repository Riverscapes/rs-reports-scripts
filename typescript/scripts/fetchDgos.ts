/**
 * Interactive script to demonstrate DGO-related GraphQL queries.
 */

import { select, input } from '@inquirer/prompts'
import { ReportsAPI } from '../src/index.js'

interface QueryEntry {
  variables: string[]
  queryFile: string
}

const QUERIES: Record<string, QueryEntry> = {
  'Fetch all DGOs inside a HUC10 (paginated)': {
    variables: ['huc10'],
    queryFile: 'fetchDGOsByHuc10',
  },
  'Fetch a signed S3 URL to download raw Parquet data': {
    variables: ['huc10'],
    queryFile: 'fetchDGOParquetByHuc10',
  },
  'Fetch DGOs between a start and end segment distance of a given levelPath': {
    variables: ['huc10', 'startLevelPath', 'startSegmentDistance', 'endSegmentationDistance'],
    queryFile: 'fetchDGOsByLevelPathEnd',
  },
  'Fetch DGOs downstream of a given levelPath by segmentDistance': {
    variables: ['huc10', 'startLevelPath', 'startSegmentDistance', 'distance'],
    queryFile: 'fetchDGOsByLevelPathDistance',
  },
  'Fetch all DGOs downstream of a given levelPath and count': {
    variables: ['huc10', 'startLevelPath', 'startSegmentDistance', 'count'],
    queryFile: 'fetchDGOsByLevelPathCount',
  },
  'Fetch DGOs by a specific list of DGO IDs': {
    variables: ['huc10', 'dgoIds'],
    queryFile: 'fetchDGOs',
  },
}

const DEFAULTS: Record<string, string | number | string[]> = {
  huc10: '1602020101',
  startLevelPath: '70000400028442',
  startSegmentDistance: 1034.0,
  endSegmentationDistance: 10.0,
  distance: 500.0,
  count: 5,
  dgoIds: ['70000400028442-1034.0'],
}

async function promptVariables(varNames: string[]): Promise<Record<string, unknown>> {
  const variables: Record<string, unknown> = {}

  for (const name of varNames) {
    const defaultVal = DEFAULTS[name]

    if (name === 'dgoIds') {
      const raw = await input({
        message: `${name} (comma-separated):`,
        default: (defaultVal as string[]).join(','),
      })
      variables[name] = raw
        .split(',')
        .map((v) => v.trim())
        .filter(Boolean)
    } else if (typeof defaultVal === 'number' && !Number.isInteger(defaultVal)) {
      const raw = await input({ message: `${name}:`, default: String(defaultVal) })
      variables[name] = parseFloat(raw)
    } else if (typeof defaultVal === 'number') {
      const raw = await input({ message: `${name}:`, default: String(defaultVal) })
      variables[name] = parseInt(raw, 10)
    } else {
      variables[name] = await input({ message: `${name}:`, default: String(defaultVal) })
    }
  }

  return variables
}

async function main(): Promise<void> {
  const stage = process.argv[2]
  if (!stage || !['staging', 'production', 'local'].includes(stage)) {
    console.error('Usage: npx tsx scripts/fetchDgos.ts <staging|production|local>')
    process.exit(1)
  }

  const choice = await select({
    message: 'Which query would you like to run?',
    choices: Object.keys(QUERIES).map((label) => ({ name: label, value: label })),
  })

  const entry = QUERIES[choice]
  const variables = await promptVariables(entry.variables)

  console.log(`\n=== Running: ${choice} ===`)
  console.log(`Variables: ${JSON.stringify(variables, null, 2)}\n`)

  const api = new ReportsAPI({ stage })
  await api.open()

  try {
    const query = api.loadQuery(entry.queryFile)
    console.log(`Executing query from ${entry.queryFile}.graphql ...`)
    const result = await api.runQuery(query, variables)
    console.log(JSON.stringify(result, null, 2))
  } finally {
    api.close()
  }
}

main().catch(console.error)
