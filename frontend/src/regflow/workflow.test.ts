import { describe, expect, it } from 'vitest'

import type { CanonicalSchema, RegFlowPreflightResult, RegPackDetail, RegPackSummary, RegPackWorkflow, SourceFileInspection } from '../types/regflow'
import {
  createMappingDrafts,
  initialWorkflowState,
  mappingRecommendationSummary,
  mappingDefinitionToDrafts,
  recommendMappingDrafts,
  requiredMappingsComplete,
  workflowReducer,
} from './workflow'

const pack: RegPackSummary = {
  id: 'example-pack',
  name: 'Example Pack',
  regulator: { code: 'EX', name: 'Example Regulator' },
  versions: ['1.0.0', '1.1.0'],
  workflow_versions: ['1.0.0', '1.1.0'],
  output_versions: ['1.1.0'],
}

const schema: CanonicalSchema = {
  id: 'example-schema',
  version: '1.0.0',
  name: 'Example Schema',
  description: null,
  fields: [
    { id: 'required_name', name: 'Required name', data_type: 'string', required: true, description: null, aliases: ['Name'] },
    { id: 'optional_count', name: 'Optional count', data_type: 'integer', required: false, description: null, aliases: ['Count'] },
  ],
}

function inspection(headers = ['required_name', 'Count']): SourceFileInspection {
  return {
    source_name: 'source.csv',
    source_type: 'csv',
    file_size_bytes: 20,
    file_sha256: 'a'.repeat(64),
    sheets: [],
    selected_sheet: null,
    selection_required: false,
    header_row: 1,
    columns: headers.map((header, index) => ({ index: index + 1, header, excel_column: null })),
    data_row_count: 1,
    preview_rows: [],
    formula_cells_detected: false,
    warnings: [],
    source_header_signature: 'f'.repeat(64),
    source_signature_version: 'source-header-v1',
    run_id: null, run_state: null, run_revision: null,
  }
}

function preflight(canGenerate: boolean): RegFlowPreflightResult {
  return {
    success: true,
    pack: {
      id: pack.id,
      version: '1.1.0',
      name: pack.name,
      regulator_code: pack.regulator.code,
      regulator_name: pack.regulator.name,
      status: 'verified',
      fingerprint: 'a'.repeat(64),
      output_configured: true,
      sources: [],
    },
    source_summary: {
      source_name: 'source.csv', source_type: 'csv', file_size_bytes: 10,
      file_sha256: 'b'.repeat(64), selected_sheet: null, data_row_count: 1,
      column_count: 1, formula_cells_detected: false, warnings: [],
    },
    mapping_fingerprint: 'c'.repeat(64),
    dataset_summary: { dataset_id: 'data', schema_id: schema.id, schema_version: schema.version, record_count: 1, preview_count: 1 },
    dataset_fingerprint: 'd'.repeat(64),
    import_issues: [], total_import_issues: 0, returned_import_issues: 0,
    import_issues_truncated: false, validation: null, reconciliation: null,
    blocking_findings: canGenerate ? 0 : 1,
    review_findings: canGenerate ? 1 : 0,
    passed_checks: 10,
    ready: canGenerate,
    can_generate: canGenerate,
    run_id: null, run_state: null, run_revision: null,
  }
}

describe('RegFlow workflow state', () => {
  it('loads arbitrary multi-section workflow metadata without a pack-specific branch', () => {
    const secondSchema = { ...schema, id: 'dispatch-schema', name: 'Dispatches' }
    const workflow: RegPackWorkflow = {
      id: 'inventory-workflow', version: '1.0.0', runtime_fields: [], rules: [],
      sections: [
        { id: 'receipts', name: 'Receipts', description: null, optional: false, schema, reconciliation: 'not_applicable' },
        { id: 'dispatches', name: 'Dispatches', description: null, optional: true, schema: secondSchema, reconciliation: 'not_applicable' },
      ],
    }
    const detail = {
      id: pack.id, name: pack.name, version: '1.0.0', regulator: pack.regulator,
      description: 'Generic inventory proof', status: 'draft', reporting: null,
      sources: [], fingerprint: null, canonical_schema_id: null,
      canonical_schema_version: null, output_definition_id: null,
      output_definition_version: null, output_type: null,
      workflow_definition_id: workflow.id, workflow_definition_version: workflow.version,
      workflow_section_count: 2, runtime_field_count: 0,
    } satisfies RegPackDetail
    const loaded = workflowReducer(
      { ...initialWorkflowState, pack, version: '1.0.0' },
      { type: 'PACK_METADATA_READY', detail, workflow },
    )
    expect(loaded.workflow?.sections.map((section) => section.id)).toEqual(['receipts', 'dispatches'])
    expect(loaded.schema?.id).toBe(schema.id)
  })

  it('handles explicit pack selection without choosing among multiple versions', () => {
    const selected = workflowReducer(initialWorkflowState, { type: 'SELECT_PACK', pack })
    expect(selected.step).toBe('select')
    expect(selected.version).toBe('')
    expect(selected.pack?.id).toBe(pack.id)
  })

  it('requires every required schema field to be mapped', () => {
    const drafts = createMappingDrafts(schema)
    expect(requiredMappingsComplete(schema, drafts)).toBe(false)
    drafts.required_name.sourceColumnIndex = 1
    expect(requiredMappingsComplete(schema, drafts)).toBe(true)
  })

  it('applies a saved positional mapping as a reviewable draft', () => {
    const drafts = mappingDefinitionToDrafts(schema, {
      target_schema_id: schema.id, target_schema_version: schema.version,
      sheet_name: null, header_row: 1, skip_blank_rows: true,
      fields: [{ source_column_index: 2, target_field_id: 'required_name', conversion: { type: 'string', trim_whitespace: true } }],
    })
    expect(drafts.required_name.sourceColumnIndex).toBe(2)
    expect(drafts.required_name.matchKind).toBe('manual')
    expect(drafts.required_name.trimWhitespace).toBe(true)
  })

  it('recommends exact and RegPack-approved alias matches', () => {
    const drafts = recommendMappingDrafts(schema, inspection())
    expect(drafts.required_name.sourceColumnIndex).toBe(1)
    expect(drafts.required_name.matchKind).toBe('exact')
    expect(drafts.optional_count.sourceColumnIndex).toBe(2)
    expect(drafts.optional_count.matchKind).toBe('alias')
    expect(mappingRecommendationSummary(schema, drafts)).toEqual({
      exact: 1,
      aliases: 1,
      manual: 0,
      unresolvedRequired: 0,
    })
  })

  it('does not guess when a recommended header is duplicated', () => {
    const drafts = recommendMappingDrafts(schema, inspection(['Name', 'Name']))
    expect(drafts.required_name.sourceColumnIndex).toBeNull()
    expect(mappingRecommendationSummary(schema, drafts).unresolvedRequired).toBe(1)
  })

  it('applies recommendations as soon as inspection completes', () => {
    const readyForInspection = { ...initialWorkflowState, schema, mappings: createMappingDrafts(schema) }
    const inspected = workflowReducer(readyForInspection, { type: 'INSPECTION_READY', inspection: inspection() })
    expect(inspected.mappings.required_name.matchKind).toBe('exact')
    expect(inspected.mappings.optional_count.matchKind).toBe('alias')
    expect(requiredMappingsComplete(schema, inspected.mappings)).toBe(true)
  })

  it('can restore deterministic recommendations after a manual edit', () => {
    const inspected = {
      ...initialWorkflowState,
      step: 'map' as const,
      schema,
      inspection: inspection(),
      mappings: recommendMappingDrafts(schema, inspection()),
    }
    const changed = workflowReducer(inspected, {
      type: 'MAPPING_CHANGED',
      fieldId: 'required_name',
      draft: { ...inspected.mappings.required_name, sourceColumnIndex: null, matchKind: null },
    })
    const restored = workflowReducer(changed, { type: 'APPLY_MAPPING_RECOMMENDATIONS' })
    expect(restored.mappings.required_name.sourceColumnIndex).toBe(1)
    expect(restored.mappings.required_name.matchKind).toBe('exact')
  })

  it('preselects all 18 columns in the synthetic Phase 8 return fixture', () => {
    const columns = [
      ['company_name', 'Company'], ['licence_number', 'Licence'],
      ['reporting_period', 'Period'], ['section_code', 'Section'],
      ['item_description', 'Description'], ['unit', 'Unit'],
      ['opening_balance', 'Opening'], ['from_generator', 'Generator'],
      ['from_licensed_collector', 'Collector'], ['direct_reuse', 'Reuse'],
      ['export_quantity', 'Export'], ['resale_to_licensed_collector', 'Resale'],
      ['recycle_recover', 'Recycle'], ['incinerate', 'Incinerate'],
      ['discharge_to_sewer', 'Sewer'], ['landfill', 'Landfill'],
      ['fixation', 'Fixation'], ['actual_closing_balance', 'Closing'],
    ] as const
    const fixtureSchema: CanonicalSchema = {
      id: 'return-schema', version: '1.0.0', name: 'Return', description: null,
      fields: columns.map(([id, header], index) => ({
        id,
        name: id.replaceAll('_', ' '),
        data_type: index < 6 ? 'string' : 'decimal',
        required: index < 6,
        description: null,
        aliases: [header],
      })),
    }
    const drafts = recommendMappingDrafts(fixtureSchema, inspection(columns.map(([, header]) => header)))
    const summary = mappingRecommendationSummary(fixtureSchema, drafts)
    expect(Object.values(drafts).every((draft) => draft.sourceColumnIndex !== null)).toBe(true)
    expect(summary.exact + summary.aliases).toBe(18)
    expect(summary.unresolvedRequired).toBe(0)
  })

  it('retains blocking readiness as generation-disabled', () => {
    const result = preflight(false)
    const state = workflowReducer(initialWorkflowState, { type: 'PREFLIGHT_READY', result })
    expect(state.step).toBe('preflight')
    expect(state.preflight?.can_generate).toBe(false)
  })

  it('allows generation when only review findings remain', () => {
    const result = preflight(true)
    const state = workflowReducer(initialWorkflowState, { type: 'PREFLIGHT_READY', result })
    expect(state.preflight?.review_findings).toBe(1)
    expect(state.preflight?.can_generate).toBe(true)
  })

  it('invalidates preflight and generated state when a mapping changes', () => {
    const result = preflight(true)
    const generated = { blob: new Blob(['x']), filename: 'output.xlsx', artifactId: null, sha256: null, runId: null, runState: null, runRevision: null }
    const ready = { ...initialWorkflowState, step: 'complete' as const, schema, mappings: createMappingDrafts(schema), preflight: result, generated }
    const changed = workflowReducer(ready, {
      type: 'MAPPING_CHANGED',
      fieldId: 'required_name',
      draft: { ...ready.mappings.required_name, sourceColumnIndex: 1 },
    })
    expect(changed.step).toBe('map')
    expect(changed.preflight).toBeNull()
    expect(changed.generated).toBeNull()
  })
})
