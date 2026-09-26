import type { RegPackSummary } from '../../types/regflow'

interface Props {
  packs: RegPackSummary[]
  connected: boolean | null
  onStart: () => void
  onBrowsePacks: () => void
}

export function HomePage({ packs, connected, onStart, onBrowsePacks }: Props) {
  const workflowCount = packs.reduce((total, pack) => total + pack.workflow_versions.length, 0)
  const outputCount = packs.reduce((total, pack) => total + pack.output_versions.length, 0)

  return (
    <div className="platform-page home-page">
      <section className="home-hero">
        <div className="home-hero__copy">
          <p className="eyebrow">Regulatory last mile, made reviewable</p>
          <h1>Turn operational data into submission-ready regulatory output.</h1>
          <p>RegBridge guides your team from source file to deterministic preflight and regulator-prescribed output—without replacing human accountability.</p>
          <div className="actions home-actions">
            <button className="button button--primary button--large" type="button" onClick={onStart}>Start preparing a return</button>
            <button className="button button--secondary button--large" type="button" onClick={onBrowsePacks}>Explore RegPacks</button>
          </div>
          <div className="trust-line"><span className={`status-dot status-dot--${connected === null ? 'checking' : connected ? 'connected' : 'unavailable'}`} /><span>{connected === null ? 'Checking the local platform' : connected ? 'Local platform ready' : 'Local API needs attention'}</span><span>Files processed transiently</span></div>
        </div>
        <aside className="home-hero__panel" aria-label="RegFlow overview">
          <span className="panel-kicker">One controlled workflow</span>
          <ol>
            <li><span>01</span><div><strong>Select</strong><small>Choose a versioned RegPack</small></div></li>
            <li><span>02</span><div><strong>Prepare</strong><small>Inspect and review recommended mappings</small></div></li>
            <li><span>03</span><div><strong>Preflight</strong><small>Resolve deterministic findings</small></div></li>
            <li><span>04</span><div><strong>Generate</strong><small>Download prescribed output</small></div></li>
          </ol>
        </aside>
      </section>

      <section className="platform-metrics" aria-label="Platform availability">
        <div><strong>{packs.length}</strong><span>RegPack{packs.length === 1 ? '' : 's'} available</span></div>
        <div><strong>{workflowCount}</strong><span>Executable version{workflowCount === 1 ? '' : 's'}</span></div>
        <div><strong>{outputCount}</strong><span>Output definition{outputCount === 1 ? '' : 's'}</span></div>
        <div><strong>0</strong><span>Files retained after request</span></div>
      </section>

      <section className="home-section">
        <div className="section-heading home-section__heading"><div><p className="eyebrow">What RegBridge does</p><h2>A clearer path from source data to regulatory review.</h2></div><p>Every important transformation stays visible and deterministic, so users verify recommendations instead of trusting a black box.</p></div>
        <div className="capability-grid">
          <article><span>01</span><h3>Understand the source</h3><p>Inspect CSV or XLSX structure, worksheets, headers, formulas, and preview rows before processing.</p></article>
          <article><span>02</span><h3>Recommend safe mappings</h3><p>Preselect exact and RegPack-approved aliases. Ambiguous columns remain clearly unresolved.</p></article>
          <article><span>03</span><h3>Run deterministic preflight</h3><p>Present validation and reconciliation findings with source rows, evidence, and rule identifiers.</p></article>
          <article><span>04</span><h3>Generate trusted output</h3><p>Revalidate server-side and populate the regulator-prescribed workbook only when blockers are cleared.</p></article>
        </div>
      </section>

      <section className="home-cta">
        <div><p className="eyebrow">Ready to begin?</p><h2>Prepare your next return with a reviewable RegFlow.</h2><p>Workflow metadata and confirmed mappings persist; source rows and generated workbook bytes do not.</p></div>
        <button className="button button--primary button--large" type="button" onClick={onStart}>Start a RegFlow</button>
      </section>
    </div>
  )
}
