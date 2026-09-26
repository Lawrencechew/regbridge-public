import type { MouseEvent, ReactNode } from 'react'

import { routePaths, type AppRoute } from '../../platform/navigation'
import { PlatformStatus } from '../PlatformStatus'
import type { AuthSession } from '../../types/regflow'

interface Props {
  route: AppRoute
  connected: boolean | null
  onNavigate: (route: AppRoute) => void
  session: AuthSession | null
  onSwitchOrganisation: (organisationId: string) => void
  onLogout: () => void
}

function NavigationLink({ route, current, onNavigate, children, className = '' }: {
  route: AppRoute
  current: AppRoute
  onNavigate: (route: AppRoute) => void
  children: ReactNode
  className?: string
}) {
  function follow(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    onNavigate(route)
  }

  return <a className={className} href={routePaths[route]} aria-current={current === route ? 'page' : undefined} onClick={follow}>{children}</a>
}

export function AppNavigation({ route, connected, onNavigate, session, onSwitchOrganisation, onLogout }: Props) {
  return (
    <header className="app-header">
      <NavigationLink route="home" current={route} onNavigate={onNavigate} className="brand-lockup">
        <span className="brand-mark" aria-hidden="true">RB</span>
        <span><strong>RegBridge</strong><small>Regulatory last-mile platform</small></span>
      </NavigationLink>
      <nav className="primary-nav" aria-label="Primary navigation">
        <NavigationLink route="home" current={route} onNavigate={onNavigate}>Home</NavigationLink>
        <NavigationLink route="regflow" current={route} onNavigate={onNavigate}>Prepare Return</NavigationLink>
        <NavigationLink route="runs" current={route} onNavigate={onNavigate}>Runs</NavigationLink>
        <NavigationLink route="regpacks" current={route} onNavigate={onNavigate}>RegPacks</NavigationLink>
        {session?.authenticated && <NavigationLink route="organisation" current={route} onNavigate={onNavigate}>Organisation</NavigationLink>}
        <NavigationLink route="help" current={route} onNavigate={onNavigate}>Help &amp; Status</NavigationLink>
      </nav>
      <div className="identity-menu">{session?.authenticated && <><label><span className="sr-only">Active organisation</span><select aria-label="Active organisation" value={session.active_organisation?.id ?? ''} onChange={(event) => onSwitchOrganisation(event.target.value)}>{session.organisations.map((organisation) => <option key={organisation.id} value={organisation.id}>{organisation.name}</option>)}</select></label><span className="identity-user"><strong>{session.user?.display_name}</strong><small>{session.active_organisation?.role}</small></span><button className="button button--quiet" onClick={onLogout}>Logout</button></>}<PlatformStatus connected={connected} /></div>
    </header>
  )
}
