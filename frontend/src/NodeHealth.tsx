import { useEffect, useState } from 'react'
import { api } from './api'

type NodeHealthResult = {
  configured: boolean
  healthy: boolean
  schedulingAvailable: boolean
  message: string
  checkedAt: number
}

export function NodeHealth() {
  const [result, setResult] = useState<NodeHealthResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    async function check() {
      try {
        const next = await api.get<NodeHealthResult>('/backend/remote-node/health')
        if (active) { setResult(next); setError(null) }
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : 'Could not check the node')
      } finally {
        if (active) setLoading(false)
      }
    }
    void check()
    return () => { active = false }
  }, [refreshKey])

  const healthy = !loading && !error && result?.healthy
  const failed = !loading && (Boolean(error) || Boolean(result?.configured && !result.healthy))
  const label = loading ? 'Checking: Node' : error ? 'Unknown: Node' : !result?.configured ? 'Not configured: Node' : healthy ? 'Online: Node' : 'Offline: Node'
  const detail = loading ? 'Checking the remote node…' : error ?? result?.message ?? 'Node health has not been checked.'
  const checked = !loading && !error && result ? ` Checked ${new Date(result.checkedAt * 1000).toLocaleTimeString()}.` : ''

  return <button
    className={`status-pill node-health ${healthy ? 'status-pill--ready' : failed ? 'status-pill--error' : 'status-pill--quiet'}`}
    type="button"
    disabled={loading}
    aria-busy={loading}
    aria-label={`${label}. ${detail} Click to check again.`}
    title={`${detail}${checked} Click to check again.`}
    onClick={() => { setLoading(true); setRefreshKey((key) => key + 1) }}
  >{label}</button>
}
