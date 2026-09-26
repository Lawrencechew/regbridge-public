import { useState } from 'react'

import type {
  ReconciliationFinding,
  RegFlowPreflightResult,
  RegPackDetail,
  Severity,
  ValidationFinding,
} from '../../types/regflow'

type Filter = 'all' | Severity

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Blank'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  try { return JSON.stringify(value) } catch { return 'Unavailable' }
}

function Evidence({ refs, detail }: { refs: string[]; detail: RegPackDetail }) {
  if (!refs.length) return null
  const sources = refs.map((id) => detail.sources.find((source) => source.id === id)).filter((source) => source !== undefined)
  return (
    <details className="evidence">
      <summary>Why is this checked?</summary>
      {sources.map((source) => <p key={source.id}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a><span>{source.publisher}</span></p>)}
    </details>
  )
}

function ValidationCard({ finding, detail }: { finding: ValidationFinding; detail: RegPackDetail }) {
  return (
    <article className="finding-card">
      <div className="finding-title"><span className={`badge badge--${finding.severity}`}>{finding.severity}</span><strong>{finding.rule_name}</strong></div>
      <p>{finding.message}</p>
      {finding.source && <small>{[finding.source.sheet, finding.source.row ? `Row ${finding.source.row}` : null, finding.source.column].filter(Boolean).join(' · ')}</small>}
      <dl><div><dt>Expected</dt><dd>{valueText(finding.expected)}</dd></div><div><dt>Actual</dt><dd>{valueText(finding.actual)}</dd></div></dl>
      <Evidence refs={finding.source_refs} detail={detail} />
      <details className="technical"><summary>Technical details</summary><code>{finding.rule_id}</code></details>
    </article>
  )
}

function ReconciliationCard({ finding, detail }: { finding: ReconciliationFinding; detail: RegPackDetail }) {
  const source = finding.source_values.find((item) => item.source)?.source
  return (
    <article className="finding-card">
      <div className="finding-title"><span className={`badge badge--${finding.severity}`}>{finding.severity}</span><strong>{finding.rule_name}</strong></div>
      <p>{finding.message}</p>
      {source && <small>{[source.sheet, source.row ? `Row ${source.row}` : null, source.column].filter(Boolean).join(' · ')}</small>}
      <dl><div><dt>Expected closing</dt><dd>{finding.expected}</dd></div><div><dt>Actual closing</dt><dd>{finding.actual}</dd></div><div><dt>Difference</dt><dd>{finding.difference}</dd></div><div><dt>Tolerance</dt><dd>{finding.tolerance}</dd></div></dl>
      {finding.group && <p className="group-context">Group: {valueText(finding.group)}</p>}
      <Evidence refs={finding.source_refs} detail={detail} />
      <details className="technical"><summary>Technical details</summary><code>{finding.rule_id}</code></details>
    </article>
  )
}

interface Props {
  result: RegFlowPreflightResult
  detail: RegPackDetail
  generating: boolean
  onGenerate: () => void
  onRunAgain: () => void
  onBack: () => void
}

export function PreflightPanel({ result, detail, generating, onGenerate, onRunAgain, onBack }: Props) {
  const [filter, setFilter] = useState<Filter>('all')
  const validation = (result.validation?.findings ?? []).filter((item) => filter === 'all' || item.severity === filter)
  const reconciliation = (result.reconciliation?.findings ?? []).filter((item) => filter === 'all' || item.severity === filter)
  const truncated = Boolean(result.validation?.findings_truncated || result.reconciliation?.findings_truncated)
  const totalFindings = (result.validation?.total_findings ?? 0) + (result.reconciliation?.total_findings ?? 0)
  const returnedFindings = (result.validation?.returned_findings ?? 0) + (result.reconciliation?.returned_findings ?? 0)

  return (
    <section className="workflow-card" aria-labelledby="preflight-heading">
      <div className="section-heading">
        <div><p className="eyebrow">Step 4</p><h2 id="preflight-heading">RegFlow preflight result</h2><p>Configured data and reconciliation checks for this RegPack.</p></div>
        <span className={`readiness readiness--${result.ready ? 'ready' : 'blocked'}`}>{result.ready ? 'Ready to generate' : 'Not ready to generate'}</span>
      </div>
      <div className="summary-grid">
        <div className="metric metric--blocking"><strong>{result.blocking_findings}</strong><span>Blocking</span></div>
        <div className="metric metric--review"><strong>{result.review_findings}</strong><span>Review</span></div>
        <div className="metric metric--passed"><strong>{result.passed_checks}</strong><span>Passed</span></div>
      </div>
      {result.blocking_findings > 0 && <div className="notice notice--blocking"><strong>Resolve blocking issues before generating output.</strong><span>Update the source file or mapping, then run preflight again.</span></div>}
      {result.blocking_findings === 0 && result.review_findings > 0 && <div className="notice notice--review"><strong>{result.review_findings} review item{result.review_findings === 1 ? '' : 's'} remain.</strong><span>You may generate output, but review these items before submission.</span></div>}
      {result.blocking_findings === 0 && result.review_findings === 0 && <div className="notice notice--success"><strong>Preflight passed</strong><span>All configured RegPack checks passed. The output is ready to generate.</span></div>}
      {!result.pack.output_configured && <div className="notice notice--review">Preflight is supported, but output generation is not configured for this RegPack.</div>}
      {truncated && <div className="notice notice--review">Showing the first {returnedFindings.toLocaleString()} of {totalFindings.toLocaleString()} findings. Fix the underlying issue and run preflight again.</div>}
      {result.import_issues.length > 0 && (
        <div className="issue-panel">
          <h3>Source data issues</h3>
          {result.import_issues.map((issue, index) => <article className="issue-card" key={`${issue.code}-${index}`}><span className="badge badge--blocking">Import issue</span><strong>{issue.message}</strong></article>)}
        </div>
      )}

      <div className="finding-toolbar" aria-label="Filter findings">
        {(['all', 'blocking', 'review'] as const).map((item) => <button key={item} type="button" className={filter === item ? 'active' : ''} onClick={() => setFilter(item)}>{item}</button>)}
      </div>
      <div className="findings-section"><h3>Data checks</h3>{validation.length ? validation.map((finding) => <ValidationCard key={`${finding.rule_id}-${finding.record_id ?? ''}`} finding={finding} detail={detail} />) : <p className="empty-findings">No data findings in this filter.</p>}</div>
      <div className="findings-section"><h3>Reconciliation checks</h3>{reconciliation.length ? reconciliation.map((finding) => <ReconciliationCard key={`${finding.rule_id}-${finding.record_id ?? ''}`} finding={finding} detail={detail} />) : <p className="empty-findings">No reconciliation findings in this filter.</p>}</div>

      <details className="technical technical-panel"><summary>Technical details</summary><dl><div><dt>RegPack</dt><dd>{result.pack.id} · {result.pack.version}</dd></div><div><dt>Pack fingerprint</dt><dd>{result.pack.fingerprint.slice(0, 16)}…</dd></div><div><dt>Dataset fingerprint</dt><dd>{result.dataset_fingerprint?.slice(0, 16)}…</dd></div><div><dt>Mapping fingerprint</dt><dd>{result.mapping_fingerprint.slice(0, 16)}…</dd></div></dl></details>
      <div className="responsibility-note">RegBridge prepares output using configured RegPack checks. Review the generated file before submitting it; final submission responsibility remains with the submitter.</div>
      <div className="actions actions--between">
        <button className="button button--quiet" type="button" onClick={onBack}>Edit Mapping</button>
        <div className="actions"><button className="button button--secondary" type="button" disabled={generating} onClick={onRunAgain}>Run Preflight Again</button><button className="button button--primary" type="button" disabled={!result.can_generate || generating} onClick={onGenerate}>{generating ? 'Generating output…' : 'Generate Output'}</button></div>
      </div>
    </section>
  )
}
