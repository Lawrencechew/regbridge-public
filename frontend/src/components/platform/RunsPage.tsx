import { useEffect, useState } from 'react'

import {
  deleteMappingProfile, deleteRun, getMappingProfiles, getRun, getRuns,
} from '../../services/api'
import type { MappingProfileSummary, RunDetail, RunSummary } from '../../types/regflow'

interface Props {
  onResume: (run: RunDetail) => void
  onError: (error: unknown) => void
}

function short(value: string | null, length = 10) {
  return value ? `${value.slice(0, length)}…` : '—'
}

function when(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

export function RunsPage({ onResume, onError }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [profiles, setProfiles] = useState<MappingProfileSummary[]>([])
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [loading, setLoading] = useState(true)

  function reload(signal?: AbortSignal) {
    setLoading(true)
    Promise.all([getRuns(signal), getMappingProfiles(signal)])
      .then(([nextRuns, nextProfiles]) => { setRuns(nextRuns); setProfiles(nextProfiles) })
      .catch(onError)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([getRuns(controller.signal), getMappingProfiles(controller.signal)])
      .then(([nextRuns, nextProfiles]) => { setRuns(nextRuns); setProfiles(nextProfiles) })
      .catch(onError)
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [onError])

  async function inspectRun(runId: string) {
    try { setDetail(await getRun(runId)) } catch (error) { onError(error) }
  }

  async function removeRun(run: RunSummary) {
    if (!window.confirm(`Delete retained metadata for ${run.source_display_name ?? 'this run'}? Uploaded files and workbook bytes were never retained.`)) return
    try { await deleteRun(run.id); if (detail?.id === run.id) setDetail(null); reload() } catch (error) { onError(error) }
  }

  async function removeProfile(profile: MappingProfileSummary) {
    if (!window.confirm(`Delete all versions of “${profile.display_name ?? 'Saved mapping'}”? Historical run mapping snapshots remain.`)) return
    try { await deleteMappingProfile(profile.profile_id); reload() } catch (error) { onError(error) }
  }

  return (
    <div className="platform-page runs-page">
      <section className="page-hero page-hero--compact"><p className="eyebrow">Local workspace history</p><h1>Runs</h1><p>Review privacy-minimal workflow metadata, resume a run by re-uploading its source, and manage saved mappings.</p></section>
      {loading && <div className="loading-panel">Loading persisted workspace metadata…</div>}
      {!loading && runs.length === 0 && <section className="help-card"><h2>No runs yet</h2><p>Runs are created only when you commit to a selected RegPack.</p></section>}
      {runs.length > 0 && <section className="history-section"><div className="section-heading"><div><h2>Recent runs</h2><p>Newest updates first. Hashes are abbreviated by default.</p></div></div><div className="table-scroll"><table><thead><tr><th>Updated</th><th>RegPack</th><th>Source</th><th>State</th><th>Blocking</th><th>Review</th><th>Output</th><th>Actions</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id}><td>{when(run.updated_at)}</td><td>{run.pack.id}<small className="table-note">v{run.pack.version}</small></td><td>{run.source_display_name ?? 'Awaiting upload'}</td><td><span className="badge badge--state">{run.state.replaceAll('_', ' ')}</span></td><td>{run.blocking_count}</td><td>{run.review_count}</td><td>{run.output_generated ? 'Generated' : '—'}</td><td><div className="actions"><button className="button button--quiet" onClick={() => void inspectRun(run.id)}>Details</button><button className="button button--secondary" onClick={() => void getRun(run.id).then(onResume).catch(onError)}>Resume</button><button className="button button--danger" onClick={() => void removeRun(run)}>Delete</button></div></td></tr>)}</tbody></table></div></section>}

      {detail && <section className="run-detail"><div className="section-heading"><div><p className="eyebrow">Run {short(detail.id, 8)}</p><h2>{detail.source.display_name ?? 'Awaiting source upload'}</h2><p>{detail.pack.id} v{detail.pack.version} · revision {detail.revision}</p></div><button className="button button--primary" onClick={() => onResume(detail)}>Resume run</button></div><div className="run-detail-grid"><div><span>State</span><strong>{detail.state.replaceAll('_', ' ')}</strong></div><div><span>Updated</span><strong>{when(detail.updated_at)}</strong></div><div><span>File SHA-256</span><code>{short(detail.source.sha256)}</code></div><div><span>Structure</span><code>{short(detail.source.header_signature)}</code></div><div><span>Mapping</span><code>{short(detail.mapping.fingerprint)}</code></div><div><span>Dataset</span><code>{short(detail.preflight.dataset_fingerprint)}</code></div></div>{detail.preflight.snapshot_id && <div className="notice notice--review"><strong>Previous preflight summary</strong><span>{detail.preflight.blocking_count} blocking · {detail.preflight.review_count} review · {detail.preflight.passed_count} passed. Detailed findings are not retained; re-upload and rerun preflight to view them.</span></div>}{detail.artifact && <div className="notice notice--success"><strong>Output generated previously: {detail.artifact.filename}</strong><span>RegBridge retains output metadata but not workbook bytes. Re-upload the source to regenerate and download it.</span></div>}<h3>Activity</h3><ol className="activity-list">{detail.audit_events.map((event) => <li key={event.id}><strong>{event.event_type.replaceAll('_', ' ')}</strong><span>{when(event.occurred_at)} · revision {event.run_revision}</span></li>)}</ol></section>}

      <section className="history-section"><div className="section-heading"><div><h2>Saved mappings</h2><p>Only exact RegPack, schema, fingerprint, and source-layout matches are offered.</p></div></div>{profiles.length === 0 ? <p className="muted">No reusable mapping profiles saved.</p> : <div className="profile-grid">{profiles.map((profile) => <article key={profile.profile_id}><div><strong>{profile.display_name ?? 'Saved mapping'}</strong><span>{profile.pack.id} v{profile.pack.version} · profile v{profile.latest_version}</span><code>{short(profile.source_header_signature)}</code></div><button className="button button--danger" onClick={() => void removeProfile(profile)}>Delete</button></article>)}</div>}</section>
    </div>
  )
}
