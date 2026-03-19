/**
 * A simple terminal spinner that displays elapsed time.
 *
 * Usage:
 *   const result = await Spinner.run('Running query', () => api.runQuery(query, variables))
 */

const CHARS = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'

export class Spinner {
  /**
   * Show a braille spinner with elapsed seconds while `fn` executes.
   * Returns the resolved value of `fn`.
   */
  static async run<T>(message: string, fn: () => Promise<T>): Promise<T> {
    const start = Date.now()
    let i = 0

    const timer = setInterval(() => {
      const elapsed = ((Date.now() - start) / 1000).toFixed(1)
      process.stdout.write(`\r  ${CHARS[i % CHARS.length]} ${message}... ${elapsed}s`)
      i++
    }, 100)

    try {
      const result = await fn()
      const elapsed = ((Date.now() - start) / 1000).toFixed(1)
      clearInterval(timer)
      process.stdout.write(`\r  ✔ ${message} complete in ${elapsed}s\n`)
      return result
    } catch (err) {
      const elapsed = ((Date.now() - start) / 1000).toFixed(1)
      clearInterval(timer)
      process.stdout.write(`\r  ✖ ${message} failed after ${elapsed}s\n`)
      throw err
    }
  }
}
