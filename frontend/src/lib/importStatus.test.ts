import { describe, expect, it } from 'vitest'

import { makeImport } from '../test/fixtures'
import { isTerminal, pollInterval, stageStates, statusAnnouncement } from './importStatus'

describe('stageStates', () => {
  it('marca as etapas anteriores como feitas e a atual em andamento', () => {
    expect(stageStates('pending')).toEqual(['upcoming', 'upcoming', 'upcoming'])
    expect(stageStates('fetching')).toEqual(['current', 'upcoming', 'upcoming'])
    expect(stageStates('transcribing')).toEqual(['done', 'current', 'upcoming'])
    expect(stageStates('generating')).toEqual(['done', 'done', 'current'])
    expect(stageStates('done')).toEqual(['done', 'done', 'done'])
  })
})

describe('pollInterval', () => {
  it('para nos estados terminais', () => {
    expect(isTerminal('done')).toBe(true)
    expect(isTerminal('failed')).toBe(true)
    expect(pollInterval(makeImport({ status: 'done' }), 0)).toBe(false)
    expect(pollInterval(makeImport({ status: 'failed' }), 0)).toBe(false)
  })

  it('começa rápido e espaça com o tempo', () => {
    const imp = makeImport({ status: 'fetching' })
    expect(pollInterval(undefined, 0)).toBe(1000)
    expect(pollInterval(imp, 5_000)).toBe(1000)
    expect(pollInterval(imp, 30_000)).toBe(2000)
    expect(pollInterval(imp, 2 * 60_000)).toBe(5000)
    expect(pollInterval(imp, 10 * 60_000)).toBe(10_000)
  })

  it('espera mais quando está longe na fila ou adiado', () => {
    expect(pollInterval(makeImport({ status: 'pending', queue_position: 12 }), 0)).toBe(10_000)
    expect(pollInterval(makeImport({ status: 'pending', queue_position: 2 }), 0)).toBe(1000)
    expect(pollInterval(makeImport({ status: 'deferred' }), 0)).toBe(60_000)
  })
})

describe('statusAnnouncement', () => {
  it('fala a posição na fila', () => {
    expect(statusAnnouncement(makeImport({ status: 'pending', queue_position: 3 }))).toBe(
      'Na fila: 3º lugar.',
    )
    expect(statusAnnouncement(makeImport({ status: 'generating' }))).toBe('Escrevendo a receita.')
  })
})
