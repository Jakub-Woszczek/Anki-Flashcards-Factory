import { useEffect, useState } from 'react'
import { api } from './api'

type ListCoverage = {
  name: string
  total: number
  entries: number
  invalid: number
  error: string | null
  html: number
  audio: number
  ready: number
  percent: number
  noExactMatch: number
  noAudio: number
  errors: number
  pending: number
}

type Coverage = {
  lists: ListCoverage[]
  offlineOnly: boolean
  cooldownUntil: number
  cooldownReason: string | null
  lastRun: {
    startedAt: number
    finishedAt: number | null
    status: string
    attempted: number
    html: number
    audio: number
    errors: number
    message: string | null
  } | null
}

function date(seconds: number) {
  return new Date(seconds * 1000).toLocaleString()
}

export function OfflineDownloads() {
  const [coverage, setCoverage] = useState<Coverage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    let inFlight = false
    async function refresh() {
      if (inFlight) return
      inFlight = true
      setLoading(true)
      try {
        const next = await api.get<Coverage>('/backend/offline-coverage')
        if (active) { setCoverage(next); setError(null) }
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : 'Could not read offline coverage')
      } finally {
        inFlight = false
        if (active) setLoading(false)
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 60_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [refreshKey])

  const run = coverage?.lastRun
  return <section className="panel offline-panel" aria-label="Offline downloads">
    <div className="panel__heading">
      <div><p className="eyebrow">LOCAL DICTIONARY CACHE</p><h2>Offline downloads</h2>
        <p>Lists in <code>words_to_add/</code>, including book subfolders. Shared words download once.</p></div>
      <button className="tiny-button" type="button" disabled={loading} onClick={() => setRefreshKey((key) => key + 1)}>{loading ? 'Reading…' : 'Refresh coverage'}</button>
    </div>
    {error ? <div className="inline-error">{error}</div> : null}
    {coverage ? <>
      <p className="muted">{coverage.offlineOnly ? 'Offline-only mode' : 'Cache-first mode'} · Ready = exact meanings + MP3. Percentages use unique words; this view never downloads resources.</p>
      {coverage.cooldownUntil > Date.now() / 1000 ? <div className="notice notice--error">{coverage.cooldownReason} · Retry after {date(coverage.cooldownUntil)}</div> : null}
      {coverage.lists.length ? <div className="offline-table-wrap"><table className="offline-table">
        <thead><tr><th scope="col">List</th><th scope="col">HTML</th><th scope="col">MP3</th><th scope="col">Offline ready</th></tr></thead>
        <tbody>{coverage.lists.map((list) => <tr key={list.name}>
          <th scope="row"><strong>{list.name}</strong><small>{list.total} unique words · {list.entries} entries</small>
            {list.error ? <small className="offline-error">{list.error}</small> : <small>{list.pending} pending · {list.noExactMatch} without exact match · {list.noAudio} without recording · {list.errors} temporary failures{list.invalid ? ` · ${list.invalid} invalid entries` : ''}</small>}</th>
          <td>{list.html} / {list.total}</td><td>{list.audio} / {list.total}</td>
          <td><strong>{list.percent}%</strong><progress aria-label={`${list.name} offline ready`} value={list.ready} max={list.total || 1} /><small>{list.ready} / {list.total}</small></td>
        </tr>)}</tbody>
      </table></div> : <p className="muted">No .txt lists found in the configured words folder.</p>}
      <div className="offline-run" role="status">{run ? <>
        <strong>Last batch: {run.status.replaceAll('_', ' ')}</strong> · {date(run.finishedAt ?? run.startedAt)}
        <span>{run.attempted} words attempted · {run.html} HTML + {run.audio} MP3 downloaded · {run.errors} failures</span>
        {run.message ? <span>{run.message}</span> : null}
      </> : 'No background batch recorded yet. Run the prefetch command or enable the launchd agent.'}</div>
    </> : !error ? <p className="muted">Reading local cache…</p> : null}
  </section>
}
