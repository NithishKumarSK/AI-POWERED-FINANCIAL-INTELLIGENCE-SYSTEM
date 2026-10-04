import { useState, type FormEvent } from 'react'
import { useIdentity } from '../context/IdentityContext'
import { apiErrorMessage, fetchMe } from '../lib/api'

export function IdentityGate() {
  const { setName } = useIdentity()
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed) {
      setError('Enter your name to continue.')
      return
    }
    setLoading(true)
    setError('')
    setName(trimmed)
    try {
      await fetchMe()
    } catch (err) {
      setError(
        `Could not reach the API: ${apiErrorMessage(err)}. Make sure the backend is running ` +
          '(uvicorn backend.main:app --port 8000).',
      )
      setLoading(false)
      return
    }
    setLoading(false)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="card w-full max-w-sm p-8">
        <div className="mb-6 flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
            AV
          </div>
          <span className="text-xl font-semibold text-slate-900">AlphaVerity</span>
        </div>
        <h1 className="text-lg font-semibold text-slate-900">Who's running this?</h1>
        <p className="mt-1 text-sm text-slate-500">
          Every prediction you run is attributed to this name in the shared team ledger.
        </p>
        <form onSubmit={handleSubmit} className="mt-5 space-y-3">
          <input
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Your name"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-60"
          >
            {loading ? 'Connecting…' : 'Continue'}
          </button>
        </form>
      </div>
    </div>
  )
}
