import type { AuthSession } from '../types/regflow'

export type AuthGate = 'loading' | 'login' | 'onboarding' | 'application'

export function authGate(session: AuthSession | null): AuthGate {
  if (session === null) return 'loading'
  if (session.auth_enabled && !session.authenticated) return 'login'
  if (session.auth_enabled && !session.active_organisation) return 'onboarding'
  return 'application'
}

export function canManageOrganisation(role: 'OWNER' | 'MEMBER' | undefined): boolean {
  return role === 'OWNER'
}

export function mustClearWorkspace(previousOrganisationId: string | null, nextOrganisationId: string): boolean {
  return previousOrganisationId !== nextOrganisationId
}

export function authenticationRecovery(status: number): 'reauthenticate' | 'forbidden' | 'none' {
  if (status === 401) return 'reauthenticate'
  if (status === 403) return 'forbidden'
  return 'none'
}
