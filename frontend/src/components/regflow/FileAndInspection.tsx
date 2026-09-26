import type { ImportLimits, SourceFileInspection } from '../../types/regflow'
import { sourceColumnLabel } from '../../regflow/presentation'

interface Props {
  file: File | null
  inspection: SourceFileInspection | null
  limits: ImportLimits | null
  sheetName: string | null
  headerRow: number
  loading: boolean
  onFile: (file: File) => void
  onRemove: () => void
  onOptions: (sheet: string | null, headerRow: number) => void
  onContinue: () => void
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  try { return JSON.stringify(value) } catch { return 'Unsupported value' }
}

export function FileAndInspection({
  file,
  inspection,
  limits,
  sheetName,
  headerRow,
  loading,
  onFile,
  onRemove,
  onOptions,
  onContinue,
}: Props) {
  return (
    <section className="workflow-card" aria-labelledby="upload-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Step 2</p>
          <h2 id="upload-heading">Upload and inspect your source</h2>
          <p>XLSX or CSV · Maximum {limits ? `${Math.round(limits.max_file_size_bytes / 1024 / 1024)} MB` : 'configured by the API'}</p>
        </div>
      </div>

      {!file ? (
        <label className="upload-zone">
          <strong>Choose a source file</strong>
          <span>RegBridge processes it transiently and does not save it.</span>
          <input
            type="file"
            accept=".csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
            onChange={(event) => {
              const selected = event.target.files?.[0]
              if (selected) onFile(selected)
            }}
          />
        </label>
      ) : (
        <>
          <div className="selected-file">
            <div><strong>{file.name}</strong><span>{(file.size / 1024).toFixed(1)} KB · {file.type || 'File type determined by API'}</span></div>
            <button className="button button--quiet" type="button" onClick={onRemove}>Choose another file</button>
          </div>
          {loading && <div className="loading-panel" role="status">Inspecting source file…</div>}
          {inspection && (
            <>
              <div className="inspection-grid">
                <div><span>Source type</span><strong>{inspection.source_type.toUpperCase()}</strong></div>
                <div><span>Rows</span><strong>{inspection.data_row_count ?? 'Select a sheet'}</strong></div>
                <div><span>Columns</span><strong>{inspection.columns.length}</strong></div>
                <div><span>Fingerprint</span><strong title={inspection.file_sha256}>{inspection.file_sha256.slice(0, 12)}…</strong></div>
              </div>

              <div className="inspection-controls">
                {inspection.sheets.length > 1 && (
                  <label>
                    Worksheet
                    <select value={sheetName ?? ''} onChange={(event) => onOptions(event.target.value || null, headerRow)}>
                      <option value="">Choose a worksheet</option>
                      {inspection.sheets.filter((sheet) => sheet.visibility === 'visible').map((sheet) => (
                        <option key={sheet.name} value={sheet.name}>{sheet.name}</option>
                      ))}
                    </select>
                  </label>
                )}
                <label>
                  Header row
                  <input
                    type="number"
                    min={limits?.min_header_row ?? 1}
                    max={limits?.max_header_row ?? 50}
                    value={headerRow}
                    onChange={(event) => onOptions(sheetName, Number(event.target.value))}
                  />
                </label>
              </div>

              {inspection.formula_cells_detected && (
                <div className="notice notice--review">
                  <strong>Formula cells were detected.</strong>
                  <span>RegBridge does not evaluate customer formulas. A formula blocks import only when its column is mapped.</span>
                </div>
              )}

              {!inspection.selection_required && inspection.columns.length > 0 && (
                <div className="table-scroll preview-table">
                  <table>
                    <thead><tr><th>Source row</th>{inspection.columns.map((column) => <th key={column.index}>{sourceColumnLabel(column)}</th>)}</tr></thead>
                    <tbody>
                      {inspection.preview_rows.map((row) => (
                        <tr key={row.source_row}><th>{row.source_row}</th>{row.values.map((value, index) => <td key={`${row.source_row}-${inspection.columns[index]?.index ?? index}`}>{displayValue(value)}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="actions actions--end">
                <button className="button button--primary" type="button" disabled={inspection.selection_required || inspection.columns.length === 0} onClick={onContinue}>
                  Continue to Mapping
                </button>
              </div>
            </>
          )}
        </>
      )}
    </section>
  )
}
