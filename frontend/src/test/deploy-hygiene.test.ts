/**
 * Deployment-hygiene regression tests.
 *
 * `frontend/node_modules` is 260 MB, and the repository also carries a 61 MB
 * Python virtualenv. Neither is in version control and neither belongs in a
 * shipped image: both are rebuilt from a lockfile during the Docker build. The
 * Node tree is worse than merely large — it holds Windows-built native binaries
 * (`@rolldown/binding-win32-x64-msvc`, `lightningcss.win32-x64-msvc.node`), and
 * copying those into a Linux container fails at *runtime*, not at build time.
 *
 * That separation is not a property of the code. It is a property of two
 * configuration files, and it is one careless edit away from failing silently:
 *
 *   * Adding `COPY . .` to the runtime stage of `Dockerfile`, or widening
 *     `COPY --from=build /app/dist` to `COPY --from=build /app`, drags the whole
 *     tree across the stage boundary. The image still works — it is just several
 *     hundred megabytes larger and carries a Node toolchain into an nginx
 *     container.
 *   * Deleting the `node_modules/` line from `.dockerignore` sends the tree to
 *     the daemon on every build, which is the difference between a fast build
 *     and a slow one.
 *
 * Nothing else in the suite would notice either change, so both vectors are
 * asserted directly here.
 *
 * ## What this file does not cover
 *
 * `docker-compose.yml` and the repository-root `.gitignore` sit above the Vite
 * root, and `import.meta.glob` cannot reach outside it. Those are checked by
 * hand; what is enforced here is the frontend's own `Dockerfile`,
 * `.dockerignore` and `.gitignore`.
 *
 * ## Two constraints worth knowing before editing this file
 *
 * 1. `tsconfig.app.json` lists only `vite/client` in `types`, so no Node type
 *    definitions are in scope under `src/`. The files are therefore read through
 *    `import.meta.glob` rather than `node:fs`, for the same reason
 *    `numerals.test.ts` does it. Adding `node` to `types` would put Node globals
 *    in scope for the whole application.
 * 2. `import.meta.glob` rejects a pattern with no wildcard — `'/Dockerfile'`
 *    throws `Expected pattern to be a non-empty string` at transform time. The
 *    patterns below are deliberately written as `'/Docker*'` and `'/.docker*'`.
 *    Do not "simplify" them to the literal filenames.
 */

import { describe, expect, it } from 'vitest'

// ---------------------------------------------------------------------------
// Reading the configuration files
// ---------------------------------------------------------------------------

/**
 * `?raw` so the contents arrive as text. `eager` because the assertions are
 * synchronous, and the leading `/` resolves against the Vite root — which is
 * `frontend/`, exactly where these files live. Dotfiles are matched: a probe
 * against `'/.*'` returned `.dockerignore`, `.gitignore` and `.oxlintrc.json`.
 */
const DOCKERFILE_GLOB = import.meta.glob('/Docker*', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const DOCKERIGNORE_GLOB = import.meta.glob('/.docker*', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const GITIGNORE_GLOB = import.meta.glob('/.git*', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** The single file a glob matched. Fails loudly if the file was renamed away. */
function only(globbed: Record<string, string>, label: string): string {
  const paths = Object.keys(globbed)
  expect(paths, `${label}: expected exactly one match, found ${paths.length}`).toHaveLength(1)
  return globbed[paths[0]]
}

// ---------------------------------------------------------------------------
// Dockerfile parsing
// ---------------------------------------------------------------------------

/** Instructions only: comments and blank lines carry no meaning for Docker. */
function instructions(dockerfile: string): string[] {
  return dockerfile
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith('#'))
}

/** Index of the final `FROM` — the start of the image that actually ships. */
function runtimeStageStart(lines: string[]): number {
  let start = -1
  lines.forEach((line, index) => {
    if (/^FROM\b/i.test(line)) start = index
  })
  return start
}

/**
 * The source paths of a `COPY`/`ADD`, minus flags and the trailing destination.
 *
 * Shell form only (`COPY a b`), which is what this Dockerfile uses. The exec
 * form (`COPY ["a", "b"]`) would need JSON parsing; if it is ever adopted, this
 * helper must learn it or the guard goes quiet.
 */
function copySources(line: string): string[] {
  const tokens = line.replace(/^(COPY|ADD)\b/i, '').trim().split(/\s+/)
  const paths = tokens.filter((token) => !token.startsWith('--'))
  return paths.slice(0, -1)
}

/**
 * Whether a copy source is a directory that contains `node_modules`.
 *
 * `.` is the whole build context, `/app` is the whole build stage workspace —
 * the tree is installed at `/app/node_modules` — and an explicit `node_modules`
 * needs no explanation.
 */
function isWholeTree(source: string): boolean {
  const trimmed = source.replace(/\/+$/, '')
  return (
    trimmed === '.' ||
    trimmed === '' ||
    trimmed === '/app' ||
    trimmed === 'app' ||
    /(^|\/)node_modules$/.test(trimmed)
  )
}

// ---------------------------------------------------------------------------
// Ignore-file parsing
// ---------------------------------------------------------------------------

/** Rule lines only, in order, so a later negation can be detected. */
function rules(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith('#'))
}

/** Strip the leading/trailing slashes so `node_modules/` and `/node_modules` agree. */
function normalise(rule: string): string {
  return rule.replace(/^\/+/, '').replace(/\/+$/, '')
}

function excludes(rules_: string[], name: string): boolean {
  return rules_.some((rule) => !rule.startsWith('!') && normalise(rule) === name)
}

/** A `!name` or `!name/…` rule re-admits something an earlier line excluded. */
function reIncludes(rules_: string[], name: string): boolean {
  return rules_.some((rule) => {
    if (!rule.startsWith('!')) return false
    const target = normalise(rule.slice(1))
    return target === name || target.startsWith(`${name}/`)
  })
}

// ---------------------------------------------------------------------------
// The image that ships
// ---------------------------------------------------------------------------

describe('the runtime image cannot carry node_modules', () => {
  const dockerfile = instructions(only(DOCKERFILE_GLOB, 'Dockerfile'))
  const start = runtimeStageStart(dockerfile)
  const runtime = dockerfile.slice(start)

  it('is a separate stage from the build', () => {
    // A single-stage Dockerfile has no boundary at all, so the dependency tree
    // installed for the build is the dependency tree that ships.
    expect(start, 'expected a build stage followed by a runtime stage').toBeGreaterThan(0)
  })

  it('is not based on Node', () => {
    expect(runtime[0]).not.toMatch(/^FROM\s+\S*node/i)
  })

  it('never runs a package manager', () => {
    const offenders = runtime.filter((line) =>
      /^RUN\b.*\b(npm|npx|yarn|pnpm|corepack)\b/i.test(line),
    )
    expect(offenders, 'the runtime stage must not install anything').toEqual([])
  })

  it('copies only explicit paths across the stage boundary', () => {
    const offenders = runtime.filter((line) => {
      if (!/^(COPY|ADD)\b/i.test(line)) return false
      return copySources(line).some(isWholeTree)
    })
    expect(offenders, 'a whole-tree copy re-introduces node_modules').toEqual([])
  })
})

// ---------------------------------------------------------------------------
// The build context
// ---------------------------------------------------------------------------

describe('the build context excludes what the build regenerates', () => {
  const dockerignore = rules(only(DOCKERIGNORE_GLOB, '.dockerignore'))

  it('excludes node_modules', () => {
    expect(excludes(dockerignore, 'node_modules')).toBe(true)
  })

  it('does not re-include node_modules afterwards', () => {
    expect(reIncludes(dockerignore, 'node_modules')).toBe(false)
  })

  it('excludes the build output', () => {
    // `dist/` is rebuilt by `npm run build` inside the stage; sending the local
    // copy only risks a stale bundle being copied over a fresh one.
    expect(excludes(dockerignore, 'dist')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Version control
// ---------------------------------------------------------------------------

describe('node_modules stays out of version control', () => {
  const gitignore = rules(only(GITIGNORE_GLOB, '.gitignore'))

  it('is ignored', () => {
    expect(excludes(gitignore, 'node_modules')).toBe(true)
  })

  it('is not re-included afterwards', () => {
    expect(reIncludes(gitignore, 'node_modules')).toBe(false)
  })
})
