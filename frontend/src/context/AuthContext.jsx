import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, getToken, setToken } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(Boolean(getToken()))

  useEffect(() => {
    const signedOut = () => setUser(null)
    window.addEventListener('bugsense:signed-out', signedOut)
    return () => window.removeEventListener('bugsense:signed-out', signedOut)
  }, [])

  useEffect(() => {
    if (!getToken()) return
    api.get('/auth/me').then(setUser).catch(() => setUser(null)).finally(() => setChecking(false))
  }, [])

  const accept = useCallback((result) => {
    setToken(result.access_token)
    setUser(result.user)
  }, [])

  const value = useMemo(
    () => ({
      user,
      checking,
      login: async (email, password) => accept(await api.post('/auth/login', { email, password })),
      register: async (form) => accept(await api.post('/auth/register', form)),
      logout: () => {
        setToken(null)
        setUser(null)
      },
    }),
    [user, checking, accept],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
