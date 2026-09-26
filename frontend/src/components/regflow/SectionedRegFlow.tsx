import { useMemo, useState } from 'react'

import {
  buildImportMapping,
  createMappingDrafts,
  mappingDefinitionToDrafts,
  recommendMappingDrafts,
  requiredMappingsComplete,
} from '../../regflow/workflow'
import {
  downloadGeneratedFile,
  generateSectionedOutput,
  inspectSource,
  mapSectionedSource,
  matchMappingProfiles,
  runSectionedPreflight,
} from '../../services/api'
import type {
  GeneratedFile,
  ImportLimits,
  MappingDrafts,
  MappingProfileVersion,
  RegPackDetail,
  RegPackSummary,
  RegPackWorkflow,
  RunDetail,
  SourceFileInspection,
  WorkflowImportMapping,
  WorkflowImportResult,
  WorkflowPreflightResult,
} from '../../types/regflow'

interface SectionState {
  enabled: boolean
  sheetName: string | null
  headerRow: number
  inspection: SourceFileInspection | null
  drafts: MappingDrafts
  profiles: MappingProfileVersion[]
  appliedProfile: MappingProfileVersion | null
}

interface Props {
  pack: RegPackSummary
  version: string
  detail: RegPackDetail
  workflow: RegPackWorkflow
  run: RunDetail | null
  limits: ImportLimits | null
  onRunMutation: (state: RunDetail['state'], revision: number) => void
  onError: (error: unknown) => void
  onStartNew: () => void
}

function normalise(value: string): string[] {
  return value.toLocaleLowerCase('en').split(/[^a-z0-9]+/).filter((token) => token.length > 2 && !['record', 'value', 'total'].includes(token))
}

function recommendedSheet(sectionName: string, sheets: SourceFileInspection['sheets']): string | null {
  const terms = new Set(normalise(sectionName))
  const ranked = sheets
    .filter((sheet) => sheet.visibility === 'visible')
    .map((sheet) => ({ sheet, score: normalise(sheet.name).filter((term) => terms.has(term)).length }))
    .sort((a, b) => b.score - a.score)
  return ranked[0]?.score ? ranked[0].sheet.name : null
}

function initialSections(workflow: RegPackWorkflow, run: RunDetail | null): Record<string, SectionState> {
  return Object.fromEntries(workflow.sections.map((section) => {
    const saved = run?.workflow_sections.find((item) => item.section_id === section.id)
    return [section.id, {
      enabled: saved ? !saved.omitted : true,
      sheetName: saved?.source?.selected_sheet ?? null,
      headerRow: 1,
      inspection: null,
      drafts: saved?.mapping.definition
        ? mappingDefinitionToDrafts(section.schema, saved.mapping.definition)
        : createMappingDrafts(section.schema),
      profiles: [],
      appliedProfile: null,
    }]
  }))
}

export function SectionedRegFlow({ pack, version, detail, workflow, run, limits, onRunMutation, onError, onStartNew }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [overview, setOverview] = useState<SourceFileInspection | null>(null)
  const [sections, setSections] = useState<Record<string, SectionState>>(() => initialSections(workflow, run))
  const [runtime, setRuntime] = useState<Record<string, string>>(() => Object.fromEntries(workflow.runtime_fields.map((field) => [field.id, ''])))
  const [mappingResult, setMappingResult] = useState<WorkflowImportResult | null>(null)
  const [preflight, setPreflight] = useState<WorkflowPreflightResult | null>(null)
  const [generated, setGenerated] = useState<GeneratedFile | null>(null)
  const [loading, setLoading] = useState<string | null>(null)
  const [saveProfiles, setSaveProfiles] = useState(false)
  const [runRevision, setRunRevision] = useState(run?.revision ?? null)

  async function inspectSection(sectionId: string, selectedFile: File, sheetName: string, headerRow = 1) {
    const definition = workflow.sections.find((section) => section.id === sectionId)!
    const inspection = await inspectSource(selectedFile, sheetName, headerRow)
    const saved = run?.workflow_sections.find((item) => item.section_id === sectionId)?.mapping.definition
    const drafts = saved
      ? mappingDefinitionToDrafts(definition.schema, saved)
      : recommendMappingDrafts(definition.schema, inspection)
    const profiles = await matchMappingProfiles(
      pack.id, version, definition.schema.id, definition.schema.version,
      inspection.source_header_signature, undefined, sectionId,
    )
    setSections((current) => ({
      ...current,
      [sectionId]: { ...current[sectionId], sheetName, headerRow, inspection, drafts, profiles, appliedProfile: null },
    }))
  }

  async function chooseFile(selected: File) {
    setLoading('inspect')
    setFile(selected)
    setMappingResult(null)
    setPreflight(null)
    setGenerated(null)
    try {
      const inspected = await inspectSource(selected, null, 1)
      setOverview(inspected)
      await Promise.all(workflow.sections.map(async (section) => {
        const current = sections[section.id]
        if (!current.enabled) return
        const sheet = current.sheetName ?? recommendedSheet(section.name, inspected.sheets)
        if (sheet) await inspectSection(section.id, selected, sheet, current.headerRow)
      }))
    } catch (error) { onError(error) }
    finally { setLoading(null) }
  }

  function workflowMapping(): WorkflowImportMapping {
    return {
      sections: workflow.sections.map((definition) => {
        const state = sections[definition.id]
        return {
          section_id: definition.id,
          mapping: state.enabled && state.inspection
            ? buildImportMapping(definition.schema, state.drafts, state.sheetName, state.headerRow)
            : null,
        }
      }),
    }
  }

  const ready = useMemo(() => {
    const runtimeReady = workflow.runtime_fields.every((field) => !field.required || runtime[field.id]?.trim())
    const sectionsReady = workflow.sections.every((definition) => {
      const state = sections[definition.id]
      if (!state.enabled) return definition.optional
      return Boolean(state.inspection && requiredMappingsComplete(definition.schema, state.drafts))
    })
    return Boolean(file && runtimeReady && sectionsReady)
  }, [file, runtime, sections, workflow])

  async function checkMapping() {
    if (!file) return
    setLoading('map')
    try {
      setMappingResult(await mapSectionedSource(file, pack.id, version, workflowMapping()))
    } catch (error) { onError(error) }
    finally { setLoading(null) }
  }

  async function runPreflight() {
    if (!file) return
    setLoading('preflight')
    try {
      const origins = Object.fromEntries(workflow.sections.map((definition) => [
        definition.id,
        Object.fromEntries(Object.entries(sections[definition.id].drafts)
          .filter(([, draft]) => draft.matchKind)
          .map(([fieldId, draft]) => [fieldId, draft.matchKind!])),
      ]))
      const result = await runSectionedPreflight(
        file, pack.id, version, workflowMapping(), runtime, undefined,
        run && runRevision !== null ? {
          runId: run.id, expectedRevision: runRevision, saveProfiles, recommendationOrigins: origins,
        } : undefined,
      )
      setPreflight(result)
      if (result.run_revision !== null && result.run_state) {
        setRunRevision(result.run_revision)
        onRunMutation(result.run_state, result.run_revision)
      }
    } catch (error) { onError(error) }
    finally { setLoading(null) }
  }

  async function generate() {
    if (!file || !preflight?.can_generate) return
    setLoading('generate')
    try {
      const result = await generateSectionedOutput(
        file, pack.id, version, workflowMapping(), runtime, undefined,
        run && runRevision !== null ? {
          runId: run.id, expectedRevision: runRevision, idempotencyKey: crypto.randomUUID(),
        } : undefined,
      )
      setGenerated(result)
      if (result.runRevision !== null && result.runState) {
        setRunRevision(result.runRevision)
        onRunMutation(result.runState, result.runRevision)
      }
      downloadGeneratedFile(result)
    } catch (error) { onError(error) }
    finally { setLoading(null) }
  }

  if (generated) return (
    <section className="workflow-card">
      <p className="eyebrow">Complete</p><h2>Official workbook generated</h2>
      <p>{generated.filename} is ready. RegBridge retained metadata, not the workbook bytes or transient runtime values.</p>
      <div className="actions"><button className="button button--primary" onClick={() => downloadGeneratedFile(generated)}>Download again</button><button className="button button--quiet" onClick={onStartNew}>Start another run</button></div>
    </section>
  )

  return (
    <div className="sectioned-flow">
      {run && !file && run.workflow_sections.length > 0 && <div className="notice notice--review"><strong>Resume needs two transient inputs</strong><span>Reselect the source workbook and re-enter runtime details. Confirmed section mappings and safe fingerprints were restored; personal declaration values were not.</span></div>}
      <section className="workflow-card">
        <div className="section-heading"><div><p className="eyebrow">Workflow details</p><h2>Enter transient return details</h2><p>Fields are generated from this RegPack. Sensitive values stay in browser/request memory and are not persisted.</p></div></div>
        <div className="runtime-grid">{workflow.runtime_fields.map((field) => <label key={field.id}>{field.name}{field.required && <span aria-label="required"> *</span>}<input type={field.data_type === 'date' ? 'date' : 'text'} maxLength={field.max_length ?? undefined} value={runtime[field.id] ?? ''} onChange={(event) => { setRuntime((current) => ({ ...current, [field.id]: event.target.value })); setPreflight(null) }} /><small>{field.description}{field.sensitive ? ' This value is transient.' : ''}</small></label>)}</div>
      </section>

      <section className="workflow-card workflow-card--wide">
        <div className="section-heading"><div><p className="eyebrow">Source workbook</p><h2>Upload once, map each section</h2><p>One customer XLSX can supply different worksheets to each canonical section.</p></div></div>
        {!file ? <label className="upload-zone"><strong>Choose a customer XLSX</strong><span>The official {detail.regulator.name} template is output-only; upload your operational export here.</span><input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => { const selected = event.target.files?.[0]; if (selected) void chooseFile(selected) }} /></label>
          : <div className="selected-file"><div><strong>{file.name}</strong><span>{overview?.sheets.filter((sheet) => sheet.visibility === 'visible').length ?? 0} visible worksheets</span></div><button className="button button--quiet" onClick={() => { setFile(null); setOverview(null); setPreflight(null); setMappingResult(null) }}>Choose another file</button></div>}
        {loading === 'inspect' && <div className="loading-panel">Inspecting worksheets and preparing safe mapping recommendations…</div>}

        {file && overview && <div className="section-mapping-list">{workflow.sections.map((definition) => {
          const state = sections[definition.id]
          const mapped = Object.values(state.drafts).filter((draft) => draft.sourceColumnIndex !== null).length
          return <article className="section-mapping-card" key={definition.id}>
            <div className="section-heading"><div><h3>{definition.name}</h3><p>{definition.description}</p></div><span className={`badge ${state.enabled ? 'badge--match-exact' : ''}`}>{state.enabled ? `${mapped}/${definition.schema.fields.length} mapped` : 'No transactions'}</span></div>
            {definition.optional && <label className="inline-check"><input type="checkbox" checked={!state.enabled} onChange={(event) => { setSections((current) => ({ ...current, [definition.id]: { ...current[definition.id], enabled: !event.target.checked } })); setMappingResult(null); setPreflight(null) }} /> No transactions in this section for this period</label>}
            {state.enabled && <>
              <div className="inspection-controls"><label>Worksheet<select value={state.sheetName ?? ''} onChange={(event) => { if (event.target.value) void inspectSection(definition.id, file, event.target.value, state.headerRow) }}><option value="">Choose a worksheet</option>{overview.sheets.filter((sheet) => sheet.visibility === 'visible').map((sheet) => <option key={sheet.name}>{sheet.name}</option>)}</select></label><label>Header row<input type="number" min={limits?.min_header_row ?? 1} max={limits?.max_header_row ?? 50} value={state.headerRow} onChange={(event) => { if (state.sheetName) void inspectSection(definition.id, file, state.sheetName, Number(event.target.value)) }} /></label></div>
              {state.profiles.length > 0 && <div className="saved-mapping-panel"><div><strong>Exact saved mapping available</strong><small>Apply it for review; confirmation is still required.</small></div><button className="button button--secondary" onClick={() => { const profile = state.profiles[0]; setSections((current) => ({ ...current, [definition.id]: { ...current[definition.id], drafts: mappingDefinitionToDrafts(definition.schema, profile.mapping_definition), appliedProfile: profile } })) }}>Apply saved mapping</button></div>}
              {state.inspection && <div className="table-scroll compact-section-table"><table><thead><tr><th>Canonical field</th><th>Required</th><th>Recommended source</th><th>Match</th></tr></thead><tbody>{definition.schema.fields.map((field) => { const draft = state.drafts[field.id]; return <tr key={field.id}><th>{field.name}</th><td>{field.required ? 'Yes' : 'No'}</td><td><select value={draft.sourceColumnIndex ?? ''} onChange={(event) => { const value = event.target.value ? Number(event.target.value) : null; setSections((current) => ({ ...current, [definition.id]: { ...current[definition.id], drafts: { ...current[definition.id].drafts, [field.id]: { ...draft, sourceColumnIndex: value, matchKind: value ? 'manual' : null } } } })); setMappingResult(null); setPreflight(null) }}><option value="">Not mapped</option>{state.inspection!.columns.map((column) => <option key={column.index} value={column.index}>{column.excel_column ?? column.index} · {column.header ?? 'Untitled'}</option>)}</select></td><td>{draft.matchKind ? <span className="badge badge--match-exact">{draft.matchKind}</span> : <span className="badge badge--blocking">Review</span>}</td></tr> })}</tbody></table></div>}
            </>}
          </article>
        })}</div>}
        {file && <><label className="save-mapping-choice"><input type="checkbox" checked={saveProfiles} onChange={(event) => setSaveProfiles(event.target.checked)} /><span><strong>Save exact section mappings for future months</strong><small>Profiles are keyed by RegPack, section, schema, fingerprint, and positional header signature.</small></span></label><div className="actions actions--end"><button className="button button--secondary" disabled={!ready || loading !== null} onClick={() => void checkMapping()}>{loading === 'map' ? 'Checking…' : 'Confirm & Check All Sections'}</button><button className="button button--primary" disabled={!mappingResult?.success || loading !== null} onClick={() => void runPreflight()}>{loading === 'preflight' ? 'Running preflight…' : 'Run Preflight'}</button></div></>}
        {mappingResult && <div className={`notice ${mappingResult.success ? 'notice--success' : 'notice--blocking'}`}><strong>{mappingResult.success ? 'All active section mappings passed' : 'Some section mappings need attention'}</strong><span>{mappingResult.sections.map((item) => `${item.section_id}: ${item.dataset_summary.record_count} rows`).join(' · ')}</span></div>}
      </section>

      {preflight && <section className="workflow-card"><p className="eyebrow">Preflight</p><h2>{preflight.ready ? 'Ready to generate' : 'Resolve blocking findings'}</h2><div className="inspection-grid"><div><span>Blocking</span><strong>{preflight.blocking_findings}</strong></div><div><span>Review</span><strong>{preflight.review_findings}</strong></div><div><span>Passed</span><strong>{preflight.passed_checks}</strong></div><div><span>Sections</span><strong>{preflight.sections.length}</strong></div></div>{preflight.runtime_validation?.findings.map((finding) => <div className="notice notice--blocking" key={`${finding.rule_id}-${finding.record_id}`}><strong>{finding.rule_id}</strong><span>{finding.message}</span></div>)}{preflight.sections.map((section) => <article className="preflight-section" key={section.section_id}><strong>{workflow.sections.find((item) => item.id === section.section_id)?.name}</strong><span>{section.omitted ? 'No transactions' : `${section.dataset_summary.record_count} records`} · reconciliation {section.reconciliation_status.replace('_', ' ')}</span>{section.validation?.findings.map((finding) => <small key={`${finding.rule_id}-${finding.record_id}`}>{finding.rule_id}: {finding.message}</small>)}</article>)}<div className="actions actions--end"><button className="button button--quiet" onClick={() => setPreflight(null)}>Back to mapping</button><button className="button button--primary" disabled={!preflight.can_generate || loading !== null} onClick={() => void generate()}>{loading === 'generate' ? 'Generating…' : 'Generate Official Workbook'}</button></div></section>}

      <section className="workflow-card workflow-card--subtle"><h3>Reporting workflow</h3><p>Register period: {detail.reporting?.record_period?.frequency ?? detail.reporting?.frequency ?? 'See RegPack'} · Submission cadence: {detail.reporting?.submission?.frequency ?? 'See RegPack'}</p>{detail.reporting?.exceptions?.map((item) => <p key={item.description}>{item.description}</p>)}{detail.reporting?.notes?.map((item) => <p key={item.description}>{item.description}</p>)}</section>
    </div>
  )
}
