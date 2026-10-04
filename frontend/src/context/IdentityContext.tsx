import { createContext, useContext, useState, type ReactNode } from 'react'
import { clearStoredName, getStoredName, setStoredName } from '../lib/api'

interface IdentityContextValue {
  name: string
  setName: (name: string) => void
  signOut: () => void
}

const IdentityContext = createContext<IdentityContextValue | undefined>(undefined)

export function IdentityProvider({ children }: { children: ReactNode }) {
  const [name, setNameState] = useState<string>(getStoredName())

  const setName = (next: string) => {
    setStoredName(next)
    setNameState(next.trim())
  }

  const signOut = () => {
    clearStoredName()
    setNameState('')
  }

  return (
    <IdentityContext.Provider value={{ name, setName, signOut }}>
      {children}
    </IdentityContext.Provider>
  )
}

export function useIdentity(): IdentityContextValue {
  const ctx = useContext(IdentityContext)
  if (!ctx) throw new Error('useIdentity must be used within IdentityProvider')
  return ctx
}
