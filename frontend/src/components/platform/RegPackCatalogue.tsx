import type { RegPackSummary } from '../../types/regflow'

interface Props {
  packs: RegPackSummary[]
  connected: boolean | null
  onPrepare: (pack: RegPackSummary) => void
}

export function RegPackCatalogue({ packs, connected, onPrepare }: Props) {
  return (
    <div className="platform-page">
      <section className="page-hero page-hero--compact">
        <p className="eyebrow">RegPack catalogue</p>
        <h1>Versioned regulatory definitions, ready for controlled workflows.</h1>
        <p>Each RegPack connects canonical fields, deterministic rules, reconciliation, regulatory sources, and configured output without regulator-specific application branches.</p>
      </section>
      {connected === false && <div className="notice notice--blocking">The API is unavailable. Start the local platform to load RegPacks.</div>}
      {connected !== false && packs.length === 0 && <div className="loading-panel" role="status">Loading available RegPacks…</div>}
      <section className="catalogue-grid" aria-label="Available RegPacks">
        {packs.map((pack) => (
          <article className="catalogue-card" key={pack.id}>
            <div className="catalogue-card__top"><span className="regulator-monogram">{pack.regulator.code}</span><span className="badge badge--verified">Available</span></div>
            <span className="catalogue-regulator">{pack.regulator.name}</span>
            <h2>{pack.name}</h2>
            <dl>
              <div><dt>Versions</dt><dd>{pack.versions.join(', ')}</dd></div>
              <div><dt>Preflight</dt><dd>{pack.workflow_versions.length} version{pack.workflow_versions.length === 1 ? '' : 's'}</dd></div>
              <div><dt>Output</dt><dd>{pack.output_versions.length ? `${pack.output_versions.length} configured` : 'Not configured'}</dd></div>
            </dl>
            <button className="button button--primary" type="button" disabled={!pack.workflow_versions.length} onClick={() => onPrepare(pack)}>Prepare this return</button>
          </article>
        ))}
      </section>
      <div className="responsibility-note"><strong>RegPack scope:</strong> A RegPack provides a traceable technical workflow. It does not determine legal compliance, replace regulatory advice, or submit to a government portal.</div>
    </div>
  )
}
