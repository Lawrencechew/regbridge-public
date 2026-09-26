import { describe, expect, it } from 'vitest'

import { routeFromPath, routePaths } from './navigation'

describe('platform navigation', () => {
  it.each([
    ['/', 'home'],
    ['/regflow', 'regflow'],
    ['/runs', 'runs'],
    ['/regpacks/', 'regpacks'],
    ['/organisation', 'organisation'],
    ['/help?from=footer', 'help'],
  ] as const)('maps %s to %s', (path, route) => {
    expect(routeFromPath(path)).toBe(route)
  })

  it('falls back to the home page for an unknown route', () => {
    expect(routeFromPath('/not-a-page')).toBe('home')
  })

  it('provides stable friendly paths', () => {
    expect(routePaths).toEqual({ home: '/', regflow: '/regflow', runs: '/runs', regpacks: '/regpacks', organisation: '/organisation', help: '/help' })
  })
})
