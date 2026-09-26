import { describe, expect, it } from 'vitest'

import { authGate, authenticationRecovery, canManageOrganisation, mustClearWorkspace } from './presentation'
import type { AuthSession } from '../types/regflow'

const anonymous: AuthSession = { auth_enabled: true, authenticated: false, user: null, active_organisation: null, organisations: [] }
const user = { id: 'user-1', email: 'alice@example.test', display_name: 'Alice' }

describe('Phase 10 authentication presentation rules', () => {
  it('shows loading, login, and organisation onboarding deterministically', () => {
    expect(authGate(null)).toBe('loading')
    expect(authGate(anonymous)).toBe('login')
    expect(authGate({ ...anonymous, authenticated: true, user })).toBe('onboarding')
  })

  it('allows the application for a tenant session and legacy auth-disabled mode', () => {
    const organisation = { id: 'org-a', name: 'Alpha', slug: 'alpha', role: 'OWNER' as const }
    expect(authGate({ ...anonymous, authenticated: true, user, active_organisation: organisation, organisations: [organisation] })).toBe('application')
    expect(authGate({ ...anonymous, auth_enabled: false })).toBe('application')
  })

  it('shows administration controls only to owners', () => {
    expect(canManageOrganisation('OWNER')).toBe(true)
    expect(canManageOrganisation('MEMBER')).toBe(false)
    expect(canManageOrganisation(undefined)).toBe(false)
  })

  it('invalidates workspace state only when the tenant changes', () => {
    expect(mustClearWorkspace('org-a', 'org-b')).toBe(true)
    expect(mustClearWorkspace('org-a', 'org-a')).toBe(false)
  })

  it('distinguishes expired sessions from insufficient permissions', () => {
    expect(authenticationRecovery(401)).toBe('reauthenticate')
    expect(authenticationRecovery(403)).toBe('forbidden')
    expect(authenticationRecovery(422)).toBe('none')
  })
})
