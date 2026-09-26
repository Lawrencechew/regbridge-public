import type {
  CanonicalSchema,
  FieldMapping,
  GeneratedFile,
  ImportMapping,
  ImportResult,
  MappingProfileVersion,
  MappingDraft,
  MappingDrafts,
  RegFlowPreflightResult,
  RegPackDetail,
  RegPackSummary,
  RegPackWorkflow,
  RunDetail,
  SourceFileInspection,
  WorkflowStep,
} from '../types/regflow'

export interface WorkflowState {
  step: WorkflowStep
  pack: RegPackSummary | null
  version: string
  packDetail: RegPackDetail | null
  schema: CanonicalSchema | null
  workflow: RegPackWorkflow | null
  file: File | null
  inspection: SourceFileInspection | null
  sheetName: string | null
  headerRow: number
  mappings: MappingDrafts
  mappingResult: ImportResult | null
  preflight: RegFlowPreflightResult | null
  generated: GeneratedFile | null
  run: RunDetail | null
  matchedProfiles: MappingProfileVersion[]
  appliedProfile: MappingProfileVersion | null
  saveMappingProfile: boolean
}

export const initialWorkflowState: WorkflowState = {
  step: 'select',
  pack: null,
  version: '',
  packDetail: null,
  schema: null,
  workflow: null,
  file: null,
  inspection: null,
  sheetName: null,
  headerRow: 1,
  mappings: {},
  mappingResult: null,
  preflight: null,
  generated: null,
  run: null,
  matchedProfiles: [],
  appliedProfile: null,
  saveMappingProfile: false,
}

export type WorkflowAction =
  | { type: 'SELECT_PACK'; pack: RegPackSummary | null }
  | { type: 'SELECT_VERSION'; version: string }
  | { type: 'PACK_METADATA_READY'; detail: RegPackDetail; workflow: RegPackWorkflow }
  | { type: 'CONTINUE_PACK' }
  | { type: 'RUN_CREATED'; run: RunDetail }
  | { type: 'RUN_RESTORED'; run: RunDetail; pack: RegPackSummary }
  | { type: 'RUN_MUTATED'; state: RunDetail['state']; revision: number }
  | { type: 'FILE_SELECTED'; file: File }
  | { type: 'FILE_REMOVED' }
  | { type: 'INSPECTION_READY'; inspection: SourceFileInspection }
  | { type: 'INSPECTION_OPTIONS_CHANGED'; sheetName: string | null; headerRow: number }
  | { type: 'GO_TO_MAP' }
  | { type: 'APPLY_MAPPING_RECOMMENDATIONS' }
  | { type: 'MAPPING_PROFILES_MATCHED'; profiles: MappingProfileVersion[] }
  | { type: 'APPLY_SAVED_MAPPING'; profile: MappingProfileVersion }
  | { type: 'SET_SAVE_MAPPING_PROFILE'; value: boolean }
  | { type: 'MAPPING_CHANGED'; fieldId: string; draft: MappingDraft }
  | { type: 'MAPPING_CHECKED'; result: ImportResult }
  | { type: 'PREFLIGHT_READY'; result: RegFlowPreflightResult }
  | { type: 'GENERATION_STARTED' }
  | { type: 'GENERATION_READY'; generated: GeneratedFile }
  | { type: 'GO_TO_UPLOAD' }
  | { type: 'GO_TO_MAPPING' }
  | { type: 'START_NEW' }

export function workflowReducer(state: WorkflowState, action: WorkflowAction): WorkflowState {
  switch (action.type) {
    case 'SELECT_PACK':
      return {
        ...initialWorkflowState,
        pack: action.pack,
        version: action.pack?.versions.length === 1 ? action.pack.versions[0] : '',
      }
    case 'SELECT_VERSION':
      return { ...initialWorkflowState, pack: state.pack, version: action.version }
    case 'PACK_METADATA_READY':
      {
      const schema = action.workflow.sections[0]?.schema ?? null
      return {
        ...state,
        packDetail: action.detail,
        schema,
        workflow: action.workflow,
        mappings: state.run?.mapping.definition
          && schema && action.workflow.sections.length === 1
          ? mappingDefinitionToDrafts(schema, state.run.mapping.definition as ImportMapping)
          : state.inspection && schema
          ? recommendMappingDrafts(schema, state.inspection)
          : schema ? createMappingDrafts(schema) : {},
      }
      }
    case 'CONTINUE_PACK':
      return { ...state, step: 'upload' }
    case 'RUN_CREATED':
      return { ...state, step: 'upload', run: action.run }
    case 'RUN_RESTORED':
      return {
        ...initialWorkflowState, pack: action.pack, version: action.run.pack.version,
        step: 'upload', run: action.run,
        sheetName: action.run.source.selected_sheet,
        headerRow: action.run.source.header_row ?? 1,
      }
    case 'RUN_MUTATED':
      return state.run ? { ...state, run: { ...state.run, state: action.state, revision: action.revision, updated_at: new Date().toISOString() } } : state
    case 'FILE_SELECTED':
      return {
        ...state,
        step: 'inspect',
        file: action.file,
        inspection: null,
        sheetName: null,
        headerRow: 1,
        mappings: state.schema ? createMappingDrafts(state.schema) : {},
        mappingResult: null,
        preflight: null,
        generated: null,
        matchedProfiles: [],
        appliedProfile: null,
        saveMappingProfile: false,
      }
    case 'FILE_REMOVED':
      return {
        ...state,
        step: 'upload',
        file: null,
        inspection: null,
        sheetName: null,
        headerRow: 1,
        mappings: state.schema ? createMappingDrafts(state.schema) : {},
        mappingResult: null,
        preflight: null,
        generated: null,
        matchedProfiles: [],
        appliedProfile: null,
        saveMappingProfile: false,
      }
    case 'INSPECTION_READY':
      return {
        ...state,
        step: 'inspect',
        inspection: action.inspection,
        mappings: state.schema
          ? recommendMappingDrafts(state.schema, action.inspection)
          : state.mappings,
        mappingResult: null,
        preflight: null,
        generated: null,
        run: updateRunFromMutation(state.run, action.inspection),
        matchedProfiles: [],
        appliedProfile: null,
        saveMappingProfile: false,
      }
    case 'INSPECTION_OPTIONS_CHANGED':
      return {
        ...state,
        step: 'inspect',
        sheetName: action.sheetName,
        headerRow: action.headerRow,
        inspection: null,
        mappings: state.schema ? createMappingDrafts(state.schema) : {},
        mappingResult: null,
        preflight: null,
        generated: null,
        matchedProfiles: [],
        appliedProfile: null,
        saveMappingProfile: false,
      }
    case 'GO_TO_MAP':
      return { ...state, step: 'map' }
    case 'APPLY_MAPPING_RECOMMENDATIONS':
      if (!state.schema || !state.inspection) return state
      return {
        ...state,
        step: 'map',
        mappings: recommendMappingDrafts(state.schema, state.inspection),
        mappingResult: null,
        preflight: null,
        generated: null,
        appliedProfile: null,
      }
    case 'MAPPING_PROFILES_MATCHED':
      return { ...state, matchedProfiles: action.profiles }
    case 'APPLY_SAVED_MAPPING':
      if (!state.schema) return state
      return {
        ...state,
        mappings: mappingDefinitionToDrafts(state.schema, action.profile.mapping_definition),
        appliedProfile: action.profile,
        mappingResult: null,
        preflight: null,
        generated: null,
      }
    case 'SET_SAVE_MAPPING_PROFILE':
      return { ...state, saveMappingProfile: action.value }
    case 'MAPPING_CHANGED':
      return {
        ...state,
        step: 'map',
        mappings: { ...state.mappings, [action.fieldId]: action.draft },
        mappingResult: null,
        preflight: null,
        generated: null,
      }
    case 'MAPPING_CHECKED':
      return {
        ...state, mappingResult: action.result, preflight: null, generated: null,
        run: updateRunFromMutation(state.run, action.result),
      }
    case 'PREFLIGHT_READY':
      return {
        ...state, step: 'preflight', preflight: action.result, generated: null,
        run: updateRunFromMutation(state.run, action.result),
      }
    case 'GENERATION_STARTED':
      return { ...state, step: 'generate', generated: null }
    case 'GENERATION_READY':
      return {
        ...state, step: 'complete', generated: action.generated,
        run: updateRunFromMutation(state.run, action.generated),
      }
    case 'GO_TO_UPLOAD':
      return {
        ...state,
        step: 'upload',
        file: null,
        inspection: null,
        mappingResult: null,
        preflight: null,
        generated: null,
      }
    case 'GO_TO_MAPPING':
      return { ...state, step: 'map', mappingResult: null, preflight: null, generated: null }
    case 'START_NEW':
      return initialWorkflowState
  }
}

export function createMappingDrafts(schema: CanonicalSchema): MappingDrafts {
  return Object.fromEntries(
    schema.fields.map((field) => [
      field.id,
      {
        sourceColumnIndex: null,
        matchKind: null,
        trimWhitespace: false,
        thousandsSeparator: '',
        decimalSeparator: '.',
        trueValues: 'true, yes',
        falseValues: 'false, no',
        caseSensitive: false,
        dateFormat: '%Y-%m-%d',
        datetimeFormat: '%Y-%m-%d %H:%M:%S',
      },
    ]),
  )
}

type RunMutation = {
  run_id?: string | null
  run_state?: RunDetail['state'] | null
  run_revision?: number | null
  runId?: string | null
  runState?: RunDetail['state'] | null
  runRevision?: number | null
}

function updateRunFromMutation(run: RunDetail | null, mutation: RunMutation): RunDetail | null {
  if (!run) return null
  const id = mutation.run_id ?? mutation.runId
  const state = mutation.run_state ?? mutation.runState
  const revision = mutation.run_revision ?? mutation.runRevision
  if (!id || id !== run.id || !state || revision === null || revision === undefined) return run
  return { ...run, state, revision, updated_at: new Date().toISOString() }
}

export function mappingDefinitionToDrafts(
  schema: CanonicalSchema, mapping: ImportMapping,
): MappingDrafts {
  const drafts = createMappingDrafts(schema)
  for (const fieldMapping of mapping.fields) {
    const draft = drafts[fieldMapping.target_field_id]
    if (!draft) continue
    const conversion = fieldMapping.conversion
    drafts[fieldMapping.target_field_id] = {
      ...draft,
      sourceColumnIndex: fieldMapping.source_column_index,
      matchKind: 'manual',
      trimWhitespace: conversion.type === 'string' ? conversion.trim_whitespace : draft.trimWhitespace,
      thousandsSeparator: conversion.type === 'decimal' ? conversion.thousands_separator ?? '' : draft.thousandsSeparator,
      decimalSeparator: conversion.type === 'decimal' ? conversion.decimal_separator : draft.decimalSeparator,
      trueValues: conversion.type === 'boolean' ? conversion.true_values.join(', ') : draft.trueValues,
      falseValues: conversion.type === 'boolean' ? conversion.false_values.join(', ') : draft.falseValues,
      caseSensitive: conversion.type === 'boolean' ? conversion.case_sensitive : draft.caseSensitive,
      dateFormat: conversion.type === 'date' ? conversion.date_format ?? '' : draft.dateFormat,
      datetimeFormat: conversion.type === 'datetime' ? conversion.datetime_format ?? '' : draft.datetimeFormat,
    }
  }
  return drafts
}

interface MappingCandidate {
  fieldId: string
  sourceColumnIndex: number
  matchKind: 'exact' | 'alias'
  score: number
}

export function recommendMappingDrafts(
  schema: CanonicalSchema,
  inspection: SourceFileInspection,
): MappingDrafts {
  const drafts = createMappingDrafts(schema)
  const proposals: MappingCandidate[] = []

  for (const field of schema.fields) {
    const exactTerms = new Set([field.id, field.name].map(normaliseMappingTerm))
    const aliasTerms = new Set(field.aliases.map(normaliseMappingTerm))
    const candidates: MappingCandidate[] = []

    for (const column of inspection.columns) {
      if (!column.header) continue
      const header = normaliseMappingTerm(column.header)
      if (!header) continue
      if (exactTerms.has(header)) {
        candidates.push({ fieldId: field.id, sourceColumnIndex: column.index, matchKind: 'exact', score: 2 })
      } else if (aliasTerms.has(header)) {
        candidates.push({ fieldId: field.id, sourceColumnIndex: column.index, matchKind: 'alias', score: 1 })
      }
    }

    const bestScore = Math.max(0, ...candidates.map((candidate) => candidate.score))
    const best = candidates.filter((candidate) => candidate.score === bestScore)
    if (best.length === 1) proposals.push(best[0])
  }

  const proposalsByColumn = new Map<number, MappingCandidate[]>()
  for (const proposal of proposals) {
    const current = proposalsByColumn.get(proposal.sourceColumnIndex) ?? []
    current.push(proposal)
    proposalsByColumn.set(proposal.sourceColumnIndex, current)
  }

  for (const candidates of proposalsByColumn.values()) {
    const bestScore = Math.max(...candidates.map((candidate) => candidate.score))
    const best = candidates.filter((candidate) => candidate.score === bestScore)
    if (best.length !== 1) continue
    const recommendation = best[0]
    drafts[recommendation.fieldId] = {
      ...drafts[recommendation.fieldId],
      sourceColumnIndex: recommendation.sourceColumnIndex,
      matchKind: recommendation.matchKind,
    }
  }

  return drafts
}

export function mappingRecommendationSummary(schema: CanonicalSchema, drafts: MappingDrafts) {
  const values = schema.fields.map((field) => drafts[field.id]).filter(Boolean)
  return {
    exact: values.filter((draft) => draft.matchKind === 'exact').length,
    aliases: values.filter((draft) => draft.matchKind === 'alias').length,
    manual: values.filter((draft) => draft.matchKind === 'manual').length,
    unresolvedRequired: schema.fields.filter(
      (field) => field.required && drafts[field.id]?.sourceColumnIndex === null,
    ).length,
  }
}

function normaliseMappingTerm(value: string): string {
  return value
    .normalize('NFKD')
    .toLocaleLowerCase('en')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/g, '')
}

export function requiredMappingsComplete(schema: CanonicalSchema, drafts: MappingDrafts): boolean {
  return schema.fields.every((field) => !field.required || drafts[field.id]?.sourceColumnIndex !== null)
}

export function buildImportMapping(
  schema: CanonicalSchema,
  drafts: MappingDrafts,
  sheetName: string | null,
  headerRow: number,
): ImportMapping {
  const fields: FieldMapping[] = []
  for (const field of schema.fields) {
    const draft = drafts[field.id]
    if (!draft || draft.sourceColumnIndex === null) continue
    const source = { source_column_index: draft.sourceColumnIndex, target_field_id: field.id }
    switch (field.data_type) {
      case 'string':
        fields.push({ ...source, conversion: { type: 'string', trim_whitespace: draft.trimWhitespace } })
        break
      case 'integer':
        fields.push({ ...source, conversion: { type: 'integer' } })
        break
      case 'decimal':
        fields.push({ ...source, conversion: { type: 'decimal', thousands_separator: draft.thousandsSeparator || null, decimal_separator: draft.decimalSeparator || '.' } })
        break
      case 'boolean':
        fields.push({ ...source, conversion: { type: 'boolean', true_values: splitTokens(draft.trueValues), false_values: splitTokens(draft.falseValues), case_sensitive: draft.caseSensitive } })
        break
      case 'date':
        fields.push({ ...source, conversion: { type: 'date', date_format: draft.dateFormat || null } })
        break
      case 'datetime':
        fields.push({ ...source, conversion: { type: 'datetime', datetime_format: draft.datetimeFormat || null } })
        break
    }
  }
  return {
    target_schema_id: schema.id,
    target_schema_version: schema.version,
    sheet_name: sheetName,
    header_row: headerRow,
    skip_blank_rows: true,
    fields,
  }
}

function splitTokens(value: string): string[] {
  return value.split(',').map((token) => token.trim()).filter(Boolean)
}
