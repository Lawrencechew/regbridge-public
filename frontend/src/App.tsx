import { useCallback, useEffect, useReducer, useRef, useState } from 'react'

import { AppNavigation } from './components/platform/AppNavigation'
import { HelpStatusPage } from './components/platform/HelpStatusPage'
import { HomePage } from './components/platform/HomePage'
import { RegPackCatalogue } from './components/platform/RegPackCatalogue'
import { RunsPage } from './components/platform/RunsPage'
import { LoginPage, OrganisationOnboarding } from './components/platform/AuthBoundary'
import { OrganisationPage } from './components/platform/OrganisationPage'
import { CompletionPanel } from './components/regflow/CompletionPanel'
import { FileAndInspection } from './components/regflow/FileAndInspection'
import { MappingTable } from './components/regflow/MappingTable'
import { PackSelector } from './components/regflow/PackSelector'
import { PreflightPanel } from './components/regflow/PreflightPanel'
import { RegFlowStepper } from './components/regflow/RegFlowStepper'
import { SectionedRegFlow } from './components/regflow/SectionedRegFlow'
import { routeFromPath, routePaths, type AppRoute } from './platform/navigation'
import { buildImportMapping, initialWorkflowState, workflowReducer } from './regflow/workflow'
import {
  createRun, downloadGeneratedFile, generateOutput, getHealth, getImportLimits,
  getRegPackDetail, getRegPackWorkflow, getRegPacks, getRun, inspectSource,
  getSession, logout, mapSource, matchMappingProfiles, RegBridgeApiError,
  runPreflight, switchOrganisation,
} from './services/api'
import type { AuthSession, ImportLimits, RegPackSummary, RunDetail } from './types/regflow'
import './styles.css'

type Operation = 'pack' | 'run' | 'inspect' | 'map' | 'preflight' | 'generate' | null

function userMessage(error: unknown): string {
  if (error instanceof RegBridgeApiError) return error.message
  return 'RegBridge could not complete this step. Try again or check the API connection.'
}

function App() {
  const [route, setRoute] = useState<AppRoute>(() => routeFromPath(window.location.pathname))
  const [state, dispatch] = useReducer(workflowReducer, initialWorkflowState)
  const [packs, setPacks] = useState<RegPackSummary[]>([])
  const [limits, setLimits] = useState<ImportLimits | null>(null)
  const [connected, setConnected] = useState<boolean | null>(null)
  const [version, setVersion] = useState<string | null>(null)
  const [session, setSession] = useState<AuthSession | null>(null)
  const [operation, setOperation] = useState<Operation>(null)
  const [error, setError] = useState<string | null>(null)
  const inspectController = useRef<AbortController | null>(null)
  const packController = useRef<AbortController | null>(null)
  const reportPageError = useCallback((caught: unknown) => setError(userMessage(caught)), [])

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([getHealth(controller.signal), getRegPacks(controller.signal), getSession(controller.signal)])
      .then(async ([health, loadedPacks, loadedSession]) => {
        setConnected(true)
        setVersion(health.version)
        setPacks(loadedPacks)
        setSession(loadedSession)
        if (!loadedSession.auth_enabled || loadedSession.authenticated) {
          setLimits(await getImportLimits(controller.signal))
        }
      })
      .catch((caught: unknown) => {
        if (!(caught instanceof DOMException && caught.name === 'AbortError')) {
          setConnected(false)
          setSession({ auth_enabled: true, authenticated: false, user: null, active_organisation: null, organisations: [] })
          setError(userMessage(caught))
        }
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const titles: Record<AppRoute, string> = {
      home: 'RegBridge · Regulatory last-mile platform',
      regflow: 'Prepare Return · RegBridge',
      runs: 'Runs · RegBridge',
      regpacks: 'RegPacks · RegBridge',
      organisation: 'Organisation · RegBridge',
      help: 'Help & Status · RegBridge',
    }
    document.title = titles[route]
  }, [route])

  useEffect(() => {
    function followBrowserHistory() { setRoute(routeFromPath(window.location.pathname)) }
    window.addEventListener('popstate', followBrowserHistory)
    return () => window.removeEventListener('popstate', followBrowserHistory)
  }, [])

  function navigate(nextRoute: AppRoute) {
    const path = routePaths[nextRoute]
    if (window.location.pathname !== path || window.location.search) window.history.pushState({}, '', path)
    setRoute(nextRoute)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function loadPackMetadata(pack: RegPackSummary, version: string) {
    packController.current?.abort()
    const controller = new AbortController()
    packController.current = controller
    setOperation('pack')
    setError(null)
    try {
      const [detail, workflow] = await Promise.all([
        getRegPackDetail(pack.id, version, controller.signal),
        getRegPackWorkflow(pack.id, version, controller.signal),
      ])
      dispatch({ type: 'PACK_METADATA_READY', detail, workflow })
    } catch (caught: unknown) {
      if (!(caught instanceof DOMException && caught.name === 'AbortError')) setError(userMessage(caught))
    } finally {
      if (packController.current === controller) setOperation(null)
    }
  }

  async function handleOperationError(caught: unknown) {
    if (caught instanceof RegBridgeApiError && caught.status === 401) {
      setSession((current) => current ? { ...current, authenticated: false, user: null, active_organisation: null, organisations: [] } : current)
    }
    if (caught instanceof RegBridgeApiError && caught.code === 'RUN_REVISION_CONFLICT' && state.run) {
      try {
        const current = await getRun(state.run.id)
        const pack = packs.find((candidate) => candidate.id === current.pack.id)
        if (pack) dispatch({ type: 'RUN_RESTORED', run: current, pack })
      } catch {
        // Keep the original controlled concurrency message.
      }
    }
    setError(userMessage(caught))
  }

  async function performInspection(file: File, sheetName: string | null, headerRow: number) {
    inspectController.current?.abort()
    const controller = new AbortController()
    inspectController.current = controller
    setOperation('inspect')
    setError(null)
    try {
      const inspection = await inspectSource(
        file, sheetName, headerRow, controller.signal,
        state.run && state.pack ? {
          runId: state.run.id, expectedRevision: state.run.revision,
          packId: state.pack.id, packVersion: state.version,
        } : undefined,
      )
      dispatch({ type: 'INSPECTION_READY', inspection })
      if (state.pack && state.schema && !inspection.selection_required) {
        const profiles = await matchMappingProfiles(
          state.pack.id, state.version, state.schema.id, state.schema.version,
          inspection.source_header_signature, controller.signal,
        )
        dispatch({ type: 'MAPPING_PROFILES_MATCHED', profiles })
      }
    } catch (caught: unknown) {
      if (!(caught instanceof DOMException && caught.name === 'AbortError')) await handleOperationError(caught)
    } finally {
      if (inspectController.current === controller) setOperation(null)
    }
  }

  function selectFile(file: File) {
    inspectController.current?.abort()
    dispatch({ type: 'FILE_SELECTED', file })
    void performInspection(file, null, 1)
  }

  function changeInspection(sheetName: string | null, rawHeaderRow: number) {
    if (!state.file) return
    const minimum = limits?.min_header_row ?? 1
    const maximum = limits?.max_header_row ?? 50
    const headerRow = Math.min(maximum, Math.max(minimum, Number.isFinite(rawHeaderRow) ? rawHeaderRow : 1))
    dispatch({ type: 'INSPECTION_OPTIONS_CHANGED', sheetName, headerRow })
    void performInspection(state.file, sheetName, headerRow)
  }

  function currentMapping() {
    if (!state.schema) throw new Error('A RegPack schema is required.')
    return buildImportMapping(state.schema, state.mappings, state.sheetName, state.headerRow)
  }

  async function checkMapping() {
    if (!state.file || !state.pack) return
    setOperation('map')
    setError(null)
    try {
      const origins = Object.fromEntries(
        Object.entries(state.mappings)
          .filter(([, draft]) => draft.matchKind !== null)
          .map(([fieldId, draft]) => [fieldId, draft.matchKind!]),
      )
      const result = await mapSource(
        state.file, state.pack.id, state.version, currentMapping(), undefined,
        state.run ? {
          runId: state.run.id, expectedRevision: state.run.revision,
          saveProfile: state.saveMappingProfile,
          baseProfileId: state.appliedProfile?.profile_id,
          profileDisplayName: state.appliedProfile?.display_name ?? `${state.pack.name} mapping`,
          recommendationOrigins: origins,
        } : undefined,
      )
      dispatch({ type: 'MAPPING_CHECKED', result })
    } catch (caught: unknown) { await handleOperationError(caught) }
    finally { setOperation(null) }
  }

  async function preflight() {
    if (!state.file || !state.pack) return
    setOperation('preflight')
    setError(null)
    try {
      const result = await runPreflight(
        state.file, state.pack.id, state.version, currentMapping(), undefined,
        state.run ? { runId: state.run.id, expectedRevision: state.run.revision } : undefined,
      )
      dispatch({ type: 'PREFLIGHT_READY', result })
    } catch (caught: unknown) { await handleOperationError(caught) }
    finally { setOperation(null) }
  }

  async function generate() {
    if (!state.file || !state.pack || !state.preflight?.can_generate) return
    const currentPreflight = state.preflight
    dispatch({ type: 'GENERATION_STARTED' })
    setOperation('generate')
    setError(null)
    try {
      const generated = await generateOutput(
        state.file, state.pack.id, state.version, currentMapping(), undefined,
        state.run ? {
          runId: state.run.id, expectedRevision: state.run.revision,
          idempotencyKey: crypto.randomUUID(),
        } : undefined,
      )
      dispatch({ type: 'GENERATION_READY', generated })
      downloadGeneratedFile(generated)
    } catch (caught: unknown) {
      dispatch({ type: 'PREFLIGHT_READY', result: currentPreflight })
      await handleOperationError(caught)
    } finally { setOperation(null) }
  }

  function selectPack(pack: RegPackSummary) {
    inspectController.current?.abort()
    setError(null)
    dispatch({ type: 'SELECT_PACK', pack })
    if (pack.versions.length === 1) void loadPackMetadata(pack, pack.versions[0])
  }

  function selectVersion(version: string) {
    dispatch({ type: 'SELECT_VERSION', version })
    if (state.pack && version) void loadPackMetadata(state.pack, version)
  }

  function startRegFlow(pack?: RegPackSummary) {
    if (pack) selectPack(pack)
    navigate('regflow')
  }

  async function commitPack() {
    if (!state.pack || !state.version) return
    setOperation('run')
    setError(null)
    try {
      const run = await createRun(state.pack.id, state.version, crypto.randomUUID())
      dispatch({ type: 'RUN_CREATED', run })
      window.history.replaceState({}, '', `/regflow?run=${encodeURIComponent(run.id)}`)
    } catch (caught) { await handleOperationError(caught) }
    finally { setOperation(null) }
  }

  async function resumeRun(run: RunDetail) {
    const pack = packs.find((candidate) => candidate.id === run.pack.id)
    if (!pack) {
      setError('The exact RegPack version for this historical run is not currently available.')
      return
    }
    dispatch({ type: 'RUN_RESTORED', run, pack })
    window.history.pushState({}, '', `/regflow?run=${encodeURIComponent(run.id)}`)
    setRoute('regflow')
    await loadPackMetadata(pack, run.pack.version)
  }

  async function changeOrganisation(organisationId: string) {
    if (!session?.authenticated || organisationId === session.active_organisation?.id) return
    setError(null)
    try {
      await switchOrganisation(organisationId)
      dispatch({ type: 'START_NEW' })
      setSession(await getSession())
      setLimits(await getImportLimits())
      window.history.replaceState({}, '', '/')
      setRoute('home')
    } catch (caught) { await handleOperationError(caught) }
  }

  async function signOut() {
    setError(null)
    try {
      await logout()
      dispatch({ type: 'START_NEW' })
      setLimits(null)
      setSession((current) => ({ auth_enabled: current?.auth_enabled ?? true, authenticated: false, user: null, active_organisation: null, organisations: [] }))
      window.history.replaceState({}, '', '/')
      setRoute('home')
    } catch (caught) { await handleOperationError(caught) }
  }

  useEffect(() => {
    if (packs.length === 0 || state.run) return
    const runId = new URLSearchParams(window.location.search).get('run')
    if (!runId || route !== 'regflow') return
    const controller = new AbortController()
    getRun(runId, controller.signal)
      .then((run) => {
        const pack = packs.find((candidate) => candidate.id === run.pack.id)
        if (!pack) throw new Error('The historical RegPack is unavailable.')
        dispatch({ type: 'RUN_RESTORED', run, pack })
        return loadPackMetadata(pack, run.pack.version)
      })
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === 'AbortError')) setError(userMessage(caught))
      })
    return () => controller.abort()
  }, [packs, route, state.run])

  if (session === null) return <main className="auth-shell"><section className="auth-card"><span className="brand-mark">RB</span><p>Connecting securely to RegBridge…</p></section></main>
  if (session.auth_enabled && !session.authenticated) return <LoginPage />
  if (session.auth_enabled && !session.active_organisation) return <OrganisationOnboarding onCreated={() => window.location.assign('/')} />

  return (
    <div className="app-shell">
      <AppNavigation route={route} connected={connected} onNavigate={navigate} session={session} onSwitchOrganisation={(organisationId) => void changeOrganisation(organisationId)} onLogout={() => void signOut()} />
      <main className="app-main">
        {error && <div className="global-error" role="alert"><strong>RegBridge needs your attention</strong><span>{error}</span><button type="button" onClick={() => setError(null)} aria-label="Dismiss error">×</button></div>}
        {route === 'home' && <HomePage packs={packs} connected={connected} onStart={() => startRegFlow()} onBrowsePacks={() => navigate('regpacks')} />}
        {route === 'regpacks' && <RegPackCatalogue packs={packs} connected={connected} onPrepare={startRegFlow} />}
        {route === 'runs' && <RunsPage onResume={(run) => void resumeRun(run)} onError={reportPageError} />}
        {route === 'organisation' && <OrganisationPage session={session} onError={reportPageError} />}
        {route === 'help' && <HelpStatusPage connected={connected} limits={limits} onStart={() => startRegFlow()} />}
        {route === 'regflow' && <div className="regflow-page">
          <section className="intro intro--workflow">
            <div><p className="eyebrow">Prepare return</p><h1>Build a regulator-ready return with fewer manual errors.</h1><p>Select a RegPack, inspect your source, verify recommended mappings, run preflight, and generate the regulator-prescribed output.</p></div>
            <aside><strong>{state.run ? `Run ${state.run.id.slice(0, 8)}… · revision ${state.run.revision}` : 'Persistent workflow metadata'}</strong><span>Source files and generated workbooks remain transient. Safe metadata and confirmed mappings persist.</span></aside>
          </section>
          {state.run && !state.file && state.run.source.display_name && <div className="notice notice--review"><strong>Resume requires the source file</strong><span>Metadata for {state.run.source.display_name} was restored. RegBridge deliberately did not retain the file; reselect it to continue. A changed file can invalidate downstream state.</span></div>}
          {!(state.workflow && (state.workflow.sections.length > 1 || state.workflow.runtime_fields.length > 0) && state.step !== 'select') && <RegFlowStepper step={state.step} />}
          {state.step === 'select' && <PackSelector packs={packs} selected={state.pack} version={state.version} detail={state.packDetail} loading={operation === 'pack' || operation === 'run'} onSelect={selectPack} onVersion={selectVersion} onContinue={() => void commitPack()} />}
          {state.workflow && (state.workflow.sections.length > 1 || state.workflow.runtime_fields.length > 0) && state.step !== 'select' && state.pack && state.packDetail && <SectionedRegFlow pack={state.pack} version={state.version} detail={state.packDetail} workflow={state.workflow} run={state.run} limits={limits} onRunMutation={(runState, revision) => dispatch({ type: 'RUN_MUTATED', state: runState, revision })} onError={(caught) => void handleOperationError(caught)} onStartNew={() => { dispatch({ type: 'START_NEW' }); window.history.replaceState({}, '', '/regflow') }} />}
          {(!state.workflow || (state.workflow.sections.length === 1 && state.workflow.runtime_fields.length === 0)) && <>
            {(state.step === 'upload' || state.step === 'inspect') && <FileAndInspection file={state.file} inspection={state.inspection} limits={limits} sheetName={state.sheetName} headerRow={state.headerRow} loading={operation === 'inspect'} onFile={selectFile} onRemove={() => dispatch({ type: 'FILE_REMOVED' })} onOptions={changeInspection} onContinue={() => dispatch({ type: 'GO_TO_MAP' })} />}
            {state.step === 'map' && state.schema && state.inspection && <MappingTable schema={state.schema} inspection={state.inspection} drafts={state.mappings} result={state.mappingResult} loading={operation === 'map' || operation === 'preflight' ? operation : null} matchedProfiles={state.matchedProfiles} appliedProfile={state.appliedProfile} saveMappingProfile={state.saveMappingProfile} onChange={(fieldId, draft) => dispatch({ type: 'MAPPING_CHANGED', fieldId, draft })} onApplyRecommendations={() => dispatch({ type: 'APPLY_MAPPING_RECOMMENDATIONS' })} onApplySavedProfile={(profile) => dispatch({ type: 'APPLY_SAVED_MAPPING', profile })} onSaveMappingProfile={(value) => dispatch({ type: 'SET_SAVE_MAPPING_PROFILE', value })} onCheck={() => void checkMapping()} onPreflight={() => void preflight()} onBack={() => dispatch({ type: 'GO_TO_UPLOAD' })} />}
            {(state.step === 'preflight' || state.step === 'generate') && state.preflight && state.packDetail && <PreflightPanel result={state.preflight} detail={state.packDetail} generating={operation === 'generate'} onGenerate={() => void generate()} onRunAgain={() => void preflight()} onBack={() => dispatch({ type: 'GO_TO_MAPPING' })} />}
            {state.step === 'complete' && state.generated && state.preflight && state.packDetail && <CompletionPanel generated={state.generated} preflight={state.preflight} detail={state.packDetail} onDownload={() => downloadGeneratedFile(state.generated!)} onStartNew={() => { dispatch({ type: 'START_NEW' }); window.history.replaceState({}, '', '/regflow') }} />}
          </>}
        </div>}
      </main>
      <footer className="app-footer"><span><strong>RegBridge</strong>{version ? ` v${version}` : ''} · Regulatory last-mile platform</span><span>Deterministic evaluation · Tenant-isolated audit history · Human-reviewed submission</span></footer>
    </div>
  )
}

export default App
