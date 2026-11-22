import { useState } from 'react'
import type { Translation } from './types'

// Translation selection and per-meaning editing for the main workspace.
export function TranslationEditor({ groups, onChange, disabled = false, emptyText }: {
  groups: Translation[][]
  onChange: (groups: Translation[][], persist?: boolean) => void
  disabled?: boolean
  emptyText: string
}) {
  const [editingKey, setEditingKey] = useState<string | null>(null)

  function update(groupIndex: number, translationIndex: number, change: Partial<Translation>, persist = true) {
    onChange(groups.map((group, gi) => group.map((translation, ti) => (
      gi === groupIndex && ti === translationIndex ? { ...translation, ...change } : translation
    ))), persist)
  }

  function confirm() {
    onChange(groups, true)
    setEditingKey(null)
  }

  function add() {
    onChange([...groups, [{ original: '', value: '', selected: true }]], true)
    setEditingKey(`${groups.length}-0`)
  }

  return <>
    <div className="translation-groups">
      {groups.map((group, groupIndex) => <fieldset className="translation-group" disabled={disabled} key={groupIndex}>
        <legend>Sense {String(groupIndex + 1).padStart(2, '0')}</legend>
        {group.map((translation, translationIndex) => {
          const key = `${groupIndex}-${translationIndex}`
          const editing = editingKey === key
          const modified = !translation.isBreak && translation.original !== translation.value
          return <div className={`translation-row ${translation.isBreak ? 'translation-row--break' : ''} ${translation.selected ? 'translation-row--selected' : ''}`} key={key}>
            <label className="translation-toggle"><input type="checkbox" aria-label={`Select ${translation.isBreak ? 'line break' : translation.value || 'custom translation'}`} checked={translation.selected} onChange={(event) => update(groupIndex, translationIndex, { selected: event.target.checked })} /><span /></label>
            <div className="translation-value">{editing
              ? <input autoFocus aria-label="Translation text" value={translation.value} onChange={(event) => update(groupIndex, translationIndex, { value: event.target.value }, false)} onKeyDown={(event) => { if (event.key === 'Enter') confirm() }} />
              : <span>{translation.isBreak ? '<br>' : translation.value || 'Untitled translation'}</span>}
            </div>
            <div className="translation-actions">{!translation.isBreak ? <>
              {editing
                ? <button className="translation-icon-button translation-icon-button--confirm" type="button" aria-label="Confirm edit" title="Confirm edit" onClick={confirm}>&#10003;</button>
                : <button className="translation-icon-button" type="button" aria-label="Edit translation" title="Edit translation" onClick={() => setEditingKey(key)}>&#9998;</button>}
              {modified ? <button className="translation-icon-button translation-icon-button--reset" type="button" aria-label="Reset to Diki" title="Reset to Diki" onClick={() => update(groupIndex, translationIndex, { value: translation.original })}>&#8634;</button> : null}
            </> : null}</div>
          </div>
        })}
      </fieldset>)}
    </div>
    {!groups.length ? <div className="empty-state"><strong>No translations loaded</strong><p>{emptyText}</p></div> : null}
    <button className="button button--ghost add-translation" type="button" disabled={disabled} onClick={add}>New custom translation</button>
  </>
}
