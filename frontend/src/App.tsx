import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { ApiError, api } from './api'
import { OfflineDownloads } from './OfflineDownloads'
import type {
  Draft,
  DeckContext,
  DeckNode,
  ExistingNote,
  FieldMapping,
  Inventory,
  LookupResult,
  ModelSchema,
  Preview,
  ReviewFilter,
  ReviewItem,
  ReviewSnapshot,
  Session,
  SessionSummary,
  Status,
  Translation,
} from './types'

const FACTORY_TAGS = ['IMAGE', 'ERROR', 'GEMINI_DIFF', 'TO_EDIT']
const FLAG_NAMES = ['None', 'Red', 'Orange', 'Green', 'Blue', 'Pink', 'Turquoise', 'Purple']

type Message = { tone: 'error' | 'success'; text: string } | null
type WorkspaceConfig = { deckName: string; modelName: string; fieldMapping: FieldMapping }

function targetConfigured(config: WorkspaceConfig) {
  return Boolean(config.deckName && config.modelName && config.fieldMapping.englishField && config.fieldMapping.translationField)
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong while talking to the local backend.'
}

function formatDate(value?: string | null) {
  if (!value) return 'No activity recorded'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function stripHtml(value: string) {
  const element = document.createElement('div')
  element.innerHTML = value.replace(/<br\s*\/?\s*>/gi, '\n')
  return (element.textContent ?? '').replace(/\u00a0/g, ' ').trim()
}

function splitTranslationLine(value: string) {
  const translations: string[] = []
  let start = 0
  let parentheses = 0
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === '(') parentheses += 1
    if (value[index] === ')' && parentheses > 0) parentheses -= 1
    if (value[index] === ',' && parentheses === 0) {
      translations.push(value.slice(start, index).trim())
      start = index + 1
    }
  }
  translations.push(value.slice(start).trim())
  return translations.filter(Boolean)
}

function groupsFromExistingValue(value: string): Translation[][] {
  const text = stripHtml(value)
  if (!text) return []
  return text
    .split(/\n+/)
    .map(splitTranslationLine)
    .filter((group) => group.length > 0)
    .map((group) => [
      ...group.map((value) => ({ original: value, value, selected: true })),
      { original: '<br>', value: '<br>', selected: false, isBreak: true },
    ])
}

function defaultFieldMapping(fields: string[], existing: FieldMapping = {}) {
  const matches = (pattern: RegExp, fallback: string) => fields.find((field) => pattern.test(field)) ?? fallback
  const englishField = fields.includes(existing.englishField ?? '')
    ? existing.englishField
    : matches(/(^|[_\s-])(en|english|word|front)($|[_\s-])/i, fields[0] ?? '')
  const translationField = fields.includes(existing.translationField ?? '')
    ? existing.translationField
    : matches(/(^|[_\s-])(pl|polish|translation|meaning|back)($|[_\s-])/i, fields.find((field) => field !== englishField) ?? '')
  const audioField = fields.includes(existing.audioField ?? '')
    ? existing.audioField
    : fields.find((field) => /audio|sound/i.test(field)) ?? ''
  return {
    englishField,
    translationField,
    audioField,
    additionalFields: existing.additionalFields ?? {},
  }
}

function selectedGroups(draft: Draft | null) {
  return (draft?.groups ?? [])
    .map((group) => group.filter((translation) => translation.selected && translation.value.trim()).map((translation) => translation.value.trim()))
    .filter((group) => group.length > 0)
}

function inlineMarkdown(value: string): ReactNode[] {
  return value.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>
    if (part.startsWith('*') && part.endsWith('*')) return <em key={index}>{part.slice(1, -1)}</em>
    return part
  })
}

function MarkdownAnswer({ value }: { value: string }) {
  const lines = value.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index].trim()
    if (!line) {
      index += 1
      continue
    }
    if (line.startsWith('```')) {
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      blocks.push(<pre key={`code-${index}`}><code>{codeLines.join('\n')}</code></pre>)
      index += 1
      continue
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    if (heading) {
      const content = inlineMarkdown(heading[2])
      blocks.push(heading[1].length === 1 ? <h3 key={`heading-${index}`}>{content}</h3> : <h4 key={`heading-${index}`}>{content}</h4>)
      index += 1
      continue
    }
    if (/^[-*+]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
      const ordered = /^\d+\.\s+/.test(line)
      const items: ReactNode[] = []
      while (index < lines.length) {
        const item = lines[index].trim()
        const match = ordered ? item.match(/^\d+\.\s+(.+)$/) : item.match(/^[-*+]\s+(.+)$/)
        if (!match) break
        items.push(<li key={`item-${index}`}>{inlineMarkdown(match[1])}</li>)
        index += 1
      }
      blocks.push(ordered ? <ol key={`list-${index}`}>{items}</ol> : <ul key={`list-${index}`}>{items}</ul>)
      continue
    }
    const paragraph: string[] = [line]
    index += 1
    while (index < lines.length && lines[index].trim() && !/^(#{1,3})\s+|^[-*+]\s+|^\d+\.\s+|^```/.test(lines[index].trim())) {
      paragraph.push(lines[index].trim())
      index += 1
    }
    blocks.push(<p key={`paragraph-${index}`}>{inlineMarkdown(paragraph.join(' '))}</p>)
  }

  return <>{blocks}</>
}

function StatusPill({ active, label }: { active: boolean; label: string }) {
  return <span className={`status-pill ${active ? 'status-pill--ready' : 'status-pill--quiet'}`}>{active ? 'Online' : 'Offline'}: {label}</span>
}

function Notice({ message }: { message: Message }) {
  if (!message) return null
  return <div className={`notice notice--${message.tone}`} role="status">{message.text}</div>
}

export default function App() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [activeReview, setActiveReview] = useState<ReviewSnapshot | null>(null)
  const [status, setStatus] = useState<Status | null>(null)
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [decks, setDecks] = useState<string[]>([])
  const [inventory, setInventory] = useState<Inventory>({ tags: [], flags: [] })
  const [reviewDeck, setReviewDeck] = useState('')
  const [homeLoading, setHomeLoading] = useState(true)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [message, setMessage] = useState<Message>(null)
  const [inventoryError, setInventoryError] = useState<string | null>(null)
  const [stoppingApp, setStoppingApp] = useState(false)

  useEffect(() => {
    void refreshHome()
  }, [])

  useEffect(() => {
    void refreshInventory(reviewDeck)
  }, [reviewDeck, status?.ankiAvailable])

  useEffect(() => {
    if (!message) return
    const timeout = window.setTimeout(() => setMessage(null), 10_000)
    return () => window.clearTimeout(timeout)
  }, [message])

  async function refreshHome() {
    setHomeLoading(true)
    const [statusResult, sessionsResult] = await Promise.allSettled([
      api.get<Status>('/backend/status'),
      api.get<SessionSummary[]>('/backend/sessions'),
    ])

    if (statusResult.status === 'fulfilled') setStatus(statusResult.value)
    if (sessionsResult.status === 'fulfilled') setSessions(sessionsResult.value)
    if (statusResult.status === 'fulfilled' && statusResult.value.ankiAvailable) {
      try {
        setDecks(await api.get<string[]>('/backend/decks'))
      } catch (error) {
        setMessage({ tone: 'error', text: errorMessage(error) })
      }
    } else {
      setDecks([])
    }

    const failed = [statusResult, sessionsResult].find((result) => result.status === 'rejected')
    if (failed?.status === 'rejected') setMessage({ tone: 'error', text: errorMessage(failed.reason) })
    setHomeLoading(false)
  }

  async function refreshInventory(deckName: string) {
    if (!status?.ankiAvailable) {
      setInventoryError(null)
      setInventory({ tags: [], flags: [] })
      return
    }
    try {
      setInventoryError(null)
      setInventory(await api.get<Inventory>(`/backend/review/inventory${deckName ? `?deckName=${encodeURIComponent(deckName)}` : ''}`))
    } catch (error) {
      setInventoryError(errorMessage(error))
      setInventory({ tags: [], flags: [] })
    }
  }

  async function stopApp() {
    if (!window.confirm('Sync pending Anki changes and stop the local app server?')) return
    setStoppingApp(true)
    try {
      const result = await api.post<{ synced: boolean; syncPending: boolean; syncWarning?: string }>('/backend/shutdown', undefined, {
        headers: { 'X-Anki-Factory-Shutdown': 'true' },
      })
      setMessage({
        tone: result.syncWarning ? 'error' : 'success',
        text: result.syncWarning
          ? `The server is stopping, but Anki sync failed: ${result.syncWarning}`
          : result.synced ? 'Anki synced. The local server is stopping; you can close this tab.' : 'The local server is stopping; there were no pending Anki changes.',
      })
    } catch (error) {
      setMessage({ tone: 'error', text: errorMessage(error) })
      setStoppingApp(false)
    }
  }

  async function startReview(kind: 'tag' | 'flag', value: string | number) {
    setReviewLoading(true)
    try {
      const snapshot = await api.post<ReviewSnapshot>('/backend/review/snapshot', {
        kind,
        value,
        deckName: reviewDeck || undefined,
      })
      setActiveReview(snapshot)
    } catch (error) {
      setMessage({ tone: 'error', text: errorMessage(error) })
    } finally {
      setReviewLoading(false)
    }
  }

  if (activeSessionId) {
    return (
      <Workspace
        sessionId={activeSessionId}
        onExit={() => {
          setActiveSessionId(null)
          setMessage(null)
          void refreshHome()
        }}
      />
    )
  }

  if (activeReview) {
    return (
      <Workspace
        review={activeReview}
        onExit={() => {
          setActiveReview(null)
          setMessage(null)
          void refreshInventory(reviewDeck)
        }}
      />
    )
  }

  const sources = sessions.filter((session) => session.mode === 'add')
  return (
    <main className="app-shell">
      <header className="topbar topbar--home">
        <div className="brand"><span className="brand__mark">AF</span><span>Anki Flashcards Factory</span></div>
          <div className="topbar__status">
            <StatusPill active={Boolean(status?.ankiAvailable)} label={status?.ankiAvailable ? 'Anki' : 'Open Anki'} />
            <StatusPill active={Boolean(status?.geminiConfigured)} label="Gemini" />
            <button className="tiny-button" type="button" onClick={() => void stopApp()} disabled={stoppingApp}>{stoppingApp ? 'Stopping...' : 'Sync & stop'}</button>
          </div>
      </header>

      <section className="hero">
        <p className="eyebrow">LOCAL CARD WORKBENCH</p>
        <h1>Make the next card<br /><em>the useful one.</em></h1>
        <p className="hero__lede">A focused queue for Diki selections, careful Anki updates, and the small decisions that make a card worth reviewing.</p>
      </section>

      <Notice message={message} />
      {status && !status.ankiAvailable ? <div className="inline-error service-notice">{status.ankiError ?? 'Open Anki with AnkiConnect enabled, then refresh this page.'}</div> : null}

      <section className="source-home" aria-label="Vocabulary source files">
        <article className="panel panel--continue">
          <div className="panel__heading">
            <div><p className="eyebrow">01 / WORD FILES</p><h2>Choose a vocabulary source</h2><p>The file is the queue. Maintain words in the text files or capture them through the CLI.</p></div>
            <button className="icon-button" type="button" title="Refresh source files" onClick={() => void refreshHome()} disabled={homeLoading}>Refresh</button>
          </div>
          {homeLoading ? <LoadingMark label="Reading source files" /> : sources.length ? (
            <div className="session-list">
              {sources.map((session) => (
                <div className="session-row session-row--add" key={session.id}>
                  <button className="session-row__main" type="button" disabled={Boolean(session.sourceError) || !session.remainingCount} onClick={() => setActiveSessionId(session.id)}><strong>{session.name}</strong><small>{session.sourceError ?? `Live file${session.deckName ? ` / ${session.deckName}` : ''}`}</small></button>
                  <span className="session-row__meta"><b>{session.remainingCount}</b><small>left</small></span>
                  <span className="session-row__date">{formatDate(session.updatedAt)}</span>
                  <button className="session-row__arrow" type="button" disabled={Boolean(session.sourceError) || !session.remainingCount} onClick={() => setActiveSessionId(session.id)}>{session.remainingCount ? 'Open' : 'Empty'}</button>
                </div>
              ))}
            </div>
          ) : <EmptyState title="No source files found" text="Keep the main vocabulary and book .txt files in words_to_add/. Refresh after adding a file." />}
        </article>
      </section>

      <OfflineDownloads />

      <section className="panel review-panel">
        <div className="panel__heading review-panel__heading">
          <div><p className="eyebrow">02 / REPAIR</p><h2>Review tags and flags</h2><p>A live, one-off snapshot of current Anki metadata &mdash; nothing is saved here. Tags belong to notes; flags belong to individual cards.</p></div>
          <label className="compact-select">Deck scope<select value={reviewDeck} onChange={(event) => setReviewDeck(event.target.value)}><option value="">All decks</option>{decks.map((deck) => <option key={deck} value={deck}>{deck}</option>)}</select></label>
        </div>
        {inventoryError ? <div className="inline-error">{inventoryError}</div> : null}
        <div className="inventory-grid">
          <div className="inventory-section"><h3>Tags</h3>{inventory.tags.length ? <div className="inventory-list">{inventory.tags.map((tag) => <button className="inventory-item inventory-item--tag" type="button" disabled={reviewLoading} key={String(tag.value)} onClick={() => void startReview('tag', String(tag.value))}><span>{String(tag.value)}</span><b>{tag.count}</b></button>)}</div> : <p className="muted">No matching tags found.</p>}</div>
          <div className="inventory-section"><h3>Card flags</h3>{inventory.flags.length ? <div className="inventory-list">{inventory.flags.map((flag) => <button className={`inventory-item inventory-item--flag flag-${flag.value}`} type="button" disabled={reviewLoading} key={String(flag.value)} onClick={() => void startReview('flag', Number(flag.value))}><span>{FLAG_NAMES[Number(flag.value)] ?? `Flag ${flag.value}`}</span><b>{flag.count}</b></button>)}</div> : <p className="muted">No flagged cards in this scope.</p>}</div>
        </div>
      </section>
    </main>
  )
}

function TargetSetup({
  sessionId,
  initialConfig,
  models,
  error,
  onExit,
  onConfigured,
}: {
  sessionId: string
  initialConfig: WorkspaceConfig
  models: string[]
  error: string | null
  onExit: () => void
  onConfigured: (config: WorkspaceConfig) => Promise<void>
}) {
  const [tree, setTree] = useState<DeckNode[]>([])
  const [availableModels, setAvailableModels] = useState(models)
  const [config, setConfig] = useState<WorkspaceConfig>(initialConfig)
  const [context, setContext] = useState<DeckContext | null>(null)
  const [contextLoading, setContextLoading] = useState(false)
  const [schema, setSchema] = useState<ModelSchema | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [setupError, setSetupError] = useState<string | null>(error)
  const contextRequest = useRef(0)

  useEffect(() => {
    void loadTargetData()
  }, [sessionId])

  async function loadTargetData() {
    setLoading(true)
    try {
      const [deckTree, noteTypes] = await Promise.all([
        api.get<DeckNode[]>('/backend/deck-tree'),
        api.get<string[]>('/backend/models'),
      ])
      setTree(deckTree)
      setAvailableModels(noteTypes)
      if (initialConfig.deckName && !config.deckName) await chooseDeck(initialConfig.deckName)
      if (initialConfig.modelName && !config.modelName) await chooseModel(initialConfig.modelName)
    } catch (requestError) {
      setSetupError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  async function chooseDeck(deckName: string) {
    const requestId = ++contextRequest.current
    setSetupError(null)
    setContext(null)
    setSchema(null)
    const nextConfig = { deckName, modelName: '', fieldMapping: {} }
    setConfig(nextConfig)
    if (!deckName) {
      setContextLoading(false)
      return
    }
    setContextLoading(true)
    try {
      const nextContext = await api.post<DeckContext>('/backend/deck-context', { deckName })
      if (requestId === contextRequest.current) setContext(nextContext)
    } catch (requestError) {
      if (requestId === contextRequest.current) setSetupError(errorMessage(requestError))
    } finally {
      if (requestId === contextRequest.current) setContextLoading(false)
    }
  }

  async function chooseModel(modelName: string) {
    setSchema(null)
    const nextConfig = { ...config, modelName }
    setConfig(nextConfig)
    if (!modelName) return
    try {
      const nextSchema = await api.post<ModelSchema>('/backend/model-schema', { modelName })
      setSchema(nextSchema)
      setConfig((current) => ({
        ...current,
        modelName,
        fieldMapping: defaultFieldMapping(nextSchema.fields, current.fieldMapping),
      }))
    } catch (requestError) {
      setSetupError(errorMessage(requestError))
    }
  }

  function changeMapping(update: Partial<FieldMapping>) {
    setConfig((current) => ({ ...current, fieldMapping: { ...current.fieldMapping, ...update } }))
  }

  async function saveTarget() {
    if (!targetConfigured(config)) {
      setSetupError('Choose a deck, note type, English field, and translation field to start this queue.')
      return
    }
    setSaving(true)
    setSetupError(null)
    try {
      await onConfigured(config)
    } catch (requestError) {
      setSetupError(errorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  const deckModels = context?.models ?? []
  const selectableModels = [...deckModels, ...availableModels.filter((model) => !deckModels.includes(model))]

  return <main className="target-setup-shell">
    <header className="topbar workspace-topbar">
      <div className="brand"><span className="brand__mark">AF</span><span>Anki Flashcards Factory</span></div>
      <div className="queue-meter"><span>QUEUE TARGET</span><strong>Before <small>first word</small></strong></div>
      <button className="button button--secondary" type="button" onClick={onExit}>Exit to home</button>
    </header>
    <section className="target-intro"><p className="eyebrow">BATCH DESTINATION</p><h1>Choose where this queue belongs.</h1><p>This target applies to every new card in the queue. A one-card override remains available immediately before creating an individual note.</p><button className="text-button" type="button" onClick={() => void loadTargetData()} disabled={loading}>Refresh Anki decks and note types</button></section>
    {setupError ? <div className="notice notice--error">{setupError}</div> : null}
    {loading ? <LoadingMark label="Reading Anki decks and note types" /> : <div className="target-setup-grid">
      <section className="panel target-tree-panel"><div className="panel__heading"><div><p className="eyebrow">01 / DECK</p><h2>Deck tree</h2></div><span className="counter-badge">{tree.length} roots</span></div><p className="muted">Select the destination deck for this queue.</p><div className="deck-tree">{tree.length ? tree.map((node) => <DeckTreeBranch key={node.fullName} node={node} selected={config.deckName} onSelect={(deckName) => void chooseDeck(deckName)} />) : <EmptyState title="No decks found" text="Open Anki and create or sync a deck, then return here." />}</div></section>
      <section className="panel target-model-panel"><div className="panel__heading"><div><p className="eyebrow">02 / NOTE TYPE</p><h2>Model in this deck</h2></div></div>{config.deckName ? <><div className="selected-target-line"><span>Selected deck</span><strong>{config.deckName}</strong></div>{contextLoading ? <LoadingMark label="Reading note types in this deck" /> : context?.modelCounts.length ? <div className="model-histogram">{context.modelCounts.map((item) => <button type="button" className={`model-bar ${config.modelName === item.name ? 'model-bar--selected' : ''}`} key={item.name} onClick={() => void chooseModel(item.name)}><span>{item.name}</span><b style={{ '--model-count': item.count } as CSSProperties}>{item.count}</b></button>)}</div> : <p className="muted">This deck has no cards yet. Choose any note type below.</p>}<label className="field-label">Note type for this queue</label><select className="select-input" disabled={contextLoading} value={config.modelName} onChange={(event) => void chooseModel(event.target.value)}><option value="">Choose a note type</option>{selectableModels.map((model) => <option key={model} value={model}>{model}{deckModels.includes(model) ? ' (used in deck)' : ''}</option>)}</select></> : <EmptyState title="Select a deck first" text="The histogram shows note types already used by the selected deck." />}</section>
      <section className="panel target-mapping-panel"><div className="panel__heading"><div><p className="eyebrow">03 / FIELD MAPPING</p><h2>Card factory fields</h2></div></div>{schema ? <div className="mapping-block mapping-block--target"><label className="mapping-row">English word<select value={config.fieldMapping.englishField ?? ''} onChange={(event) => changeMapping({ englishField: event.target.value })}><option value="">Select field</option>{schema.fields.map((field) => <option key={field} value={field}>{field}</option>)}</select></label><label className="mapping-row">Polish translation<select value={config.fieldMapping.translationField ?? ''} onChange={(event) => changeMapping({ translationField: event.target.value })}><option value="">Select field</option>{schema.fields.map((field) => <option key={field} value={field}>{field}</option>)}</select></label><label className="mapping-row">Audio <span>optional</span><select value={config.fieldMapping.audioField ?? ''} onChange={(event) => changeMapping({ audioField: event.target.value })}><option value="">No audio field</option>{schema.fields.map((field) => <option key={field} value={field}>{field}</option>)}</select></label><button className="button button--primary target-start-button" type="button" disabled={saving || !targetConfigured(config)} onClick={() => void saveTarget()}>{saving ? 'Saving target...' : 'Start this queue'}</button></div> : <EmptyState title="Choose a note type" text="Its Anki fields will be loaded here before any word is processed." />}</section>
    </div>}
  </main>
}

function DeckTreeBranch({ node, selected, onSelect }: { node: DeckNode; selected: string; onSelect: (deckName: string) => void }) {
  return <div className="deck-tree__branch"><button type="button" className={`deck-tree__item ${selected === node.fullName ? 'deck-tree__item--selected' : ''}`} onClick={() => onSelect(node.fullName)}><span>{node.name}</span><small>{node.fullName === node.name ? 'root' : node.fullName}</small></button>{node.children.length ? <div className="deck-tree__children">{node.children.map((child) => <DeckTreeBranch key={child.fullName} node={child} selected={selected} onSelect={onSelect} />)}</div> : null}</div>
}

function CustomCardForm({
  sessionId,
  entryId,
  currentWord,
  initialDeckName,
  initialModelName,
  decks,
  models,
  onClose,
  onComplete,
}: {
  sessionId: string
  entryId: string
  currentWord: string
  initialDeckName: string
  initialModelName: string
  decks: string[]
  models: string[]
  onClose: () => void
  onComplete: (result: { action: string; noteId: number; session: Session; syncWarning?: string; cleanupWarning?: string }) => Promise<void>
}) {
  const [deckName, setDeckName] = useState(initialDeckName)
  const [modelName, setModelName] = useState(initialModelName)
  const [schema, setSchema] = useState<ModelSchema | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (initialModelName) void loadSchema(initialModelName)
  }, [])

  async function loadSchema(nextModelName: string) {
    setModelName(nextModelName)
    setSchema(null)
    setFields({})
    if (!nextModelName) return
    try {
      const nextSchema = await api.post<ModelSchema>('/backend/model-schema', { modelName: nextModelName })
      const wordField = nextSchema.fields.find((field) => /(^|[_\s-])(en|english|word|front)($|[_\s-])/i.test(field)) ?? nextSchema.fields[0]
      setSchema(nextSchema)
      setFields(Object.fromEntries(nextSchema.fields.map((field) => [field, field === wordField ? currentWord : ''])))
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  async function saveCustomCard() {
    if (!deckName || !modelName || !schema) {
      setError('Choose a deck and note type before saving.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const result = await api.post<{ action: string; noteId: number; session: Session; syncWarning?: string; cleanupWarning?: string }>(
        `/backend/sessions/${sessionId}/current/custom-card`,
        { deckName, modelName, fields, entryId },
      )
      await onComplete(result)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  return <div className="custom-card-backdrop" role="dialog" aria-modal="true" aria-label="Create custom card">
    <section className="custom-card-form">
      <div className="panel__heading"><div><p className="eyebrow">CUSTOM CARD</p><h2>Build this note manually</h2><p>Queue word: <b>{currentWord}</b></p></div><button className="tiny-button" type="button" onClick={onClose}>Close</button></div>
      {error ? <div className="inline-error">{error}</div> : null}
      <div className="custom-card-target"><label className="field-label">Deck</label><select className="select-input" value={deckName} onChange={(event) => setDeckName(event.target.value)}><option value="">Choose a deck</option>{decks.map((deck) => <option key={deck} value={deck}>{deck}</option>)}</select><label className="field-label">Note type</label><select className="select-input" value={modelName} onChange={(event) => void loadSchema(event.target.value)}><option value="">Choose a note type</option>{models.map((model) => <option key={model} value={model}>{model}</option>)}</select></div>
      {schema ? <div className="custom-card-fields">{schema.fields.map((field) => <label key={field}><span>{field}</span><textarea value={fields[field] ?? ''} onChange={(event) => setFields((current) => ({ ...current, [field]: event.target.value }))} placeholder={`Value for ${field}`} /></label>)}</div> : <EmptyState title="Choose a note type" text="Every field from that Anki model will appear here." />}
      <div className="custom-card-actions"><button className="button button--secondary" type="button" onClick={onClose} disabled={saving}>Cancel</button><button className="button button--primary" type="button" onClick={() => void saveCustomCard()} disabled={saving || !schema || !deckName || !modelName}>{saving ? 'Saving...' : 'Save custom card and continue'}</button></div>
    </section>
  </div>
}

function Workspace({ sessionId, review, onExit }: { sessionId?: string; review?: ReviewSnapshot; onExit: () => void }) {
  const isReview = Boolean(review)
  const [session, setSession] = useState<Session | null>(null)
  const [reviewItems, setReviewItems] = useState<ReviewItem[]>(review?.items ?? [])
  const [reviewCompleted, setReviewCompleted] = useState(0)
  const [config, setConfig] = useState<WorkspaceConfig>({ deckName: '', modelName: '', fieldMapping: {} })
  const [decks, setDecks] = useState<string[]>([])
  const [models, setModels] = useState<string[]>([])
  const [deckModels, setDeckModels] = useState<string[]>([])
  const [schema, setSchema] = useState<ModelSchema | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [lookup, setLookup] = useState<LookupResult | null>(null)
  const [existing, setExisting] = useState<ExistingNote | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [suggestionInput, setSuggestionInput] = useState('')
  const [customTag, setCustomTag] = useState('')
  const [removeTags, setRemoveTags] = useState<string[]>([])
  const [flag, setFlag] = useState<number | null>(null)
  const [queuedCardFlag, setQueuedCardFlag] = useState<number | null>(null)
  const [geminiText, setGeminiText] = useState('')
  const [geminiMode, setGeminiMode] = useState<'translate' | 'review' | null>(null)
  const [geminiLoading, setGeminiLoading] = useState(false)
  const [overrideOpen, setOverrideOpen] = useState(false)
  const [overrideModels, setOverrideModels] = useState<string[]>([])
  const [overrideSchema, setOverrideSchema] = useState<ModelSchema | null>(null)
  const [customCardOpen, setCustomCardOpen] = useState(false)
  const draftTimer = useRef<ReturnType<typeof window.setTimeout> | undefined>(undefined)
  const sourceEntry = useRef<string | undefined>(undefined)

  // Review-by-tag/flag walks an in-memory snapshot instead of a persisted session:
  // this rebuilds the same shape the rest of the workspace already expects.
  function nextReviewSession(remainingItems: ReviewItem[], completed: number): Session {
    const filter = review?.filter ?? { kind: 'tag' as const, value: '' }
    const current = remainingItems[0] ?? null
    return {
      id: 'review-local',
      mode: 'review',
      name: filter.kind === 'tag' ? `Review tag: ${filter.value}` : `Review flag: ${filter.value}`,
      source: 'anki-review',
      filter,
      deckName: null,
      modelName: null,
      fieldMapping: {},
      draft: {},
      completedCount: completed,
      createdAt: '',
      updatedAt: '',
      remainingCount: remainingItems.length,
      current: current ? { id: completed, position: completed, word: null, noteId: current.noteId, cardId: current.cardId } : null,
    }
  }

  useEffect(() => {
    void loadWorkspace()
    return () => {
      if (draftTimer.current) window.clearTimeout(draftTimer.current)
    }
  }, [sessionId])

  useEffect(() => {
    if (!notice) return
    const timeout = window.setTimeout(() => setNotice(null), 10_000)
    return () => window.clearTimeout(timeout)
  }, [notice])

  useEffect(() => {
    if (!error) return
    const timeout = window.setTimeout(() => setError(null), 10_000)
    return () => window.clearTimeout(timeout)
  }, [error])

  async function loadWorkspace() {
    if (draftTimer.current) window.clearTimeout(draftTimer.current)
    setLoading(true)
    setError(null)
    try {
      if (isReview) {
        const loaded = nextReviewSession(review?.items ?? [], 0)
        setSession(loaded)
        const nextConfig: WorkspaceConfig = { deckName: '', modelName: '', fieldMapping: {} }
        setConfig(nextConfig)
        await loadConfigurationOptions(nextConfig)
        await hydrateCurrent(loaded, nextConfig)
        return
      }
      const loaded = await api.get<Session>(`/backend/sessions/${sessionId}`)
      setSession(loaded)
      const nextConfig: WorkspaceConfig = {
        deckName: loaded.deckName ?? '',
        modelName: loaded.modelName ?? '',
        fieldMapping: loaded.fieldMapping ?? {},
      }
      setConfig(nextConfig)
      await loadConfigurationOptions(nextConfig)
      if (loaded.mode === 'add' && !targetConfigured(nextConfig)) return
      await hydrateCurrent(loaded, nextConfig)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  async function loadConfigurationOptions(currentConfig: WorkspaceConfig) {
    try {
      const appStatus = await api.get<Status>('/backend/status')
      if (!appStatus.ankiAvailable) {
        setError(appStatus.ankiError ?? 'Open Anki with AnkiConnect enabled before choosing a deck or note type.')
        return
      }
    } catch (requestError) {
      setError(errorMessage(requestError))
      return
    }
    const [deckResult, modelResult] = await Promise.allSettled([
      api.get<string[]>('/backend/decks'),
      api.get<string[]>('/backend/models'),
    ])
    if (deckResult.status === 'fulfilled') setDecks(deckResult.value)
    if (modelResult.status === 'fulfilled') setModels(modelResult.value)
    if (currentConfig.deckName) await loadDeckModels(currentConfig.deckName)
    if (currentConfig.modelName) await loadModelSchema(currentConfig.modelName)
  }

  async function loadDeckModels(deckName: string) {
    if (!deckName) {
      setDeckModels([])
      return
    }
    try {
      const context = await api.post<{ deckName: string; models: string[] }>('/backend/deck-context', { deckName })
      setDeckModels(context.models)
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  async function loadModelSchema(modelName: string) {
    if (!modelName) {
      setSchema(null)
      return null
    }
    try {
      const loadedSchema = await api.post<ModelSchema>('/backend/model-schema', { modelName })
      setSchema(loadedSchema)
      return loadedSchema
    } catch (requestError) {
      setError(errorMessage(requestError))
      return null
    }
  }

  async function hydrateCurrent(nextSession: Session, currentConfig: WorkspaceConfig) {
    sourceEntry.current = nextSession.mode === 'add' ? String(nextSession.current?.id ?? '') : undefined
    setDraft(null)
    setPreview(null)
    setExisting(null)
    setLookup(null)
    setGeminiText('')
    setGeminiMode(null)
    setCustomCardOpen(false)
    setRemoveTags(nextSession.mode === 'review' && nextSession.filter.kind === 'tag' && nextSession.filter.value === 'TO_EDIT' ? ['TO_EDIT'] : [])
    setQueuedCardFlag(null)
    setFlag(
      nextSession.mode === 'add' && typeof nextSession.draft?.flag === 'number'
        ? nextSession.draft.flag
        : nextSession.mode === 'review' && nextSession.filter.kind === 'flag' ? 0 : null,
    )
    if (!nextSession.current) {
      setDraft(null)
      return
    }

    if (nextSession.mode === 'add') {
      if (nextSession.draft?.word) {
        setDraft(nextSession.draft)
        setSuggestionInput(nextSession.draft.word)
        setLookup({
          word: nextSession.draft.word,
          exactMatch: Boolean(nextSession.draft.groups?.length),
          groups: nextSession.draft.groups ?? [],
          suggestions: [],
          existingNoteId: nextSession.draft.existingNoteId,
        })
        if (nextSession.draft.existingNoteId) await loadExistingNote(false)
        if (!nextSession.draft.resolvedWord || !nextSession.draft.groups?.length) await lookupCurrent(nextSession.draft.sourceWord ?? nextSession.draft.word)
      } else {
        await lookupCurrent()
      }
      return
    }

    try {
      const noteId = nextSession.current.noteId
      if (!noteId) throw new Error('This review item has no note to load.')
      const note = isReview
        ? await api.post<ExistingNote>('/backend/review/item/existing-note', { noteId })
        : await api.get<ExistingNote>(`/backend/sessions/${sessionId}/current/existing-note`)
      setExisting(note)
      if (nextSession.mode === 'review' && nextSession.filter.kind === 'flag') {
        const card = note.cards.find((item) => item.cardId === nextSession.current?.cardId)
        const currentFlag = card?.flags
        setQueuedCardFlag(typeof currentFlag === 'number' && currentFlag >= 0 && currentFlag <= 7 ? currentFlag : Number(nextSession.filter.value))
      }
      const fields = Object.keys(note.fields)
      const reviewConfig: WorkspaceConfig = {
        deckName: currentConfig.deckName || String(note.cards[0]?.deckName ?? ''),
        modelName: currentConfig.modelName || note.modelName,
        fieldMapping: defaultFieldMapping(fields, currentConfig.fieldMapping),
      }
      setConfig(reviewConfig)
      if (!isReview && (!currentConfig.modelName || !currentConfig.deckName || !currentConfig.fieldMapping.englishField)) {
        const saved = await api.patch<Session>(`/backend/sessions/${sessionId}`, {
          deckName: reviewConfig.deckName || undefined,
          modelName: reviewConfig.modelName || undefined,
          fieldMapping: reviewConfig.fieldMapping,
        })
        setSession(saved)
      }
      if (reviewConfig.modelName) await loadModelSchema(reviewConfig.modelName)
      const english = note.fields[reviewConfig.fieldMapping.englishField ?? ''] ?? Object.values(note.fields)[0] ?? ''
      const translation = note.fields[reviewConfig.fieldMapping.translationField ?? ''] ?? ''
      const reviewDraft: Draft = nextSession.draft?.word ? nextSession.draft : {
        sourceWord: stripHtml(english),
        word: stripHtml(english),
        groups: groupsFromExistingValue(translation),
        tags: note.tags,
        existingNoteId: note.noteId,
      }
      setDraft(reviewDraft)
      setSuggestionInput(reviewDraft.word ?? '')
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  async function lookupCurrent(word?: string) {
    const entryId = sourceEntry.current
    setError(null)
    setPreview(null)
    try {
      const result = isReview
        ? await api.post<LookupResult>('/backend/review/item/lookup', { word: word ?? draft?.word ?? '', fieldMapping: config.fieldMapping })
        : await api.post<LookupResult>(`/backend/sessions/${sessionId}/current/lookup`, { word, entryId })
      if (!isReview && entryId !== sourceEntry.current) return
      setLookup(result)
      setSuggestionInput(result.word)
      const nextDraft: Draft = {
        entryId: result.entryId,
        sourceWord: result.sourceWord ?? result.word,
        word: result.word,
        resolvedWord: result.resolvedWord,
        caseSensitive: result.caseSensitive,
        groups: result.groups,
        tags: session?.mode === 'review' ? draft?.tags ?? existing?.tags ?? [] : [],
        existingNoteId: result.existingNoteId,
      }
      setDraft(nextDraft)
      setExisting(null)
      if (result.existingNoteId) {
        const note = await loadExistingNote(false, result.existingNoteId)
        if (note && session?.mode === 'add') {
          const draftWithExistingTags = { ...nextDraft, tags: note.tags }
          setDraft(draftWithExistingTags)
          await persistDraft(draftWithExistingTags, false)
        }
      }
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  async function loadExistingNote(showFailure: boolean, noteIdOverride?: number | null) {
    const entryId = sourceEntry.current
    try {
      const note = isReview
        ? await api.post<ExistingNote>('/backend/review/item/existing-note', { noteId: noteIdOverride ?? draft?.existingNoteId ?? session?.current?.noteId })
        : await api.get<ExistingNote>(`/backend/sessions/${sessionId}/current/existing-note`)
      if (!isReview && entryId !== sourceEntry.current) return null
      setExisting(note)
      return note
    } catch (requestError) {
      if (showFailure) setError(errorMessage(requestError))
      return null
    }
  }

  async function persistDraft(value: Draft, updatePreview: boolean) {
    if (isReview) {
      // Nothing to persist for a stateless review item; the draft only lives in local state.
      setSession((current) => current ? { ...current, draft: value } : current)
    } else {
      const saved = await api.patch<Session>(`/backend/sessions/${sessionId}/current`, { draft: value, entryId: value.entryId })
      if (value.entryId !== sourceEntry.current) return
      setSession((current) => current ? { ...current, draft: value, updatedAt: saved.updatedAt } : current)
    }
    if (updatePreview) await requestPreview(false)
  }

  function scheduleDraft(nextDraft: Draft) {
    setDraft(nextDraft)
    if (draftTimer.current) window.clearTimeout(draftTimer.current)
    draftTimer.current = window.setTimeout(() => {
      void persistDraft(nextDraft, true).catch((requestError) => setError(errorMessage(requestError)))
    }, 550)
  }

  function updateTranslation(groupIndex: number, translationIndex: number, update: Partial<Translation>) {
    if (!draft) return
    const groups = (draft.groups ?? []).map((group, currentGroupIndex) => group.map((translation, currentTranslationIndex) => (
      currentGroupIndex === groupIndex && currentTranslationIndex === translationIndex ? { ...translation, ...update } : translation
    )))
    scheduleDraft({ ...draft, groups })
  }

  function editTranslationValue(groupIndex: number, translationIndex: number, value: string) {
    if (!draft) return
    const groups = (draft.groups ?? []).map((group, currentGroupIndex) => group.map((translation, currentTranslationIndex) => (
      currentGroupIndex === groupIndex && currentTranslationIndex === translationIndex ? { ...translation, value } : translation
    )))
    setDraft({ ...draft, groups })
  }

  function confirmTranslationEdit() {
    if (!draft) return
    scheduleDraft(draft)
    setEditingKey(null)
  }

  function addTranslation() {
    if (!draft) return
    const groups = [...(draft.groups ?? []), [{ original: '', value: '', selected: true }]]
    scheduleDraft({ ...draft, groups })
    setEditingKey(`${groups.length - 1}-0`)
  }

  function addTag(value: string) {
    const tag = value.trim()
    if (!tag || !draft || draft.tags?.includes(tag)) return
    scheduleDraft({ ...draft, tags: [...(draft.tags ?? []), tag] })
    setRemoveTags((current) => current.filter((item) => item !== tag))
  }

  function removeDraftTag(tag: string) {
    if (!draft) return
    scheduleDraft({ ...draft, tags: (draft.tags ?? []).filter((item) => item !== tag) })
    if (existing?.tags.includes(tag)) setRemoveTags((current) => current.includes(tag) ? current : [...current, tag])
  }

  function toggleFactoryTag(tag: string) {
    if (draft?.tags?.includes(tag)) removeDraftTag(tag)
    else addTag(tag)
  }

  function toggleDraftFlag(nextFlag: number) {
    if (!draft) return
    const flag = draft.flag === nextFlag ? undefined : nextFlag
    setFlag(flag ?? null)
    scheduleDraft({ ...draft, flag })
  }

  function chooseQueuedCardFlag(nextFlag: number) {
    const value = queuedCardFlag === nextFlag ? 0 : nextFlag
    setQueuedCardFlag(value)
    setFlag(value)
  }

  async function saveConfig(nextConfig: WorkspaceConfig) {
    setConfig(nextConfig)
    try {
      const saved = await api.patch<Session>(`/backend/sessions/${sessionId}`, {
        deckName: nextConfig.deckName || undefined,
        modelName: nextConfig.modelName || undefined,
        fieldMapping: nextConfig.fieldMapping,
      })
      setSession(saved)
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  async function chooseDeck(deckName: string) {
    const nextConfig = { ...config, deckName }
    await saveConfig(nextConfig)
    await loadDeckModels(deckName)
  }

  async function chooseModel(modelName: string) {
    const schemaForModel = await loadModelSchema(modelName)
    const mapping = schemaForModel ? defaultFieldMapping(schemaForModel.fields, config.fieldMapping) : config.fieldMapping
    await saveConfig({ ...config, modelName, fieldMapping: mapping })
  }

  async function changeMapping(update: Partial<FieldMapping>) {
    await saveConfig({ ...config, fieldMapping: { ...config.fieldMapping, ...update } })
    if (draft) void requestPreview(false)
  }

  function configurationReady() {
    return targetConfigured(config)
  }

  function effectiveConfig(): WorkspaceConfig {
    const override = draft?.targetOverride
    if (!override?.deckName && !override?.modelName) return config
    return {
      deckName: override.deckName || config.deckName,
      modelName: override.modelName || config.modelName,
      fieldMapping: override.fieldMapping || config.fieldMapping,
    }
  }

  function effectiveConfigurationReady() {
    return targetConfigured(effectiveConfig())
  }

  async function openOverride() {
    if (!draft) return
    setOverrideOpen(true)
    const override = draft.targetOverride
    if (override?.deckName) {
      try {
        const context = await api.post<DeckContext>('/backend/deck-context', { deckName: override.deckName })
        setOverrideModels(context.models)
      } catch (requestError) {
        setError(errorMessage(requestError))
      }
    }
    if (override?.modelName) {
      const loadedSchema = await loadModelSchemaForOverride(override.modelName)
      setOverrideSchema(loadedSchema)
    }
  }

  async function loadModelSchemaForOverride(modelName: string) {
    try {
      return await api.post<ModelSchema>('/backend/model-schema', { modelName })
    } catch (requestError) {
      setError(errorMessage(requestError))
      return null
    }
  }

  async function chooseOverrideDeck(deckName: string) {
    if (!draft) return
    try {
      const context = deckName
        ? await api.post<DeckContext>('/backend/deck-context', { deckName })
        : { models: [] }
      setOverrideModels(context.models)
      setOverrideSchema(null)
      scheduleDraft({
        ...draft,
        targetOverride: { deckName, modelName: '', fieldMapping: {} },
      })
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  async function chooseOverrideModel(modelName: string) {
    if (!draft) return
    const loadedSchema = await loadModelSchemaForOverride(modelName)
    if (!loadedSchema) return
    setOverrideSchema(loadedSchema)
    const previousMapping = draft.targetOverride?.fieldMapping || config.fieldMapping
    scheduleDraft({
      ...draft,
      targetOverride: {
        deckName: draft.targetOverride?.deckName || config.deckName,
        modelName,
        fieldMapping: defaultFieldMapping(loadedSchema.fields, previousMapping),
      },
    })
  }

  function changeOverrideMapping(update: Partial<FieldMapping>) {
    if (!draft) return
    const previous = draft.targetOverride?.fieldMapping || config.fieldMapping
    scheduleDraft({
      ...draft,
      targetOverride: {
        deckName: draft.targetOverride?.deckName || config.deckName,
        modelName: draft.targetOverride?.modelName || config.modelName,
        fieldMapping: { ...previous, ...update },
      },
    })
  }

  function clearOverride() {
    if (!draft) return
    const { targetOverride: _, ...withoutOverride } = draft
    setOverrideOpen(false)
    setOverrideModels([])
    setOverrideSchema(null)
    scheduleDraft(withoutOverride)
  }

  async function requestPreview(showFailure = true) {
    const entryId = draft?.entryId
    if (!effectiveConfigurationReady()) {
      if (showFailure) setError('Choose a deck, note type, English field, and translation field before previewing.')
      return
    }
    setPreviewing(true)
    try {
      const target = effectiveConfig()
      const nextPreview = isReview
        ? await api.post<Preview>('/backend/review/item/preview', {
            draft,
            deckName: target.deckName,
            modelName: target.modelName,
            fieldMapping: target.fieldMapping,
          })
        : await api.post<Preview>(`/backend/sessions/${sessionId}/current/preview`, { entryId })
      if (!isReview && entryId !== sourceEntry.current) return
      setPreview(nextPreview)
      if (existing) await loadExistingNote(false)
    } catch (requestError) {
      if (showFailure) setError(errorMessage(requestError))
    } finally {
      setPreviewing(false)
    }
  }

  async function commitCurrent() {
    if (!session || !draft) return
    if (!effectiveConfigurationReady()) {
      setError('Finish the Anki configuration before saving this card.')
      return
    }
    const isDuplicate = Boolean(existing || draft.existingNoteId)
    if (isDuplicate && existing && existing.modelName !== effectiveConfig().modelName) {
      setError(`This existing note uses ${existing.modelName}. Select that note type before updating it.`)
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (draftTimer.current) window.clearTimeout(draftTimer.current)
      let result: { action: string; noteId: number; audioDownloaded: boolean; audioError?: string; flagWarning?: string; syncWarning?: string; cleanupWarning?: string; cleanupPending?: boolean }
      let nextSession: Session
      if (isReview) {
        const target = effectiveConfig()
        result = await api.post<{ action: string; noteId: number; audioDownloaded: boolean; audioError?: string; flagWarning?: string; syncWarning?: string; cleanupWarning?: string; cleanupPending?: boolean }>('/backend/review/item/commit', {
          noteId: session.current?.noteId,
          cardId: session.current?.cardId,
          draft,
          action: isDuplicate ? 'update' : 'create',
          removeTags,
          flag,
          deckName: target.deckName,
          modelName: target.modelName,
          fieldMapping: target.fieldMapping,
        })
        if (result.cleanupPending) {
          nextSession = session
        } else {
          const remaining = reviewItems.slice(1)
          const completed = reviewCompleted + 1
          setReviewItems(remaining)
          setReviewCompleted(completed)
          nextSession = nextReviewSession(remaining, completed)
        }
      } else {
        await persistDraft(draft, false)
        const sessionResult = await api.post<{ action: string; noteId: number; audioDownloaded: boolean; audioError?: string; flagWarning?: string; syncWarning?: string; cleanupWarning?: string; session: Session }>(
          `/backend/sessions/${sessionId}/current/commit`,
          { action: isDuplicate ? 'update' : 'create', removeTags, flag, entryId: draft.entryId },
        )
        result = sessionResult
        nextSession = sessionResult.session
      }
      setNotice(`${result.action === 'updated' ? 'Updated' : 'Created'} note ${result.noteId}${result.audioDownloaded ? ' with audio.' : `. Audio was unavailable, so noAudio will be tagged: ${result.audioError ?? 'unknown reason'}`}${result.flagWarning ? ` Flag was not changed: ${result.flagWarning}` : ''}${result.syncWarning ? ` Anki sync is pending: ${result.syncWarning}` : ''}${result.cleanupWarning ? ` ${result.cleanupWarning}` : ''}`)
      setSession(nextSession)
      await hydrateCurrent(nextSession, config)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  async function discardCurrent() {
    if (!session) return
    setSaving(true)
    setError(null)
    try {
      if (draftTimer.current) window.clearTimeout(draftTimer.current)
      let nextSession: Session
      if (isReview) {
        const remaining = reviewItems.slice(1)
        const completed = reviewCompleted + 1
        setReviewItems(remaining)
        setReviewCompleted(completed)
        nextSession = nextReviewSession(remaining, completed)
      } else {
        nextSession = await api.post<Session>(`/backend/sessions/${sessionId}/current/discard`, { entryId: String(session.current?.id) })
      }
      setNotice(isReview ? 'Moved to the next review item.' : 'Discarded the current entry from its source file. Anki was not changed.')
      setSession(nextSession)
      await hydrateCurrent(nextSession, config)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  async function askGemini(compareTranslations: boolean) {
    if (!draft?.word) return
    setGeminiLoading(true)
    setError(null)
    try {
      const response = compareTranslations
        ? await api.post<{ text: string }>('/backend/gemini/review-translations', {
            word: draft.word,
            currentTranslation: existing?.fields[effectiveConfig().fieldMapping.translationField ?? ''] ?? '',
            proposedTranslations: preview?.selectedGroups ?? selectedGroups(draft),
          })
        : await api.post<{ text: string }>('/backend/gemini/translate', {
            word: draft.word,
            dikiTranslations: (draft.groups ?? [])
              .map((group) => group.filter((translation) => !translation.isBreak && translation.original).map((translation) => translation.original))
              .filter((group) => group.length > 0),
          })
      setGeminiText(response.text)
      setGeminiMode(compareTranslations ? 'review' : 'translate')
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setGeminiLoading(false)
    }
  }

  async function exitWorkspace() {
    try {
      if (draft && !isReview) {
        if (draftTimer.current) window.clearTimeout(draftTimer.current)
        await persistDraft(draft, false)
      }
    } catch {
      // The persisted version remains available if the local server is unreachable.
    }
    onExit()
  }

  if (loading) {
    return <main className="workspace-shell"><header className="topbar"><div className="brand"><span className="brand__mark">AF</span><span>Anki Flashcards Factory</span></div></header><LoadingMark label={isReview ? 'Opening review' : 'Reading source file'} /></main>
  }

  if (!session) {
    return <main className="workspace-shell"><header className="topbar"><div className="brand"><span className="brand__mark">AF</span><span>Anki Flashcards Factory</span></div><button className="button button--secondary" type="button" onClick={() => void exitWorkspace()}>Exit to home</button></header><div className="workspace-error"><h1>Source unavailable</h1><p>{error ?? 'The source file could not be loaded.'}</p></div></main>
  }

  if (session.mode === 'add' && !targetConfigured(config)) {
    return <TargetSetup
      sessionId={sessionId as string}
      initialConfig={config}
      models={models}
      error={error}
      onExit={() => void exitWorkspace()}
      onConfigured={async (nextConfig) => {
        try {
          const saved = await api.patch<Session>(`/backend/sessions/${sessionId}`, {
            deckName: nextConfig.deckName,
            modelName: nextConfig.modelName,
            fieldMapping: nextConfig.fieldMapping,
          })
          setConfig(nextConfig)
          setSession(saved)
          await loadDeckModels(nextConfig.deckName)
          await loadModelSchema(nextConfig.modelName)
          await hydrateCurrent(saved, nextConfig)
        } catch (requestError) {
          setError(errorMessage(requestError))
          throw requestError
        }
      }}
    />
  }

  const currentWord = draft?.word || session.current?.word || 'Existing Anki card'
  const isDuplicate = Boolean(existing || draft?.existingNoteId)
  const completed = !session.current
  const suggestedModels = deckModels.filter((model) => !models.includes(model))
  const allModels = [...deckModels, ...models.filter((model) => !deckModels.includes(model)), ...suggestedModels]
  const additionalFields = config.fieldMapping.additionalFields ?? {}
  const cardTarget = effectiveConfig()
  const cardReady = session.mode === 'review' || lookup?.exactMatch === true
  const useGeminiReview = Boolean(isDuplicate && draft?.tags?.includes('GEMINI_DIFF'))

  return (
    <main className="workspace-shell">
      <header className="topbar workspace-topbar">
        <div className="brand"><span className="brand__mark">AF</span><span>Anki Flashcards Factory</span></div>
        <div className="queue-meter"><span>{session.mode === 'review' ? 'REVIEW QUEUE' : 'ADD QUEUE'}</span><strong>{session.remainingCount} <small>remaining</small></strong></div>
        {!isReview ? <button className="tiny-button" type="button" disabled={saving || loading} onClick={() => void loadWorkspace()}>Reload source</button> : null}
        <button className="button button--secondary" type="button" onClick={() => void exitWorkspace()}>Exit to home</button>
      </header>

      <Notice message={error ? { tone: 'error', text: error } : null} />

      {completed ? (
          <section className="completion-card"><p className="eyebrow">{isReview ? 'REVIEW COMPLETE' : 'SOURCE EMPTY'}</p><h1>Everything here is accounted for.</h1><p>{isReview ? 'Return home to choose another review.' : 'This source has no pending words. Reload after adding vocabulary, or choose another source.'}</p>{notice ? <p className="completion-card__notice">{notice}</p> : null}<button className="button button--primary" type="button" onClick={() => void exitWorkspace()}>Return home</button></section>
      ) : (
        <>
          <section className="word-banner">
            <div><p className="eyebrow">CURRENT {session.mode === 'review' ? 'CARD' : 'WORD'}</p><h1>{currentWord}</h1>{draft?.sourceWord && draft.sourceWord !== draft.word ? <p>Imported as: {draft.sourceWord}</p> : null}</div>
            <div className="word-banner__meta"><span>{session.completedCount} completed</span><span>Position {(session.current?.position ?? session.completedCount) + 1}</span><span className={draft?.targetOverride ? 'word-banner__target word-banner__target--override' : 'word-banner__target'}>{draft?.targetOverride ? 'One-card deck' : 'Deck'}: {cardTarget.deckName}</span><span className={draft?.targetOverride ? 'word-banner__target word-banner__target--override' : 'word-banner__target'}>{draft?.targetOverride ? 'One-card note type' : 'Note type'}: {cardTarget.modelName}</span>{isDuplicate ? <b>Existing note found</b> : <b>New note</b>}</div>
          </section>

          {isDuplicate ? <section className="duplicate-decision"><div><p className="duplicate-alert-label">EXISTING ANKI NOTE DETECTED</p>{existing ? <div className="duplicate-decision__details"><div className="duplicate-decision__current"><span>Current translation</span><div dangerouslySetInnerHTML={{ __html: existing.fields[cardTarget.fieldMapping.translationField ?? ''] || '<i>(empty)</i>' }} /></div><p className="duplicate-decision__tags"><strong>Existing tags:</strong> <span>{existing.tags.length ? existing.tags.join(', ') : 'none'}</span></p></div> : <p>Loading the current Anki card...</p>}</div>{!isReview ? <div className="duplicate-decision__actions"><button className="button button--secondary" type="button" disabled={saving} onClick={() => void discardCurrent()}>Discard card from queue</button></div> : null}</section> : null}

          <section className="ai-assist"><button className="button button--secondary" type="button" disabled={geminiLoading || !draft?.word} onClick={() => void askGemini(useGeminiReview)}>{geminiLoading ? 'Asking AI...' : useGeminiReview ? 'Compare translations using AI' : 'Translate word using AI'}</button>{geminiText ? <div className="ai-assist__answer"><MarkdownAnswer value={geminiText} /></div> : null}</section>

          <div className="workspace-grid">

            <section className="editor-column">
              {session.mode === 'add' && lookup && !lookup.exactMatch ? <section className="panel suggestion-panel"><p className="eyebrow">DIKI COULD NOT CONFIRM THIS SPELLING</p><h2>Choose a suggestion or try another spelling</h2><div className="suggestion-edit"><input className="text-input" value={suggestionInput} onChange={(event) => setSuggestionInput(event.target.value)} /><button className="button button--secondary" type="button" onClick={() => void lookupCurrent(suggestionInput)}>Look up</button></div>{lookup.suggestions.length ? <div className="suggestion-list">{lookup.suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => void lookupCurrent(suggestion)}>{suggestion}</button>)}</div> : <p className="muted">Diki did not provide alternate spellings. You can discard this entry or create a custom card.</p>}</section> : null}

              {cardReady ? <><section className="panel translations-panel">
                <div className="panel__heading"><div><h2>Meanings from Diki</h2></div><div className="translation-heading-actions">{session.mode === 'review' ? <button className="tiny-button" type="button" disabled={!draft?.word} onClick={() => void lookupCurrent(draft?.word)}>Refresh Diki</button> : null}<span className="counter-badge">{selectedGroups(draft).flat().length} selected</span></div></div>
                <div className="translation-groups">
                  {(draft?.groups ?? []).map((group, groupIndex) => <fieldset className="translation-group" key={`group-${groupIndex}`}><legend>Sense {String(groupIndex + 1).padStart(2, '0')}</legend>{group.map((translation, translationIndex) => {
                    const key = `${groupIndex}-${translationIndex}`
                    const editing = editingKey === key
                    const modified = !translation.isBreak && translation.original !== translation.value
                    return <div className={`translation-row ${translation.isBreak ? 'translation-row--break' : ''} ${translation.selected ? 'translation-row--selected' : ''}`} key={key}><label className="translation-toggle"><input type="checkbox" checked={translation.selected} onChange={(event) => updateTranslation(groupIndex, translationIndex, { selected: event.target.checked })} /><span /></label><div className="translation-value">{editing ? <input autoFocus value={translation.value} onChange={(event) => editTranslationValue(groupIndex, translationIndex, event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') confirmTranslationEdit() }} /> : <span>{translation.isBreak ? '<br>' : translation.value || 'Untitled translation'}</span>}</div><div className="translation-actions">{!translation.isBreak ? <>{editing ? <button className="translation-icon-button translation-icon-button--confirm" type="button" aria-label="Confirm edit" title="Confirm edit" onClick={confirmTranslationEdit}>&#10003;</button> : <button className="translation-icon-button" type="button" aria-label="Edit translation" title="Edit translation" onClick={() => setEditingKey(key)}>&#9998;</button>}{modified ? <button className="translation-icon-button translation-icon-button--reset" type="button" aria-label="Reset to Diki" title="Reset to Diki" onClick={() => updateTranslation(groupIndex, translationIndex, { value: translation.original })}>&#8634;</button> : null}</> : null}</div></div>
                  })}</fieldset>)}
                </div>
                {!draft?.groups?.length ? <EmptyState title="No translations loaded" text={session.mode === 'review' ? 'Create a translation below or use the existing card fields as your starting point.' : 'Choose a spelling, then look it up again. You may also create a custom translation.'} /> : null}
                <button className="button button--ghost add-translation" type="button" disabled={!draft} onClick={addTranslation}>New custom translation</button>
              </section>

              <section className="panel tags-panel">
                <p className="eyebrow">Tags and completion</p>
                <div className="factory-tags">{FACTORY_TAGS.map((tag) => <button className={`tag-chip ${draft?.tags?.includes(tag) ? 'tag-chip--active' : ''}`} type="button" key={tag} onClick={() => toggleFactoryTag(tag)}>{tag}</button>)}</div>
                <div className="tag-editor"><div className="tag-list">{(draft?.tags ?? []).filter((tag) => !FACTORY_TAGS.includes(tag)).map((tag) => <button className="tag-chip tag-chip--custom" key={tag} type="button" onClick={() => removeDraftTag(tag)}>{tag} <span>Remove</span></button>)}</div><div className="custom-tag-form"><input className="text-input" value={customTag} placeholder="Custom tag" onChange={(event) => setCustomTag(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); addTag(customTag); setCustomTag('') } }} /><button className="button button--secondary" type="button" onClick={() => { addTag(customTag); setCustomTag('') }}>Save tag</button></div></div>
                {session.mode === 'add' && !isDuplicate ? <div className="flag-picker"><span className="flag-picker__label">Flag generated cards</span><div className="flag-picker__options" role="group" aria-label="Anki card flag">{FLAG_NAMES.slice(1).map((name, index) => { const value = index + 1; return <button className={`flag-chip flag-chip--${value} ${draft?.flag === value ? 'flag-chip--active' : ''}`} type="button" key={name} aria-pressed={draft?.flag === value} onClick={() => toggleDraftFlag(value)}><i /><span>{name}</span></button> })}</div></div> : null}
                {session.mode === 'review' && session.filter.kind === 'flag' ? <div className="flag-picker"><span className="flag-picker__label">Queued card flag</span><div className="flag-picker__options" role="group" aria-label="Queued Anki card flag">{FLAG_NAMES.slice(1).map((name, index) => { const value = index + 1; return <button className={`flag-chip flag-chip--${value} ${queuedCardFlag === value ? 'flag-chip--active' : ''}`} type="button" key={name} aria-pressed={queuedCardFlag === value} onClick={() => chooseQueuedCardFlag(value)}><i /><span>{name}</span></button> })}</div></div> : null}
              </section></> : null}
            </section>

            <aside className="preview-column">
              <section className="panel preview-panel">
                <div className="panel__heading"><div><p className="eyebrow">SERVER PREVIEW</p><h2>Card payload</h2></div><button className="button button--secondary" type="button" disabled={previewing || !draft || !cardReady} onClick={() => void requestPreview()}>{previewing ? 'Building...' : 'Refresh preview'}</button></div>
                {preview ? <><div className="preview-target-row"><div className="preview-target"><span>{preview.target.isOverride ? 'One-card target' : 'Batch target'}: <b>{preview.target.deckName}</b> / {preview.target.modelName}</span></div>{!isDuplicate && session.mode === 'add' ? <button className="button button--secondary preview-target__override" type="button" onClick={() => void openOverride()}>Override destination</button> : null}</div><div className="card-preview"><span className="card-preview__label">{preview.word}</span><div className="card-preview__translation" dangerouslySetInnerHTML={{ __html: preview.translationHtml || '<span class="empty-preview">No selected translation</span>' }} /><div className="card-preview__footer"><span>{preview.audioFile}</span><span>{preview.tags.length ? preview.tags.join(', ') : 'No tags'}</span></div></div><div className="field-payload">{Object.entries(preview.fields).map(([field, value]) => <div key={field}><span>{field}</span><code>{value || '(empty)'}</code></div>)}</div></> : <EmptyState title="Preview waits for configuration" text="Select a deck, model, and field mapping. The preview is generated by the backend, not recreated in the browser." />}
              </section>

              {existing ? <section className="panel duplicate-panel"><div className="panel__heading"><div><p className="eyebrow">EXISTING ANKI NOTE #{existing.noteId}</p><h2>Update in place</h2></div><span className="duplicate-badge">Scheduling safe</span></div>{existing.modelName !== cardTarget.modelName ? <div className="inline-error">This note uses <b>{existing.modelName}</b>. Select that model to update; note-type changes are intentionally blocked.</div> : null}<p className="muted">The English field stays locked. Changed fields will be updated on this existing note instead of creating a replacement.</p><div className="diff-list">{existing.fieldDiff?.length ? existing.fieldDiff.map((difference) => <div className={`diff-row ${difference.changed ? 'diff-row--changed' : ''}`} key={difference.field}><strong>{difference.field}</strong><div><span>Current</span><div className="diff-html" dangerouslySetInnerHTML={{ __html: difference.existing || '<i>(empty)</i>' }} /></div><div><span>Proposed</span><div className="diff-html" dangerouslySetInnerHTML={{ __html: difference.proposed || '<i>(empty)</i>' }} /></div></div>) : Object.entries(existing.fields).map(([field, value]) => <div className="diff-row" key={field}><strong>{field}</strong><div className="diff-html" dangerouslySetInnerHTML={{ __html: value || '<i>(empty)</i>' }} /></div>)}</div></section> : null}

              {!isDuplicate && session.mode === 'add' ? <section className="card-target-override"><div><p className="eyebrow">ONE CARD ONLY</p><h3>Override destination</h3><p>Use another deck or note type for this card without changing the queue target.</p></div><div className="override-actions"><button className="button button--secondary" type="button" onClick={() => overrideOpen ? setOverrideOpen(false) : void openOverride()}>{overrideOpen ? 'Hide override' : draft?.targetOverride ? 'Edit override' : 'Override this card'}</button>{draft?.targetOverride ? <button className="text-button" type="button" onClick={clearOverride}>Use batch target</button> : null}</div>{overrideOpen ? <div className="override-form"><label className="field-label">Deck for this card</label><select className="select-input" value={draft?.targetOverride?.deckName ?? ''} onChange={(event) => void chooseOverrideDeck(event.target.value)}><option value="">Choose a deck</option>{decks.map((deck) => <option key={deck} value={deck}>{deck}</option>)}</select><label className="field-label">Note type for this card</label><select className="select-input" value={draft?.targetOverride?.modelName ?? ''} onChange={(event) => void chooseOverrideModel(event.target.value)}><option value="">Choose a note type</option>{[...overrideModels, ...models.filter((model) => !overrideModels.includes(model))].map((model) => <option key={model} value={model}>{model}{overrideModels.includes(model) ? ' (in deck)' : ''}</option>)}</select>{overrideSchema ? <div className="override-mapping"><label className="mapping-row">English word<select value={draft?.targetOverride?.fieldMapping?.englishField ?? ''} onChange={(event) => changeOverrideMapping({ englishField: event.target.value })}><option value="">Select field</option>{overrideSchema.fields.map((field) => <option key={field} value={field}>{field}</option>)}</select></label><label className="mapping-row">Polish translation<select value={draft?.targetOverride?.fieldMapping?.translationField ?? ''} onChange={(event) => changeOverrideMapping({ translationField: event.target.value })}><option value="">Select field</option>{overrideSchema.fields.map((field) => <option key={field} value={field}>{field}</option>)}</select></label><label className="mapping-row">Audio <span>optional</span><select value={draft?.targetOverride?.fieldMapping?.audioField ?? ''} onChange={(event) => changeOverrideMapping({ audioField: event.target.value })}><option value="">No audio field</option>{overrideSchema.fields.map((field) => <option key={field} value={field}>{field}</option>)}</select></label></div> : null}</div> : null}</section> : null}

              <section className="commit-panel">{notice ? <p className="commit-panel__notice">{notice}</p> : null}<button className="button button--primary button--commit" type="button" disabled={saving || !draft || !cardReady || !effectiveConfigurationReady() || (isDuplicate && !existing)} onClick={() => void commitCurrent()}>{saving ? 'Saving...' : isDuplicate ? 'Update and continue' : 'Create and continue'}</button><div className="commit-secondary-actions"><button className="text-button text-button--danger" type="button" disabled={saving} onClick={() => void discardCurrent()}>{isReview ? 'Next review item' : 'Discard from queue'}</button>{session.mode === 'add' ? <button className="text-button" type="button" disabled={saving} onClick={() => setCustomCardOpen(true)}>Create custom card</button> : null}</div></section>
            </aside>
          </div>
          {overrideOpen && !isDuplicate && session.mode === 'add' ? <div className="override-destination-backdrop" role="dialog" aria-modal="true" aria-label="Override destination"><section className="override-destination-dialog"><div className="panel__heading"><div><p className="eyebrow">ONE CARD ONLY</p><h2>Override destination</h2><p>Choose another deck or note type for this card. The queue target will not change.</p></div><button className="tiny-button" type="button" onClick={() => setOverrideOpen(false)}>Close</button></div><label className="field-label">Deck for this card</label><select className="select-input" value={draft?.targetOverride?.deckName ?? ''} onChange={(event) => void chooseOverrideDeck(event.target.value)}><option value="">Choose a deck</option>{decks.map((deck) => <option key={deck} value={deck}>{deck}</option>)}</select><label className="field-label">Note type for this card</label><select className="select-input" value={draft?.targetOverride?.modelName ?? ''} onChange={(event) => void chooseOverrideModel(event.target.value)}><option value="">Choose a note type</option>{[...overrideModels, ...models.filter((model) => !overrideModels.includes(model))].map((model) => <option key={model} value={model}>{model}{overrideModels.includes(model) ? ' (in deck)' : ''}</option>)}</select>{overrideSchema ? <div className="override-mapping"><label className="mapping-row">English word<select value={draft?.targetOverride?.fieldMapping?.englishField ?? ''} onChange={(event) => changeOverrideMapping({ englishField: event.target.value })}><option value="">Select field</option>{overrideSchema.fields.map((field) => <option key={field} value={field}>{field}</option>)}</select></label><label className="mapping-row">Polish translation<select value={draft?.targetOverride?.fieldMapping?.translationField ?? ''} onChange={(event) => changeOverrideMapping({ translationField: event.target.value })}><option value="">Select field</option>{overrideSchema.fields.map((field) => <option key={field} value={field}>{field}</option>)}</select></label><label className="mapping-row">Audio <span>optional</span><select value={draft?.targetOverride?.fieldMapping?.audioField ?? ''} onChange={(event) => changeOverrideMapping({ audioField: event.target.value })}><option value="">No audio field</option>{overrideSchema.fields.map((field) => <option key={field} value={field}>{field}</option>)}</select></label></div> : null}<div className="override-destination-actions">{draft?.targetOverride ? <button className="button button--secondary" type="button" onClick={clearOverride}>Use batch target</button> : null}<button className="button button--primary" type="button" onClick={() => setOverrideOpen(false)}>Done</button></div></section></div> : null}
          {customCardOpen && session.mode === 'add' ? <CustomCardForm
            sessionId={sessionId as string}
            entryId={String(session.current?.id)}
            currentWord={currentWord}
            initialDeckName={config.deckName}
            initialModelName={config.modelName}
            decks={decks}
            models={models}
            onClose={() => setCustomCardOpen(false)}
            onComplete={async (result) => {
              setNotice(`Created custom note ${result.noteId}.${result.syncWarning ? ` Anki sync is pending: ${result.syncWarning}` : ''}${result.cleanupWarning ? ` ${result.cleanupWarning}` : ''}`)
              setSession(result.session)
              setCustomCardOpen(false)
              await hydrateCurrent(result.session, config)
            }}
          /> : null}
        </>
      )}
    </main>
  )
}

function LoadingMark({ label }: { label: string }) {
  return <div className="loading-mark"><span className="loading-mark__bars"><i /><i /><i /></span>{label}</div>
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="empty-state"><strong>{title}</strong><p>{text}</p></div>
}
