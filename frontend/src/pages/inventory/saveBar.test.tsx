import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { FeatureInfo } from '@/api/types'
import { renderWithApp } from '@/test/render'
import { FeaturesEditor, PropertiesEditor } from './ScopeEditors'

// Inventory editors save like Settings: changes collect under "N unsaved changes" with Save and Discard (#993).
const catalog = [{ id: 'telemetry', name: 'Telemetry', core: true, default: true }, { id: 'ssh', name: 'SSH', core: true, default: false }] as FeatureInfo[]

describe('inventory save bar', () => {
  it('collects feature switches instead of saving each one', () => {
    const onSave = vi.fn()
    renderWithApp(<FeaturesEditor catalog={catalog} value={{ ssh: true }} canEdit busy={false} onSave={onSave} />)
    expect(screen.queryByRole('region', { name: /save/i })).toBeNull()
    fireEvent.click(screen.getAllByRole('radio', { name: 'Off' })[0])
    fireEvent.click(screen.getAllByRole('radio', { name: 'Inherit' })[1])
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByText('2 unsaved changes')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith({ telemetry: false, ssh: null })
  })

  it('puts back what was there on Discard', () => {
    const onSave = vi.fn()
    renderWithApp(<FeaturesEditor catalog={catalog} value={{}} canEdit busy={false} onSave={onSave} />)
    fireEvent.click(screen.getAllByRole('radio', { name: 'On' })[1])
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    expect(screen.queryByText(/unsaved change/)).toBeNull()
    expect(onSave).not.toHaveBeenCalled()
  })

  it('counts changed properties, not empty rows', () => {
    const onSave = vi.fn()
    renderWithApp(<PropertiesEditor value={{ rack: 'A1' }} canEdit busy={false} onSave={onSave} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add property' }))
    expect(screen.queryByText(/unsaved change/)).toBeNull()
    fireEvent.change(screen.getAllByRole('textbox', { name: 'Value' })[0], { target: { value: 'B2' } })
    expect(screen.getByText('1 unsaved change')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith({ rack: 'B2' })
  })

  it('asks before the tab closes while something is unsaved', () => {
    renderWithApp(<PropertiesEditor value={{ rack: 'A1' }} canEdit busy={false} onSave={vi.fn()} />)
    const before = () => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented }
    expect(before()).toBe(false)
    fireEvent.change(screen.getByRole('textbox', { name: 'Value' }), { target: { value: 'B2' } })
    expect(before()).toBe(true)
  })
})
