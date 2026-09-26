export type WorkflowStep =
  | 'select'
  | 'upload'
  | 'inspect'
  | 'map'
  | 'preflight'
  | 'generate'
  | 'complete'

export interface AuthUser { id: string; email: string; display_name: string }
export interface AuthOrganisation { id: string; name: string; slug: string; role: 'OWNER' | 'MEMBER' }
export interface AuthSession {
  auth_enabled: boolean
  authenticated: boolean
  user: AuthUser | null
  active_organisation: AuthOrganisation | null
  organisations: AuthOrganisation[]
}
export interface OrganisationMember {
  user_id: string; email: string; display_name: string; role: 'OWNER' | 'MEMBER'; joined_at: string
}
export interface OrganisationInvitation {
  id: string; invited_email: string; invited_role: 'OWNER' | 'MEMBER'
  expires_at: string; state: 'PENDING' | 'ACCEPTED' | 'REVOKED' | 'EXPIRED'; invitation_token: string | null
}

export type DataType = 'string' | 'integer' | 'decimal' | 'boolean' | 'date' | 'datetime'
export type Severity = 'blocking' | 'review'

export interface RegulatorMetadata {
  code: string
  name: string
}

export interface RegulatorySource {
  id: string
  title: string
  publisher: string
  url: string
  reference: string | null
  published_date: string | null
  checked_at: string
  content_hash: string | null
}

export interface RegPackSummary {
  id: string
  name: string
  regulator: RegulatorMetadata
  versions: string[]
  workflow_versions: string[]
  output_versions: string[]
}

export interface RegPackDetail {
  id: string
  name: string
  version: string
  regulator: RegulatorMetadata
  description: string
  status: 'draft' | 'verified' | 'deprecated' | null
  reporting: {
    frequency: 'monthly' | null
    submission_deadline: { type: string; day: number } | null
    record_period?: { frequency: 'monthly' | 'semiannual' | 'on_request' } | null
    submission?: { frequency: 'monthly' | 'semiannual' | 'on_request' } | null
    exceptions?: Array<{ description: string; source_refs: string[] }>
    notes?: Array<{ description: string; source_refs: string[] }>
  } | null
  sources: RegulatorySource[]
  fingerprint: string | null
  canonical_schema_id: string | null
  canonical_schema_version: string | null
  output_definition_id: string | null
  output_definition_version: string | null
  output_type: string | null
  workflow_definition_id: string | null
  workflow_definition_version: string | null
  workflow_section_count: number | null
  runtime_field_count: number | null
}

export interface RuntimeFieldDefinition {
  id: string
  name: string
  data_type: 'string' | 'date'
  required: boolean
  sensitive: boolean
  description: string | null
  max_length: number | null
  source_refs: string[]
}

export interface RegPackWorkflowSection {
  id: string
  name: string
  description: string | null
  optional: boolean
  schema: CanonicalSchema
  reconciliation: 'applicable' | 'not_applicable'
}

export interface RegPackWorkflow {
  id: string
  version: string
  runtime_fields: RuntimeFieldDefinition[]
  rules: Array<Record<string, unknown>>
  sections: RegPackWorkflowSection[]
}

export interface CanonicalField {
  id: string
  name: string
  data_type: DataType
  required: boolean
  description: string | null
  aliases: string[]
}

export interface CanonicalSchema {
  id: string
  version: string
  name: string
  description: string | null
  fields: CanonicalField[]
}

export interface SourceColumn {
  index: number
  header: string | null
  excel_column: string | null
}

export interface SourceSheet {
  name: string
  visibility: 'visible' | 'hidden' | 'veryHidden'
  row_count: number
  column_count: number
}

export interface SourcePreviewRow {
  source_row: number
  values: Array<unknown>
}

export interface SourceFileInspection {
  source_name: string
  source_type: 'csv' | 'xlsx'
  file_size_bytes: number
  file_sha256: string
  sheets: SourceSheet[]
  selected_sheet: string | null
  selection_required: boolean
  header_row: number
  columns: SourceColumn[]
  data_row_count: number | null
  preview_rows: SourcePreviewRow[]
  formula_cells_detected: boolean
  warnings: string[]
  source_header_signature: string
  source_signature_version: string
  run_id: string | null
  run_state: RunState | null
  run_revision: number | null
}

export interface ImportLimits {
  max_file_size_bytes: number
  max_rows: number
  max_columns: number
  max_xlsx_sheets: number
  preview_rows: number
  min_header_row: number
  max_header_row: number
}

export type Conversion =
  | { type: 'string'; trim_whitespace: boolean }
  | { type: 'integer' }
  | { type: 'decimal'; thousands_separator: string | null; decimal_separator: string }
  | {
      type: 'boolean'
      true_values: string[]
      false_values: string[]
      case_sensitive: boolean
    }
  | { type: 'date'; date_format: string | null }
  | { type: 'datetime'; datetime_format: string | null }

export interface FieldMapping {
  source_column_index: number
  target_field_id: string
  conversion: Conversion
}

export interface ImportMapping {
  target_schema_id: string
  target_schema_version: string
  sheet_name: string | null
  header_row: number
  skip_blank_rows: boolean
  fields: FieldMapping[]
}

export interface SectionImportMapping {
  section_id: string
  mapping: ImportMapping | null
}

export interface WorkflowImportMapping {
  sections: SectionImportMapping[]
}

export interface SourceReference {
  source_name: string | null
  sheet: string | null
  row: number | null
  column: string | null
}

export interface ImportIssue {
  code: string
  message: string
  severity: 'blocking' | 'warning'
  source: SourceReference | null
  target_field_id: string | null
  expected_type: DataType | null
}

export interface DatasetSummary {
  dataset_id: string
  schema_id: string
  schema_version: string
  record_count: number
  preview_count: number
}

export interface ImportResult {
  success: boolean
  source: SourceFileInspection
  mapping_fingerprint: string
  dataset_summary: DatasetSummary | null
  dataset_preview: Array<unknown>
  issues: ImportIssue[]
  run_id: string | null
  run_state: RunState | null
  run_revision: number | null
  mapping_profile: MappingProfileVersion | null
}

export interface ValidationFinding {
  rule_id: string
  rule_type: string
  rule_name: string
  severity: Severity
  message: string
  record_id: string | null
  field_id: string | null
  actual: unknown
  expected: unknown
  source: SourceReference | null
  source_refs: string[]
}

export interface ReconciliationSourceValue {
  field_id: string
  value: unknown
  source: SourceReference | null
}

export interface ReconciliationFinding {
  rule_id: string
  rule_type: string
  rule_name: string
  severity: Severity
  message: string
  record_id: string | null
  group: Record<string, unknown> | null
  expected: string
  actual: string
  difference: string
  tolerance: string
  source_refs: string[]
  source_values: ReconciliationSourceValue[]
  records_considered: number | null
  records_skipped: number | null
}

export interface PreflightCheckResult<TFinding> {
  rule_set_id: string
  rule_set_version: string
  valid: boolean
  ready: boolean
  blocking_findings: number
  review_findings: number
  passed_checks: number
  skipped_checks: number
  total_findings: number
  returned_findings: number
  findings_truncated: boolean
  findings: TFinding[]
  report_fingerprint: string
}

export interface RegFlowPreflightResult {
  success: boolean
  pack: {
    id: string
    version: string
    name: string
    regulator_code: string
    regulator_name: string
    status: string | null
    fingerprint: string
    output_configured: boolean
    sources: Array<{
      id: string
      title: string
      publisher: string
      url: string
      reference: string | null
    }>
  }
  source_summary: {
    source_name: string
    source_type: 'csv' | 'xlsx'
    file_size_bytes: number
    file_sha256: string
    selected_sheet: string | null
    data_row_count: number | null
    column_count: number
    formula_cells_detected: boolean
    warnings: string[]
  }
  mapping_fingerprint: string
  dataset_summary: DatasetSummary | null
  dataset_fingerprint: string | null
  import_issues: ImportIssue[]
  total_import_issues: number
  returned_import_issues: number
  import_issues_truncated: boolean
  validation: PreflightCheckResult<ValidationFinding> | null
  reconciliation: PreflightCheckResult<ReconciliationFinding> | null
  blocking_findings: number
  review_findings: number
  passed_checks: number
  ready: boolean
  can_generate: boolean
  run_id: string | null
  run_state: RunState | null
  run_revision: number | null
}

export interface WorkflowSectionImportResult {
  section_id: string
  success: boolean
  omitted: boolean
  source: SourceFileInspection | null
  mapping_fingerprint: string | null
  dataset_summary: DatasetSummary
  dataset_preview: Array<unknown>
  issues: ImportIssue[]
}

export interface WorkflowImportResult {
  success: boolean
  mapping_fingerprint: string
  sections: WorkflowSectionImportResult[]
  run_id: string | null
  run_state: RunState | null
  run_revision: number | null
  mapping_profiles: Record<string, unknown>
}

export interface RuntimeFieldIssue {
  rule_id: string
  severity: Severity
  message: string
  field_id: string | null
  section_id: string | null
  record_id: string | null
  source_refs: string[]
}

export interface WorkflowSectionPreflightResult {
  section_id: string
  success: boolean
  omitted: boolean
  source_summary: (RegFlowPreflightResult['source_summary'] & {
    source_header_signature: string
    source_signature_version: string
  }) | null
  mapping_fingerprint: string | null
  dataset_summary: DatasetSummary
  dataset_fingerprint: string | null
  import_issues: ImportIssue[]
  validation: PreflightCheckResult<ValidationFinding> | null
  reconciliation_status: 'applicable' | 'not_applicable'
  reconciliation: PreflightCheckResult<ReconciliationFinding> | null
  ready: boolean
}

export interface WorkflowPreflightResult {
  success: boolean
  pack: RegFlowPreflightResult['pack']
  mapping_fingerprint: string
  bundle_id: string | null
  bundle_fingerprint: string | null
  runtime_validation: {
    valid: boolean; ready: boolean; blocking_findings: number; review_findings: number
    passed_checks: number; findings: RuntimeFieldIssue[]; fingerprint: string
  } | null
  sections: WorkflowSectionPreflightResult[]
  blocking_findings: number
  review_findings: number
  passed_checks: number
  ready: boolean
  can_generate: boolean
  validation_fingerprint: string | null
  reconciliation_fingerprint: string | null
  run_id: string | null
  run_state: RunState | null
  run_revision: number | null
}

export interface MappingDraft {
  sourceColumnIndex: number | null
  matchKind: 'exact' | 'alias' | 'manual' | null
  trimWhitespace: boolean
  thousandsSeparator: string
  decimalSeparator: string
  trueValues: string
  falseValues: string
  caseSensitive: boolean
  dateFormat: string
  datetimeFormat: string
}

export type MappingDrafts = Record<string, MappingDraft>

export interface GeneratedFile {
  blob: Blob
  filename: string
  artifactId: string | null
  sha256: string | null
  runId: string | null
  runState: RunState | null
  runRevision: number | null
}

export type RunState = 'DRAFT' | 'SOURCE_INSPECTED' | 'MAPPING_CONFIRMED' | 'PREFLIGHT_READY' | 'PREFLIGHT_BLOCKED' | 'OUTPUT_GENERATED' | 'INVALIDATED'

export interface RunDetail {
  id: string
  state: RunState
  revision: number
  created_at: string
  updated_at: string
  pack: { id: string; version: string; fingerprint: string }
  source: {
    display_name: string | null; source_type: string | null; size_bytes: number | null
    sha256: string | null; selected_sheet: string | null; header_row: number | null
    header_signature: string | null; signature_version: string | null
  }
  mapping: {
    canonical_schema_id: string | null; canonical_schema_version: string | null
    fingerprint: string | null; definition: ImportMapping | null; confirmed_at: string | null
    profile_id: string | null; profile_version: number | null
  }
  preflight: {
    snapshot_id: string | null; dataset_fingerprint: string | null
    validation_report_fingerprint: string | null; reconciliation_report_fingerprint: string | null
    blocking_count: number; review_count: number; passed_count: number; skipped_count: number
    ready: boolean; can_generate: boolean
  }
  artifact: {
    id: string; created_at: string; filename: string; media_type: string; size_bytes: number
    byte_sha256: string; logical_generation_fingerprint: string
    retained_bytes: false; storage_reference: null
  } | null
  invalidation_reason: string | null
  audit_events: Array<{
    id: string; event_type: string; run_revision: number; occurred_at: string
    metadata: Record<string, unknown>
  }>
  workflow_sections: Array<{
    section_id: string
    omitted: boolean
    source: null | {
      display_name: string; source_type: string; size_bytes: number; sha256: string
      selected_sheet: string; header_signature: string; signature_version: string
    }
    mapping: {
      canonical_schema_id: string; canonical_schema_version: string
      fingerprint: string | null; definition: ImportMapping | null; confirmed_at: string
      profile_id: string | null; profile_version: number | null
    }
    dataset: { fingerprint: string | null; record_count: number }
    preflight: { reconciliation_status: string; ready: boolean; blocking_count: number; review_count: number }
  }>
}

export interface RunSummary {
  id: string; state: RunState; revision: number; created_at: string; updated_at: string
  pack: { id: string; version: string; fingerprint: string }
  source_display_name: string | null; blocking_count: number; review_count: number
  preflight_ready: boolean; output_generated: boolean
}

export interface MappingProfileVersion {
  profile_id: string; profile_version: number; created_at: string; confirmed_at: string
  display_name: string | null
  pack: { id: string; version: string; fingerprint: string }
  canonical_schema_id: string; canonical_schema_version: string
  source_header_signature: string; source_signature_version: string
  mapping_fingerprint: string; mapping_definition: ImportMapping
  recommendation_origins: Record<string, string>
  section_id: string | null
}

export interface MappingProfileSummary {
  profile_id: string; display_name: string | null; latest_version: number
  pack: { id: string; version: string; fingerprint: string }
  canonical_schema_id: string; canonical_schema_version: string
  source_header_signature: string; created_at: string; updated_at: string
  section_id: string | null
}
