import type { GeneratedFile, RegFlowPreflightResult, RegPackDetail } from '../../types/regflow'

interface Props {
  generated: GeneratedFile
  preflight: RegFlowPreflightResult
  detail: RegPackDetail
  onDownload: () => void
  onStartNew: () => void
}

export function CompletionPanel({ generated, preflight, detail, onDownload, onStartNew }: Props) {
  return (
    <section className="workflow-card completion" aria-labelledby="complete-heading">
      <div className="completion-mark" aria-hidden="true">✓</div>
      <p className="eyebrow">RegFlow complete</p>
      <h2 id="complete-heading">Output generated</h2>
      <p>Your file remains in browser memory for this page only.</p>
      <dl className="completion-details">
        <div><dt>RegPack</dt><dd>{detail.name} · {detail.version}</dd></div>
        <div><dt>Source records</dt><dd>{preflight.dataset_summary?.record_count ?? 0}</dd></div>
        <div><dt>Output</dt><dd>{generated.filename}</dd></div>
      </dl>
      <div className="responsibility-note">Review the generated file before submitting it to the regulator. RegBridge does not submit it automatically.</div>
      <div className="actions actions--center"><button className="button button--primary" type="button" onClick={onDownload}>Download again</button><button className="button button--secondary" type="button" onClick={onStartNew}>Start new RegFlow</button></div>
    </section>
  )
}
