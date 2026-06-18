const fs = require('fs')
const vm = require('vm')

function clone(value) {
  return JSON.parse(JSON.stringify(value ?? null))
}

function readInput() {
  const raw = fs.readFileSync(0, 'utf8')
  return raw ? JSON.parse(raw) : {}
}

function createHelpers(sandbox) {
  return {
    setHeader(key, value) {
      sandbox.request.headers = sandbox.request.headers || {}
      sandbox.request.headers[String(key)] = value
    },
    setQuery(key, value) {
      sandbox.request.query_params = sandbox.request.query_params || {}
      sandbox.request.query_params[String(key)] = value
    },
    setBody(key, value) {
      const body = sandbox.request.body
      if (!body || typeof body !== 'object' || Array.isArray(body)) {
        sandbox.request.body = {}
      }
      sandbox.request.body[String(key)] = value
    },
    setVariable(key, value) {
      sandbox.variables[String(key)] = value
    },
    setExtractor(key, value) {
      sandbox.extracted[String(key)] = value
    },
  }
}

function main() {
  const payload = readInput()
  const logs = []
  const state = clone(payload.state || {}) || {}
  state.request = state.request || {}
  state.response = state.response || {}
  state.variables = state.variables || {}
  state.extracted = state.extracted || {}
  state.assertions = state.assertions || []
  const sandbox = {
    request: state.request,
    response: state.response,
    variables: state.variables,
    extracted: state.extracted,
    assertions: state.assertions,
    console: {
      log: (...args) => logs.push(args.map((item) => String(item)).join(' ')),
    },
  }
  sandbox.helpers = createHelpers(sandbox)
  vm.createContext(sandbox)
  vm.runInContext(String(payload.script || ''), sandbox, { timeout: 1000 })
  process.stdout.write(JSON.stringify({
    request: sandbox.request,
    response: sandbox.response,
    variables: sandbox.variables,
    extracted: sandbox.extracted,
    assertions: sandbox.assertions,
    logs,
  }))
}

try {
  main()
} catch (error) {
  process.stderr.write(String(error && error.message ? error.message : error))
  process.exit(1)
}
