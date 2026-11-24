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
  listsAvailable: boolean
  loading: boolean
  progress: ScanProgress | null
  coverageError: string | null
  existingNotes: ExistingNotes | null
  remotePreparation?: {
    submissionError?: string | null
    drainError?: string | null
  }
  lists: ListCoverage[]
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

type HtmlCategory = { key: string; label: string; count: number; percent: number }
type ScanProgress = { stage: string; processed: number; total: number | null }
type ReviewNote = { noteId: number; word: string | null; model: string; category: string; reason: string }
type IndexIssue = { noteId: number; word: string; reason: string; indexedNoteId?: number; indexedWord?: string }
type ExistingNotes = {
  available: boolean
  loading: boolean
  progress: ScanProgress | null
  legacy?: boolean
  snapshotAt?: string
  profile?: string
  total?: number
  entries?: number
  percent?: number
  categories?: HtmlCategory[]
  review?: ReviewNote[]
  reconciliation: string
  reconciliationError: string | null
  cacheError: string | null
  reconciledAt: string | null
  indexIssues: IndexIssue[]
  indexError: string | null
  changes: { added: number; changed: number; removed: number } | null
}

function date(seconds: number) {
  return new Date(seconds * 1000).toLocaleString()
}

function LoadingProgress({ progress, fallback }: { progress?: ScanProgress | null; fallback: string }) {
  const stage = progress?.stage ?? fallback
  const total = progress?.total
  const processed = progress?.processed ?? 0
  const measured = total !== null && total !== undefined
  const percent = measured ? (total ? Math.round(100 * processed / total) : 100) : null
  return <div className="coverage-loading" role="status">
    <div><strong>{stage}</strong>{measured ? <span>{processed} / {total} processed · {Math.max(0, total - processed)} remaining · {percent}%</span> : <span>Determining work remaining…</span>}</div>
    <progress aria-label={stage} value={measured ? (total ? processed : 1) : undefined} max={measured ? (total || 1) : undefined} />
  </div>
}

function ExistingNoteStats({ stats }: { stats: ExistingNotes | null }) {
  const [filter, setFilter] = useState('needs_review')
  const categories = stats?.categories ?? []
  const review = stats?.review ?? []
  const needsReview = review.filter((note) => note.category !== 'missing')
  const visible = filter === 'needs_review' ? needsReview : review.filter((note) => filter === 'all' || note.category === filter)
  const labels = new Map(categories.map((category) => [category.key, category.label]))
  const indexIssues = stats?.indexIssues ?? []

  return <div className="existing-coverage" aria-labelledby="existing-coverage-title">
    <div className="existing-coverage__heading">
      <h3 id="existing-coverage-title">Existing Anki notes</h3>
      {stats?.available ? <strong className="existing-coverage__goal">{stats.percent}% entries <span>· {stats.entries} / {stats.total} notes</span></strong> : null}
    </div>
    {stats?.snapshotAt ? <p className="muted">{stats.profile ? `${stats.profile} · ` : ''}Snapshot: {new Date(stats.snapshotAt).toLocaleString()}</p> : null}
    {!stats || stats.loading ? <LoadingProgress progress={stats?.progress} fallback="Reading saved note coverage" /> : stats.reconciliation === 'checking' ? <LoadingProgress fallback="Checking the saved inventory against Anki" /> : null}
    {stats?.reconciliationError ? <p className="inline-error" role="status">Anki reconciliation: {stats.reconciliationError}{stats.available ? ' Showing the saved snapshot.' : ''}</p> : null}
    {stats?.cacheError ? <p className="inline-error" role="status">Local coverage: {stats.cacheError}</p> : null}
    {stats?.legacy ? <p className="muted">The older export contains words only. Note-based statistics will appear after a successful Anki reconciliation.</p> : null}
    {stats?.reconciliation === 'complete' ? <p className="muted" role="status">Checked against Anki{stats.reconciledAt ? `: ${new Date(stats.reconciledAt).toLocaleString()}` : ''}{stats.changes ? ` · ${stats.changes.added} added · ${stats.changes.changed} changed · ${stats.changes.removed} removed` : ''}</p> : null}
    {stats?.available ? <>
      <div className="html-coverage-bar" role="img" aria-label={`Existing Anki note HTML coverage: ${categories.map((category) => `${category.label}: ${category.percent}%, ${category.count} notes`).join('; ')}`}>
        {categories.filter((category) => category.count > 0).map((category) => <span key={category.key} className={`html-category--${category.key}`} style={{ width: `${100 * category.count / (stats.total || 1)}%` }} title={`${category.label}: ${category.percent}% (${category.count})`} />)}
      </div>
      <ul className="html-coverage-legend" aria-label="HTML categories">
        {categories.map((category) => <li key={category.key}><span className={`html-coverage-swatch html-category--${category.key}`} aria-hidden="true" /><span>{category.label}{category.key === 'entries' ? ' — goal met' : ''}</span><strong>{category.percent}%</strong><small>{category.count}</small></li>)}
      </ul>
      {stats.total === 0 ? <p className="muted">No notes in the normal vocabulary note types.</p> : <>
        <div className="existing-coverage__review-heading">
          <h4>{filter === 'missing' ? 'Missing downloads' : filter === 'all' ? 'Notes outside entries' : 'Needs manual review'} <span>({visible.length})</span></h4>
          <label>Category <select value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="needs_review">Needs review ({needsReview.length})</option>
            <option value="all">All outside entries ({review.length})</option>
            {categories.filter((category) => category.key !== 'entries').map((category) => <option key={category.key} value={category.key}>{category.label} ({category.count})</option>)}
          </select></label>
        </div>
        {visible.length ? <div className="offline-table-wrap existing-coverage__notes"><table className="offline-table">
          <thead><tr><th scope="col">English / Anki note</th><th scope="col">HTML category</th><th scope="col">Reason</th></tr></thead>
          <tbody>{visible.map((note) => <tr key={note.noteId}>
            <th scope="row"><strong>{note.word || '(empty English field)'}</strong><small>Note {note.noteId} · {note.model}</small></th>
            <td>{labels.get(note.category) ?? note.category}</td><td>{note.reason}</td>
          </tr>)}</tbody>
        </table></div> : <p className="muted">{filter === 'needs_review' ? 'No downloaded notes need review.' : review.length ? 'No notes in this category.' : 'All notes have HTML classified as entries.'}</p>}
      </>}
    </> : stats?.reconciliation === 'error' && !stats.legacy ? <p className="muted">No saved note inventory is available yet.</p> : null}
    {stats?.indexError ? <p className="inline-error">Local-index comparison: {stats.indexError}</p> : null}
    {stats?.reconciliation === 'complete' ? <details className="existing-coverage__index">
      <summary>Local note index · {stats.indexError ? 'comparison unavailable' : `${indexIssues.length} discrepancies`}</summary>
      {indexIssues.length ? <div className="offline-table-wrap existing-coverage__notes"><table className="offline-table">
        <thead><tr><th scope="col">English / Anki note</th><th scope="col">Discrepancy</th></tr></thead>
        <tbody>{indexIssues.map((issue, index) => <tr key={`${issue.noteId}-${index}`}><th scope="row">{issue.word}<small>Note {issue.noteId}</small></th><td>{issue.reason}{issue.indexedNoteId ? ` (indexed note: ${issue.indexedNoteId})` : ''}{issue.indexedWord ? ` (indexed English: ${issue.indexedWord})` : ''}</td></tr>)}</tbody>
      </table></div> : <p className="muted">{stats.indexError ? 'Comparison could not be completed.' : 'The local note index matches this inventory.'}</p>}
    </details> : null}
  </div>
}

export function OfflineDownloads() {
  const [coverage, setCoverage] = useState<Coverage | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    let inFlight = false
    let timer: number | undefined
    async function refresh() {
      if (inFlight) return
      inFlight = true
      let delay = 60_000
      try {
        const next = await api.get<Coverage>('/backend/offline-coverage')
        if (active) { setCoverage(next); setError(null) }
        if (next.loading || next.existingNotes?.loading || !next.existingNotes || ['starting', 'checking'].includes(next.existingNotes.reconciliation)) delay = 1_000
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : 'Could not read offline coverage')
      } finally {
        inFlight = false
        if (active) timer = window.setTimeout(() => void refresh(), delay)
      }
    }
    void refresh()
    return () => { active = false; window.clearTimeout(timer) }
  }, [])

  const run = coverage?.lastRun
  return <section className="panel offline-panel" aria-label="Offline downloads">
    <div className="panel__heading">
      <div><p className="eyebrow">LOCAL DICTIONARY CACHE</p><h2>Offline downloads</h2></div>
    </div>
    {error ? <div className="inline-error">{error}</div> : null}
    {!error && (!coverage || coverage.loading) ? <LoadingProgress progress={coverage?.progress} fallback="Reading local cache" /> : null}
    {coverage?.coverageError ? <p className="inline-error">Local cache scan: {coverage.coverageError}</p> : null}
    {coverage ? <>
      <ExistingNoteStats stats={coverage.existingNotes} />
      {coverage.remotePreparation?.submissionError ? <p className="inline-error">Remote submission: {coverage.remotePreparation.submissionError}</p> : null}
      {coverage.remotePreparation?.drainError ? <p className="inline-error">Remote import: {coverage.remotePreparation.drainError}</p> : null}
      {coverage.cooldownUntil > Date.now() / 1000 ? <div className="notice notice--error">{coverage.cooldownReason} · Retry after {date(coverage.cooldownUntil)}</div> : null}
      {coverage.listsAvailable ? <><h3>Pending vocabulary lists</h3>
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
      </> : 'No background batch recorded yet. Run the prefetch command or enable the launchd agent.'}</div></> : null}
    </> : null}
  </section>
}
