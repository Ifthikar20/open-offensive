import axios from 'axios'

// Single shared axios instance. Auth is a Django session cookie (not JWT), so we
// send credentials and echo the CSRF cookie back on unsafe methods. Responses are
// plain DRF JSON — callers read `res.data` directly (no envelope unwrap).
const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

function csrfToken() {
  try {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
    return m ? decodeURIComponent(m[1]) : ''
  } catch {
    return ''
  }
}

const SAFE = new Set(['get', 'head', 'options'])

api.interceptors.request.use((config) => {
  if (!SAFE.has((config.method || 'get').toLowerCase())) {
    config.headers['X-CSRFToken'] = csrfToken()
  }
  return config
})

const FRIENDLY = {
  400: "Something didn't look right. Please check your input.",
  401: 'Please sign in to continue.',
  403: 'Your session has expired. Please sign in again.',
  404: 'Not found.',
  429: 'Too many attempts — please slow down and try again.',
  500: 'Something went wrong on our end. Please try again.',
  502: 'The server is unavailable right now. Please try again.',
  503: 'The server is unavailable right now. Please try again.',
}

/** Pull the friendliest message out of a DRF error body. */
function messageFrom(data, status) {
  if (typeof data === 'string' && data) return data
  if (data && typeof data === 'object') {
    if (typeof data.detail === 'string') return data.detail
    for (const v of Object.values(data)) {
      if (typeof v === 'string') return v
      if (Array.isArray(v) && typeof v[0] === 'string') return v[0]
    }
  }
  return FRIENDLY[status] || FRIENDLY[500]
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      error.displayMessage = messageFrom(error.response.data, error.response.status)
    } else {
      error.displayMessage = "Can't reach the server. Is the backend running?"
    }
    return Promise.reject(error)
  }
)

export default api
