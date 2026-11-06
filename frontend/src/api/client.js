import { useCallback, useEffect, useRef, useState } from 'react'

const TOKEN_KEY = 'bugsense.token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Storage can be blocked. The session then lasts until the page reloads.
  }
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

function messageFrom(body, status) {
  // Hosting platforms can reject a large request before it reaches the API.
  if (status === 413 && !body?.detail) return 'This file is too large. Files can be up to 4 MB.'
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = item.loc?.filter((part) => part !== 'body').join(' ')
        const text = String(item.msg || '').replace(/^Value error, /, '')
        return field ? `${field.replaceAll('_', ' ')}: ${text}` : text
      })
      .join(' ')
  }
  return `The request failed (${status}).`
}

async function send(path, { method = 'GET', body, params, raw = false } = {}) {
  const query = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value)
  })
  const url = `/api${path}${query.size ? `?${query}` : ''}`
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const isForm = body instanceof FormData
  if (body && !isForm) headers['Content-Type'] = 'application/json'

  let response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: isForm ? body : body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError('Cannot reach the server. Check that the API is running on port 8100.', 0)
  }

  if (response.status === 401 && token) {
    setToken(null)
    window.dispatchEvent(new Event('bugsense:signed-out'))
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new ApiError(messageFrom(data, response.status), response.status)
  }
  if (raw) return response
  if (response.status === 204) return null
  return response.json()
}

export const api = {
  get: (path, params) => send(path, { params }),
  post: (path, body) => send(path, { method: 'POST', body }),
  put: (path, body) => send(path, { method: 'PUT', body }),
  delete: (path) => send(path, { method: 'DELETE' }),
  blob: (path) => send(path, { raw: true }).then((response) => response.blob()),
}

/** Loads data for a page. Old data stays visible during a reload, so the layout never jumps. */
export function useApi(path, params) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(path) })
  const key = JSON.stringify(params || {})
  const latest = useRef(0)

  const load = useCallback(async () => {
    if (!path) {
      setState({ data: null, error: null, loading: false })
      return
    }
    const id = ++latest.current
    setState((current) => ({ ...current, loading: true, error: null }))
    try {
      const data = await api.get(path, JSON.parse(key))
      if (id === latest.current) setState({ data, error: null, loading: false })
    } catch (error) {
      if (id === latest.current) setState((current) => ({ ...current, error: error.message, loading: false }))
    }
  }, [path, key])

  useEffect(() => {
    load()
  }, [load])

  return { ...state, reload: load, setData: (data) => setState((current) => ({ ...current, data })) }
}
