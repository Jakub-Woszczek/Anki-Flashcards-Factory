export type Translation = {
  original: string
  value: string
  selected: boolean
  isBreak?: boolean
}

export type Draft = {
  sourceWord?: string
  word?: string
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
  id: number
  position: number
  word?: string | null
  noteId?: number | null
  cardId?: number | null
}

export type QueueDiffLine = {
  kind: 'context' | 'add' | 'remove' | 'change'
  saved: string | null
  proposed: string | null
}

export type QueueDiffHunk = {
  id: string
  savedStart: number
  savedEnd: number
  proposedStart: number
  proposedEnd: number
  lines: QueueDiffLine[]
}

export type QueueDiff = {
  savedWords: string[]
  proposedWords: string[]
  hunks: QueueDiffHunk[]
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
  queue: QueueItem[]
}

export type SessionSummary = Pick<
  Session,
  'id' | 'mode' | 'name' | 'source' | 'deckName' | 'modelName' | 'completedCount' | 'remainingCount' | 'updatedAt'
>

export type Status = {
  ankiAvailable: boolean
  ankiError?: string | null
  geminiConfigured: boolean
  databasePath?: string
  syncPending?: boolean
  syncError?: string | null
}

export type LookupResult = {
  word: string
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
