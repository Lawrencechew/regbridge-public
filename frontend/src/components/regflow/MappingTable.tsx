import type {
  CanonicalField,
  CanonicalSchema,
  ImportResult,
  MappingProfileVersion,
  MappingDraft,
  MappingDrafts,
  SourceFileInspection,
} from '../../types/regflow'
import { mappingRecommendationSummary, requiredMappingsComplete } from '../../regflow/workflow'
import { sourceColumnLabel } from '../../regflow/presentation'

interface Props {
  schema: CanonicalSchema
  inspection: SourceFileInspection
  drafts: MappingDrafts
  result: ImportResult | null
  loading: 'map' | 'preflight' | null
  onChange: (fieldId: string, draft: MappingDraft) => void
  onApplyRecommendations: () => void
  matchedProfiles: MappingProfileVersion[]
  appliedProfile: MappingProfileVersion | null
  saveMappingProfile: boolean
  onApplySavedProfile: (profile: MappingProfileVersion) => void
  onSaveMappingProfile: (value: boolean) => void
  onCheck: () => void
  onPreflight: () => void
  onBack: () => void
}

function MatchBadge({ draft, required }: { draft: MappingDraft; required: boolean }) {
  if (draft.matchKind === 'exact') return <span className="badge badge--match-exact">Exact match</span>
  if (draft.matchKind === 'alias') return <span className="badge badge--match-alias">Approved alias</span>
  if (draft.matchKind === 'manual') return <span className="badge badge--match-manual">Manual choice</span>
  return required
    ? <span className="badge badge--blocking">Needs input</span>
    : <span className="muted">Not suggested</span>
}

function ConversionControl({ field, draft, update }: {
  field: CanonicalField
  draft: MappingDraft
  update: (changes: Partial<MappingDraft>) => void
}) {
  if (draft.sourceColumnIndex === null) return <span className="muted">Select a source column</span>
  if (field.data_type === 'string') {
    return <label className="inline-check"><input type="checkbox" checked={draft.trimWhitespace} onChange={(event) => update({ trimWhitespace: event.target.checked })} /> Trim whitespace</label>
  }
  if (field.data_type === 'decimal') {
    return (
      <div className="compact-inputs">
        <label>Decimal <input aria-label={`${field.name} decimal separator`} maxLength={1} value={draft.decimalSeparator} onChange={(event) => update({ decimalSeparator: event.target.value })} /></label>
        <label>Thousands <input aria-label={`${field.name} thousands separator`} maxLength={1} placeholder="None" value={draft.thousandsSeparator} onChange={(event) => update({ thousandsSeparator: event.target.value })} /></label>
      </div>
    )
  }
  if (field.data_type === 'boolean') {
    return (
      <div className="compact-inputs compact-inputs--wide">
        <label>True values <input value={draft.trueValues} onChange={(event) => update({ trueValues: event.target.value })} /></label>
        <label>False values <input value={draft.falseValues} onChange={(event) => update({ falseValues: event.target.value })} /></label>
        <label className="inline-check"><input type="checkbox" checked={draft.caseSensitive} onChange={(event) => update({ caseSensitive: event.target.checked })} /> Case sensitive</label>
      </div>
    )
  }
  if (field.data_type === 'date' || field.data_type === 'datetime') {
    const value = field.data_type === 'date' ? draft.dateFormat : draft.datetimeFormat
    const updateKey = field.data_type === 'date' ? 'dateFormat' : 'datetimeFormat'
    const options = field.data_type === 'date'
      ? [['%d/%m/%Y', 'DD/MM/YYYY'], ['%Y-%m-%d', 'YYYY-MM-DD'], ['%m/%d/%Y', 'MM/DD/YYYY']]
      : [['%d/%m/%Y %H:%M', 'DD/MM/YYYY HH:mm'], ['%Y-%m-%d %H:%M:%S', 'YYYY-MM-DD HH:mm:ss'], ['%m/%d/%Y %H:%M', 'MM/DD/YYYY HH:mm']]
    return (
      <label>
        Explicit format
        <select value={value} onChange={(event) => update({ [updateKey]: event.target.value })}>
          {options.map(([format, label]) => <option key={format} value={format}>{label}</option>)}
        </select>
      </label>
    )
  }
  return <span className="muted">Standard integer conversion</span>
}

function IssueList({ result }: { result: ImportResult }) {
  if (result.success) return (
    <div className="notice notice--success">
      <strong>Source mapped successfully</strong>
      <span>{result.dataset_summary?.record_count.toLocaleString()} records understood · {result.dataset_summary?.schema_id}</span>
    </div>
  )
  return (
    <div className="issue-panel" role="alert">
      <h3>Blocking source data issues</h3>
      <p>Correct the mapping, or update the source file and upload it again.</p>
      {result.issues.map((issue, index) => (
        <article key={`${issue.code}-${index}`} className="issue-card">
          <span className="badge badge--blocking">Import issue</span>
          <strong>{issue.message}</strong>
          {issue.source && <small>{[issue.source.sheet, issue.source.row ? `Row ${issue.source.row}` : null, issue.source.column].filter(Boolean).join(' · ')}</small>}
        </article>
      ))}
    </div>
  )
}

export function MappingTable({ schema, inspection, drafts, result, loading, onChange, onApplyRecommendations, matchedProfiles, appliedProfile, saveMappingProfile, onApplySavedProfile, onSaveMappingProfile, onCheck, onPreflight, onBack }: Props) {
  const selected = new Set(Object.values(drafts).map((draft) => draft.sourceColumnIndex).filter((value) => value !== null))
  const requiredReady = requiredMappingsComplete(schema, drafts)
  const mappedCount = Object.values(drafts).filter((draft) => draft.sourceColumnIndex !== null).length
  const recommendation = mappingRecommendationSummary(schema, drafts)
  const recommendedCount = recommendation.exact + recommendation.aliases

  return (
    <section className="workflow-card workflow-card--wide" aria-labelledby="map-heading">
      <div className="section-heading">
        <div><p className="eyebrow">Step 3</p><h2 id="map-heading">Review recommended mappings</h2><p>RegBridge matched safe headers for you. Verify the recommendations and only adjust fields that need attention.</p></div>
        <span className="mapping-count">{mappedCount} of {schema.fields.length} mapped</span>
      </div>
      <div className={`recommendation-panel ${recommendation.unresolvedRequired ? 'recommendation-panel--attention' : ''}`} aria-live="polite">
        <div>
          <strong>{recommendedCount > 0 ? `${recommendedCount} mappings recommended` : 'No safe mappings recommended'}</strong>
          <span>{recommendation.exact} exact · {recommendation.aliases} approved alias · {recommendation.manual} manual · {recommendation.unresolvedRequired} required unresolved</span>
        </div>
        <button className="button button--quiet" type="button" disabled={loading !== null} onClick={onApplyRecommendations}>Restore recommendations</button>
      </div>
      {matchedProfiles.length > 0 && <div className="saved-mapping-panel"><div><strong>Saved mapping available</strong><span>{matchedProfiles[0].display_name ?? 'Saved mapping'} · version {matchedProfiles[0].profile_version} · confirmed {new Date(matchedProfiles[0].confirmed_at).toLocaleDateString()}</span><small>Applying fills the table only. You must still confirm and check the mapping.</small></div><button className="button button--secondary" type="button" onClick={() => onApplySavedProfile(matchedProfiles[0])}>Apply saved mapping</button></div>}
      {appliedProfile && <div className="notice notice--success"><strong>Saved mapping applied for review</strong><span>Profile version {appliedProfile.profile_version} is filling the table. No preflight has run.</span></div>}
      <div className="table-scroll mapping-table">
        <table>
          <thead><tr><th>RegPack field</th><th>Required</th><th>Type</th><th>Recommended source</th><th>Match</th><th>Conversion</th></tr></thead>
          <tbody>
            {schema.fields.map((field) => {
              const draft = drafts[field.id]
              return (
                <tr key={field.id}>
                  <th><strong>{field.name}</strong>{field.description && <small>{field.description}</small>}</th>
                  <td>{field.required ? <span className="badge badge--required">Required</span> : <span className="muted">Optional</span>}</td>
                  <td><code>{field.data_type}</code></td>
                  <td>
                    <select
                      aria-label={`Source column for ${field.name}`}
                      value={draft.sourceColumnIndex ?? ''}
                      onChange={(event) => onChange(field.id, {
                        ...draft,
                        sourceColumnIndex: event.target.value ? Number(event.target.value) : null,
                        matchKind: event.target.value ? 'manual' : null,
                      })}
                    >
                      <option value="">Not mapped</option>
                      {inspection.columns.map((column) => (
                        <option key={column.index} value={column.index} disabled={selected.has(column.index) && draft.sourceColumnIndex !== column.index}>
                          {sourceColumnLabel(column)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td><MatchBadge draft={draft} required={field.required} /></td>
                  <td><ConversionControl field={field} draft={draft} update={(changes) => onChange(field.id, { ...draft, ...changes })} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {!requiredReady && <div className="notice notice--blocking">Map every required RegPack field before checking the mapping.</div>}
      {requiredReady && !result && <div className="notice notice--success"><strong>Required mappings are ready for review</strong><span>Check the recommended source columns above, then confirm them with the mapping check.</span></div>}
      {result && <IssueList result={result} />}
      <label className="save-mapping-choice"><input type="checkbox" checked={saveMappingProfile} onChange={(event) => onSaveMappingProfile(event.target.checked)} /> <span><strong>Save this mapping for future files with the same layout</strong><small>Unchecked by default. Saving creates a versioned profile after backend verification.</small></span></label>
      <div className="actions actions--between">
        <button className="button button--quiet" type="button" onClick={onBack}>Back to Upload</button>
        <div className="actions">
          <button className="button button--secondary" type="button" disabled={!requiredReady || loading !== null} onClick={onCheck}>
            {loading === 'map' ? 'Checking mapping…' : 'Confirm & Check Mapping'}
          </button>
          <button className="button button--primary" type="button" disabled={!result?.success || loading !== null} onClick={onPreflight}>
            {loading === 'preflight' ? 'Running preflight…' : 'Run Preflight'}
          </button>
        </div>
      </div>
    </section>
  )
}
