/**
 * Introspect the Reports GraphQL API and update the local schema file.
 */

import * as fs from 'node:fs'
import * as path from 'node:path'
import { select } from '@inquirer/prompts'
import { type IntrospectionQuery, getIntrospectionQuery, buildClientSchema, printSchema } from 'graphql'

const API_URLS: Record<string, string> = {
  staging: 'https://api.reports.riverscapes.net/staging',
  production: 'https://api.reports.riverscapes.net',
}

const SCHEMA_PATH = path.resolve(import.meta.dirname, '..', 'src', 'graphql', 'rs-reports.schema.graphql')

async function main(): Promise<void> {
  const stage = await select({
    message: 'Which API stage to introspect?',
    choices: Object.keys(API_URLS).map((s) => ({ name: s, value: s })),
    default: 'staging',
  })

  const url = API_URLS[stage]
  console.log(`Introspecting ${stage} API at ${url} ...`)

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: getIntrospectionQuery() }),
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status} from API`)
  }

  const result = (await response.json()) as { data?: Record<string, unknown>; errors?: unknown[] }

  if (result.errors) {
    throw new Error(`Introspection failed: ${JSON.stringify(result.errors)}`)
  }

  const schema = buildClientSchema(result.data as unknown as IntrospectionQuery)
  const sdl = printSchema(schema)

  fs.writeFileSync(SCHEMA_PATH, sdl + '\n', 'utf-8')
  console.log(`Schema written to ${SCHEMA_PATH}`)
}

main().catch(console.error)
