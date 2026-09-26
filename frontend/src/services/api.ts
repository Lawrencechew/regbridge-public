import type {
  CanonicalSchema,
  GeneratedFile,
  ImportLimits,
  ImportMapping,
  ImportResult,
  MappingProfileSummary,
  MappingProfileVersion,
  RegFlowPreflightResult,
  RegPackDetail,
  RegPackSummary,
  RegPackWorkflow,
  RunDetail,
  RunState,
  RunSummary,
  SourceFileInspection,
  WorkflowImportMapping,
  WorkflowImportResult,
  WorkflowPreflightResult,
  AuthSession,
  AuthOrganisation,
  OrganisationInvitation,
  OrganisationMember,
} from '../types/regflow'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

type HealthResponse = {
  status: 'healthy'
  service: string
  version: string
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string }
}

export class RegBridgeApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'RegBridgeApiError'
    this.code = code
    this.status = status
  }
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${url}`, authenticatedInit(init))
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new RegBridgeApiError('CONNECTION_ERROR', 'RegBridge could not connect to the API.', 0)
  }
  if (!response.ok) throw await apiError(response)
  return response.json() as Promise<T>
}

function cookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const prefix = `${encodeURIComponent(name)}=`
  const item = document.cookie.split(';').map((value) => value.trim()).find((value) => value.startsWith(prefix))
  return item ? decodeURIComponent(item.slice(prefix.length)) : null
}

function authenticatedInit(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers)
  const method = (init.method ?? 'GET').toUpperCase()
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrf = cookie('regbridge_csrf')
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }
  return { ...init, credentials: 'include', headers }
}

export function getSession(signal?: AbortSignal): Promise<AuthSession> {
  return requestJson('/auth/session', { signal })
}

export function loginUrl(returnTo = '/'): string {
  return `${apiBaseUrl}/auth/login?return_to=${encodeURIComponent(returnTo)}`
}

export async function logout(): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/auth/logout`, authenticatedInit({ method: 'POST' }))
  if (!response.ok) throw await apiError(response)
}

export function createOrganisation(name: string, slug: string): Promise<AuthOrganisation> {
  return requestJson('/api/v1/organisations', authenticatedInit({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, slug }) }))
}

export async function switchOrganisation(organisationId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organisations/active`, authenticatedInit({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ organisation_id: organisationId }) }))
  if (!response.ok) throw await apiError(response)
}

export async function acceptInvitation(token: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organisations/invitations/accept`, authenticatedInit({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) }))
  if (!response.ok) throw await apiError(response)
}

export function getOrganisationMembers(signal?: AbortSignal): Promise<OrganisationMember[]> {
  return requestJson('/api/v1/organisations/active/members', { signal })
}

export function getInvitations(signal?: AbortSignal): Promise<OrganisationInvitation[]> {
  return requestJson('/api/v1/organisations/active/invitations', { signal })
}

export function inviteMember(email: string, role: 'OWNER' | 'MEMBER'): Promise<OrganisationInvitation> {
  return requestJson('/api/v1/organisations/active/invitations', authenticatedInit({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, role }) }))
}

export async function revokeInvitation(id: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organisations/active/invitations/${encodeURIComponent(id)}`, authenticatedInit({ method: 'DELETE' }))
  if (!response.ok) throw await apiError(response)
}

export async function updateMemberRole(userId: string, role: 'OWNER' | 'MEMBER'): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organisations/active/members/${encodeURIComponent(userId)}`, authenticatedInit({ method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role }) }))
  if (!response.ok) throw await apiError(response)
}

export async function removeMember(userId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/organisations/active/members/${encodeURIComponent(userId)}`, authenticatedInit({ method: 'DELETE' }))
  if (!response.ok) throw await apiError(response)
}

async function apiError(response: Response): Promise<RegBridgeApiError> {
  let envelope: ErrorEnvelope = {}
  try {
    envelope = (await response.json()) as ErrorEnvelope
  } catch {
    // A controlled fallback is safer than exposing raw response bodies.
  }
  return new RegBridgeApiError(
    envelope.error?.code ?? 'API_ERROR',
    envelope.error?.message ?? 'RegBridge could not complete the request.',
    response.status,
  )
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson('/api/v1/health', { signal })
}

export async function getRegPacks(signal?: AbortSignal): Promise<RegPackSummary[]> {
  const response = await requestJson<{ packs: RegPackSummary[] }>('/api/v1/regpacks', { signal })
  return response.packs
    .filter((pack) => pack.workflow_versions.length > 0)
    .map((pack) => ({ ...pack, versions: pack.workflow_versions }))
}

export function getRegPackDetail(
  packId: string,
  version: string,
  signal?: AbortSignal,
): Promise<RegPackDetail> {
  return requestJson(`/api/v1/regpacks/${encodeURIComponent(packId)}/versions/${encodeURIComponent(version)}`, { signal })
}

export function getRegPackSchema(
  packId: string,
  version: string,
  signal?: AbortSignal,
): Promise<CanonicalSchema> {
  return requestJson(`/api/v1/regpacks/${encodeURIComponent(packId)}/versions/${encodeURIComponent(version)}/schema`, { signal })
}

export function getRegPackWorkflow(
  packId: string,
  version: string,
  signal?: AbortSignal,
): Promise<RegPackWorkflow> {
  return requestJson(`/api/v1/regpacks/${encodeURIComponent(packId)}/versions/${encodeURIComponent(version)}/workflow`, { signal })
}

export function getImportLimits(signal?: AbortSignal): Promise<ImportLimits> {
  return requestJson('/api/v1/imports/limits', { signal })
}

function sourceForm(file: File, sheetName?: string | null, headerRow?: number): FormData {
  const form = new FormData()
  form.append('file', file)
  if (sheetName) form.append('sheet_name', sheetName)
  if (headerRow !== undefined) form.append('header_row', String(headerRow))
  return form
}

function workflowForm(
  file: File,
  packId: string,
  version: string,
  mapping: ImportMapping,
  persistence?: { runId: string; expectedRevision: number },
): FormData {
  const form = sourceForm(file)
  form.append('pack_id', packId)
  form.append('pack_version', version)
  form.append('mapping', JSON.stringify(mapping))
  if (persistence) {
    form.append('run_id', persistence.runId)
    form.append('expected_revision', String(persistence.expectedRevision))
  }
  return form
}

function sectionWorkflowForm(
  file: File,
  packId: string,
  version: string,
  mapping: WorkflowImportMapping,
  runtimeValues?: Record<string, string>,
  persistence?: { runId: string; expectedRevision: number },
): FormData {
  const form = sourceForm(file)
  form.append('pack_id', packId)
  form.append('pack_version', version)
  form.append('mapping', JSON.stringify(mapping))
  if (runtimeValues) form.append('runtime_values', JSON.stringify(runtimeValues))
  if (persistence) {
    form.append('run_id', persistence.runId)
    form.append('expected_revision', String(persistence.expectedRevision))
  }
  return form
}

export function inspectSource(
  file: File,
  sheetName: string | null,
  headerRow: number,
  signal?: AbortSignal,
  persistence?: { runId: string; expectedRevision: number; packId: string; packVersion: string },
): Promise<SourceFileInspection> {
  const form = sourceForm(file, sheetName, headerRow)
  if (persistence) {
    form.append('run_id', persistence.runId)
    form.append('expected_revision', String(persistence.expectedRevision))
    form.append('pack_id', persistence.packId)
    form.append('pack_version', persistence.packVersion)
  }
  return requestJson('/api/v1/imports/inspect', {
    method: 'POST',
    body: form,
    signal,
  })
}

export function mapSource(
  file: File,
  packId: string,
  version: string,
  mapping: ImportMapping,
  signal?: AbortSignal,
  persistence?: {
    runId: string; expectedRevision: number; saveProfile: boolean
    baseProfileId?: string | null; profileDisplayName?: string | null
    recommendationOrigins?: Record<string, string>
  },
): Promise<ImportResult> {
  const form = workflowForm(file, packId, version, mapping, persistence)
  if (persistence) {
    form.append('save_mapping_profile', String(persistence.saveProfile))
    if (persistence.baseProfileId) form.append('base_profile_id', persistence.baseProfileId)
    if (persistence.profileDisplayName) form.append('profile_display_name', persistence.profileDisplayName)
    form.append('recommendation_origins', JSON.stringify(persistence.recommendationOrigins ?? {}))
  }
  return requestJson('/api/v1/imports/map', {
    method: 'POST',
    body: form,
    signal,
  })
}

export function mapSectionedSource(
  file: File,
  packId: string,
  version: string,
  mapping: WorkflowImportMapping,
  signal?: AbortSignal,
): Promise<WorkflowImportResult> {
  return requestJson('/api/v1/imports/map-sections', {
    method: 'POST', body: sectionWorkflowForm(file, packId, version, mapping), signal,
  })
}

export function runPreflight(
  file: File,
  packId: string,
  version: string,
  mapping: ImportMapping,
  signal?: AbortSignal,
  persistence?: { runId: string; expectedRevision: number },
): Promise<RegFlowPreflightResult> {
  return requestJson('/api/v1/regflow/preflight', {
    method: 'POST',
    body: workflowForm(file, packId, version, mapping, persistence),
    signal,
  })
}

export function runSectionedPreflight(
  file: File,
  packId: string,
  version: string,
  mapping: WorkflowImportMapping,
  runtimeValues: Record<string, string>,
  signal?: AbortSignal,
  persistence?: {
    runId: string; expectedRevision: number; saveProfiles: boolean
    recommendationOrigins: Record<string, Record<string, string>>
  },
): Promise<WorkflowPreflightResult> {
  const form = sectionWorkflowForm(file, packId, version, mapping, runtimeValues, persistence)
  if (persistence) {
    form.append('save_mapping_profiles', String(persistence.saveProfiles))
    form.append('recommendation_origins', JSON.stringify(persistence.recommendationOrigins))
  }
  return requestJson('/api/v1/regflow/preflight-sections', {
    method: 'POST', body: form, signal,
  })
}

export async function generateSectionedOutput(
  file: File,
  packId: string,
  version: string,
  mapping: WorkflowImportMapping,
  runtimeValues: Record<string, string>,
  signal?: AbortSignal,
  persistence?: { runId: string; expectedRevision: number; idempotencyKey: string },
): Promise<GeneratedFile> {
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}/api/v1/outputs/generate-sections`, authenticatedInit({
      method: 'POST',
      body: sectionWorkflowForm(file, packId, version, mapping, runtimeValues, persistence),
      headers: persistence ? { 'Idempotency-Key': persistence.idempotencyKey } : undefined,
      signal,
    }))
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new RegBridgeApiError('CONNECTION_ERROR', 'RegBridge could not connect to the API.', 0)
  }
  if (!response.ok) throw await apiError(response)
  return {
    blob: await response.blob(),
    filename: safeDownloadFilename(response.headers.get('content-disposition')),
    artifactId: response.headers.get('x-regbridge-artifact-id'),
    sha256: response.headers.get('x-regbridge-artifact-sha256'),
    runId: response.headers.get('x-regbridge-run-id'),
    runState: response.headers.get('x-regbridge-run-state') as RunState | null,
    runRevision: response.headers.get('x-regbridge-run-revision') ? Number(response.headers.get('x-regbridge-run-revision')) : null,
  }
}

export async function generateOutput(
  file: File,
  packId: string,
  version: string,
  mapping: ImportMapping,
  signal?: AbortSignal,
  persistence?: { runId: string; expectedRevision: number; idempotencyKey: string },
): Promise<GeneratedFile> {
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}/api/v1/outputs/generate`, authenticatedInit({
      method: 'POST',
      body: workflowForm(file, packId, version, mapping, persistence),
      headers: persistence ? { 'Idempotency-Key': persistence.idempotencyKey } : undefined,
      signal,
    }))
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new RegBridgeApiError('CONNECTION_ERROR', 'RegBridge could not connect to the API.', 0)
  }
  if (!response.ok) throw await apiError(response)
  return {
    blob: await response.blob(),
    filename: safeDownloadFilename(response.headers.get('content-disposition')),
    artifactId: response.headers.get('x-regbridge-artifact-id'),
    sha256: response.headers.get('x-regbridge-artifact-sha256'),
    runId: response.headers.get('x-regbridge-run-id'),
    runState: response.headers.get('x-regbridge-run-state') as RunState | null,
    runRevision: response.headers.get('x-regbridge-run-revision') ? Number(response.headers.get('x-regbridge-run-revision')) : null,
  }
}

export function createRun(packId: string, version: string, idempotencyKey: string): Promise<RunDetail> {
  return requestJson('/api/v1/regflow/runs', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ pack_id: packId, pack_version: version }),
  })
}

export function getRuns(signal?: AbortSignal): Promise<RunSummary[]> {
  return requestJson<{ runs: RunSummary[] }>('/api/v1/regflow/runs?limit=50', { signal }).then((value) => value.runs)
}

export function getRun(runId: string, signal?: AbortSignal): Promise<RunDetail> {
  return requestJson(`/api/v1/regflow/runs/${encodeURIComponent(runId)}`, { signal })
}

export async function deleteRun(runId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/regflow/runs/${encodeURIComponent(runId)}`, authenticatedInit({ method: 'DELETE' }))
  if (!response.ok) throw await apiError(response)
}

export function matchMappingProfiles(
  packId: string, version: string, schemaId: string, schemaVersion: string,
  signature: string, signal?: AbortSignal, sectionId?: string,
): Promise<MappingProfileVersion[]> {
  const query = new URLSearchParams({
    pack_id: packId, pack_version: version, canonical_schema_id: schemaId,
    canonical_schema_version: schemaVersion, source_header_signature: signature,
  })
  if (sectionId) query.set('section_id', sectionId)
  return requestJson<{ profiles: MappingProfileVersion[] }>(`/api/v1/mapping-profiles/match?${query}`, { signal }).then((value) => value.profiles)
}

export function getMappingProfiles(signal?: AbortSignal): Promise<MappingProfileSummary[]> {
  return requestJson<{ profiles: MappingProfileSummary[] }>('/api/v1/mapping-profiles', { signal }).then((value) => value.profiles)
}

export async function deleteMappingProfile(profileId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/mapping-profiles/${encodeURIComponent(profileId)}`, authenticatedInit({ method: 'DELETE' }))
  if (!response.ok) throw await apiError(response)
}

export function safeDownloadFilename(contentDisposition: string | null): string {
  const match = contentDisposition?.match(/filename="([^"\r\n]+)"/i)
  const candidate = match?.[1]
  if (!candidate || candidate.includes('/') || candidate.includes('\\') || candidate.includes('..')) {
    return 'regbridge-output.xlsx'
  }
  const safe = candidate
    .replace(/[<>:"/\\|?*]/g, '_')
    .split('')
    .map((character) => character.charCodeAt(0) < 32 ? '_' : character)
    .join('')
    .replace(/[. ]+$/, '')
  return safe.toLowerCase().endsWith('.xlsx') && safe.length <= 180
    ? safe
    : 'regbridge-output.xlsx'
}

export function downloadGeneratedFile(file: GeneratedFile): void {
  const url = URL.createObjectURL(file.blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = file.filename
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}
