import { useState } from 'react'

import { acceptInvitation, createOrganisation, loginUrl } from '../../services/api'

export function LoginPage() {
  const cancelled = new URLSearchParams(window.location.search).get('auth_error') === 'login_cancelled'
  return <main className="auth-shell"><section className="auth-card"><span className="brand-mark">RB</span><p className="eyebrow">Secure workspace</p><h1>Sign in to RegBridge</h1>{cancelled && <div className="notice notice--review"><strong>Sign-in was cancelled</strong><span>No RegBridge session was created. You can try again when ready.</span></div>}<p>Continue through your organisation's configured OpenID Connect provider. RegBridge receives no password and keeps provider tokens off the frontend.</p><a className="button button--primary" href={loginUrl(`${window.location.pathname}${window.location.search}`)}>Continue to sign in</a></section></main>
}

export function OrganisationOnboarding({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [invitationToken, setInvitationToken] = useState(() => new URLSearchParams(window.location.search).get('invitation') ?? '')
  const [error, setError] = useState<string | null>(null)
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError(null)
    try { await createOrganisation(name, slug); onCreated() } catch (caught) { setError(caught instanceof Error ? caught.message : 'Organisation creation failed.') }
  }
  async function accept(event: React.FormEvent) {
    event.preventDefault(); setError(null)
    try { await acceptInvitation(invitationToken.trim()); onCreated() } catch (caught) { setError(caught instanceof Error ? caught.message : 'Invitation acceptance failed.') }
  }
  return <main className="auth-shell"><section className="auth-card auth-card--wide"><p className="eyebrow">Organisation onboarding</p><h1>Join or create a workspace</h1><p>Use an invitation from an owner, or create a new organisation where your first membership will be OWNER.</p>{error && <div className="notice notice--blocking">{error}</div>}<div className="onboarding-options"><form onSubmit={(event) => void accept(event)}><h2>Accept invitation</h2><label>One-time invitation token<input required autoComplete="off" value={invitationToken} onChange={(event) => setInvitationToken(event.target.value)} /></label><button className="button button--primary">Join organisation</button></form><form onSubmit={(event) => void submit(event)}><h2>Create organisation</h2><label>Organisation name<input required minLength={2} maxLength={200} value={name} onChange={(event) => setName(event.target.value)} /></label><label>Workspace slug<input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" value={slug} onChange={(event) => setSlug(event.target.value.toLowerCase())} /></label><button className="button button--primary">Create organisation</button></form></div></section></main>
}
