export type Translation = {
  original: string
  value: string
  selected: boolean
  isBreak?: boolean
}

export type Draft = {
  matchingHeadwords?: { word: string; caseSensitive: boolean }[]
  lookupQuery?: string
  entryId?: string
  sourceWord?: string
  word?: string
  resolvedWord?: string | null
  caseSensitive?: boolean
  groups?: Translation[][]
  tags?: string[]
  flag?: number
  existingNoteId?: number | null
  targetOverride?: TargetOverride
}

export type FieldMapping = {
  englishField?: string
  translationField?: string
  audioField?: string
  additionalFields?: Record<string, string>
}

export type TargetOverride = {
  deckName?: string
  modelName?: string
  fieldMapping?: FieldMapping
}

export type DeckNode = {
  name: string
  fullName: string
  children: DeckNode[]
}

export type DeckContext = {
  deckName: string
  models: string[]
  modelCounts: Array<{ name: string; count: number }>
}

export type QueueItem = {
  id: number | string
  position: number
  word?: string | null
  noteId?: number | null
  cardId?: number | null
}

export type Session = {
  id: string
  mode: 'add' | 'review'
  name: string
  source: string
  filter: { kind?: 'tag' | 'flag'; value?: string | number; deckName?: string | null }
  deckName?: string | null
  modelName?: string | null
  fieldMapping: FieldMapping
  draft: Draft
  completedCount: number
  createdAt: string
  updatedAt: string
  remainingCount: number
  current: QueueItem | null
  pendingRemoval?: SaveResult
}

export type SaveResult = {
  action: string
  noteId: number
  saveId: string
  verified: boolean
  audioDownloaded?: boolean
  audioError?: string
  flagWarning?: string
  syncWarning?: string
  confirmationWarning?: string | null
  cleanupWarning?: string
  cleanupPending?: boolean
}

export type SourceSaveResult = SaveResult & { session: Session }

export type SessionSummary = Pick<
  Session,
  'id' | 'mode' | 'name' | 'source' | 'deckName' | 'modelName' | 'completedCount' | 'remainingCount' | 'updatedAt'
> & { sourceError?: string | null }

export type Status = {
  ankiAvailable: boolean
  ankiError?: string | null
  geminiConfigured: boolean
  databasePath?: string
  syncPending?: boolean
  syncError?: string | null
}

export type LookupResult = {
  matchingHeadwords?: { word: string; caseSensitive: boolean }[]
  draft?: Draft | null
  lookupQuery?: string
  pageKind?: 'entries' | 'suggestions' | 'related' | 'collocation' | 'not_found' | 'unknown' | null
  entryChoices?: string[]
  relatedEntries?: string[]
  entryId?: string
  sourceWord?: string
  word: string
  resolvedWord?: string | null
  caseSensitive?: boolean
  exactMatch: boolean
  groups: Translation[][]
  suggestions: string[]
  existingNoteId?: number | null
}

export type Preview = {
  word: string
  translationHtml: string
  selectedGroups: string[][]
  fields: Record<string, string>
  tags: string[]
  audioFile: string
  target: {
    deckName: string
    modelName: string
    fieldMapping: FieldMapping
    isOverride: boolean
  }
}

export type ExistingNote = {
  noteId: number
  modelName: string
  fields: Record<string, string>
  tags: string[]
  cards: Array<Record<string, unknown>>
  proposedFields?: Record<string, string>
  fieldDiff?: Array<{ field: string; existing: string; proposed: string; changed: boolean }>
}

export type ReviewFilter = { kind: 'tag' | 'flag'; value: string | number; deckName?: string }

export type ReviewItem = { noteId: number; cardId: number | null }

export type ReviewSnapshot = { items: ReviewItem[]; filter: ReviewFilter }

export type InventoryItem = { value: string | number; count: number }

export type Inventory = {
  tags: InventoryItem[]
  flags: InventoryItem[]
}

export type ModelSchema = {
  name: string
  fields: string[]
  templates: Record<string, unknown>
  styling: Record<string, unknown>
}
