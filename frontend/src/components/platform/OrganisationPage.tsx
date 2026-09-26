import { useCallback, useEffect, useState } from 'react'

import { getInvitations, getOrganisationMembers, inviteMember, removeMember, revokeInvitation, updateMemberRole } from '../../services/api'
import { canManageOrganisation } from '../../auth/presentation'
import type { AuthSession, OrganisationInvitation, OrganisationMember } from '../../types/regflow'

export function OrganisationPage({ session, onError }: { session: AuthSession; onError: (error: unknown) => void }) {
  const [members, setMembers] = useState<OrganisationMember[]>([])
  const [invitations, setInvitations] = useState<OrganisationInvitation[]>([])
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'OWNER' | 'MEMBER'>('MEMBER')
  const [issuedToken, setIssuedToken] = useState<string | null>(null)
  const owner = canManageOrganisation(session.active_organisation?.role)
  const load = useCallback(async () => {
    try {
      setMembers(await getOrganisationMembers())
      setInvitations(owner ? await getInvitations() : [])
    } catch (error) { onError(error) }
  }, [onError, owner])
  useEffect(() => {
    let ignored = false
    async function initialLoad() {
      try {
        const [loadedMembers, loadedInvitations] = await Promise.all([
          getOrganisationMembers(),
          owner ? getInvitations() : Promise.resolve([]),
        ])
        if (!ignored) { setMembers(loadedMembers); setInvitations(loadedInvitations) }
      } catch (error) { if (!ignored) onError(error) }
    }
    void initialLoad()
    return () => { ignored = true }
  }, [onError, owner])
  async function invite(event: React.FormEvent) {
    event.preventDefault()
    try { const created = await inviteMember(email, role); setIssuedToken(created.invitation_token); setEmail(''); await load() } catch (error) { onError(error) }
  }
  return <div className="platform-page"><section className="page-hero page-hero--compact"><p className="eyebrow">Organisation workspace</p><h1>{session.active_organisation?.name}</h1><p>Membership controls affect this organisation only. Operational records never cross workspace boundaries.</p></section>{owner && <section className="workflow-card"><h2>Invite a member</h2><form className="member-invite" onSubmit={(event) => void invite(event)}><label>Email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label><label>Role<select value={role} onChange={(event) => setRole(event.target.value as 'OWNER' | 'MEMBER')}><option>MEMBER</option><option>OWNER</option></select></label><button className="button button--primary">Create invitation</button></form>{issuedToken && <div className="notice notice--success"><strong>Invitation created</strong><span>Share this one-time token securely. It is shown only now.</span><code>{issuedToken}</code></div>}</section>}<section className="workflow-card"><h2>Members</h2><div className="table-scroll"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th>{owner && <th>Actions</th>}</tr></thead><tbody>{members.map((member) => <tr key={member.user_id}><td>{member.display_name}</td><td>{member.email}</td><td>{member.role}</td>{owner && <td><div className="actions"><button className="button button--quiet" onClick={() => void updateMemberRole(member.user_id, member.role === 'OWNER' ? 'MEMBER' : 'OWNER').then(load).catch(onError)}>{member.role === 'OWNER' ? 'Make member' : 'Make owner'}</button><button className="button button--danger" onClick={() => void removeMember(member.user_id).then(load).catch(onError)}>Remove</button></div></td>}</tr>)}</tbody></table></div></section>{owner && <section className="workflow-card"><h2>Invitations</h2>{invitations.length === 0 ? <p className="muted">No invitations.</p> : invitations.map((invitation) => <article className="invitation-row" key={invitation.id}><div><strong>{invitation.invited_email}</strong><span>{invitation.invited_role} · {invitation.state}</span></div>{invitation.state === 'PENDING' && <button className="button button--danger" onClick={() => void revokeInvitation(invitation.id).then(load).catch(onError)}>Revoke</button>}</article>)}</section>}</div>
}
