import type { RegPackDetail, RegPackSummary } from '../../types/regflow'

interface Props {
  packs: RegPackSummary[]
  selected: RegPackSummary | null
  version: string
  detail: RegPackDetail | null
  loading: boolean
  onSelect: (pack: RegPackSummary) => void
  onVersion: (version: string) => void
  onContinue: () => void
}

export function PackSelector({
  packs,
  selected,
  version,
  detail,
  loading,
  onSelect,
  onVersion,
  onContinue,
}: Props) {
  return (
    <section className="workflow-card" aria-labelledby="select-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Step 1</p>
          <h2 id="select-heading">Choose a RegPack</h2>
          <p>Select the regulatory definition and version for this RegFlow.</p>
        </div>
        <span className="release-chip">Local / internal MVP</span>
      </div>

      <div className="pack-grid">
        {packs.map((pack) => (
          <button
            type="button"
            key={pack.id}
            className={`pack-card ${selected?.id === pack.id ? 'selected' : ''}`}
            onClick={() => onSelect(pack)}
          >
            <span>{pack.regulator.name}</span>
            <strong>{pack.name}</strong>
            <small>{pack.versions.length} available version{pack.versions.length === 1 ? '' : 's'}</small>
          </button>
        ))}
      </div>

      {selected && (
        <div className="pack-selection-panel">
          <label>
            RegPack version
            <select value={version} onChange={(event) => onVersion(event.target.value)}>
              <option value="">Choose a version</option>
              {selected.versions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          {loading && <p className="loading-text" role="status">Loading RegPack details…</p>}
          {detail && (
            <div className="pack-detail">
              <div className="detail-line">
                <span className={`badge badge--${detail.status ?? 'draft'}`}>{detail.status ?? 'Unspecified'}</span>
                <span>{detail.reporting?.frequency ?? 'Reporting frequency not specified'}</span>
                <span>{detail.output_type ? 'Output configured' : 'Output not configured'}</span>
              </div>
              <p>{detail.description}</p>
              <details>
                <summary>View RegPack details and regulatory sources</summary>
                <ul className="source-list">
                  {detail.sources.map((source) => (
                    <li key={source.id}>
                      <a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>
                      <span>{source.publisher}{source.reference ? ` · ${source.reference}` : ''}</span>
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          )}
          <div className="actions actions--end">
            <button className="button button--primary" type="button" disabled={!detail || loading} onClick={onContinue}>
              Continue to Upload
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
