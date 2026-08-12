import { apiRequest } from "@/lib/api-wrapper"
import { getApiUrl } from "@/lib/utils"

export interface LoopEvalTotals {
  run_count: number
  case_count: number
  result_count: number
  passed: number
  failed: number
  pass_rate: number
}

export interface LoopEvalGroupMetric {
  key?: string | number | boolean | null
  loop_type?: string
  run_count?: number
  case_count?: number
  result_count?: number
  passed: number
  failed: number
  pass_rate: number
}

export interface LoopEvalRun {
  id: string
  background_job_id: string | null
  run_id: string
  dataset_version: string | null
  agent_id: number
  api_base: string | null
  worker_api_base: string | null
  dry_run: boolean
  case_count: number
  passed: number
  failed: number
  pass_rate: number
  report_path: string
  by_loop: Record<string, unknown>
  budget: Record<string, unknown>
  summary: Record<string, unknown>
  created_at_source: string | null
  created_at: string | null
  updated_at: string | null
}

export interface LoopEvalResult {
  id: number
  eval_run_id: string
  case_id: string
  loop_type: string | null
  dataset_version: string | null
  task_id: number | null
  passed: boolean
  score: number | null
  transport: Record<string, unknown>
  judge: Record<string, unknown>
  tags: Record<string, unknown>
  result_path: string
  raw_output_path: string | null
  failed_case_path: string | null
  created_at: string | null
  updated_at: string | null
}

export interface LoopEvalMetrics {
  filters: {
    agent_id: number | null
    dataset_version: string | null
    dry_run: boolean | null
    created_from: string | null
    created_to: string | null
  }
  totals: LoopEvalTotals
  by_loop: LoopEvalGroupMetric[]
  by_dataset: LoopEvalGroupMetric[]
  by_agent: LoopEvalGroupMetric[]
  by_dry_run: LoopEvalGroupMetric[]
  recent_runs: LoopEvalRun[]
  outcomes?: SelectionOutcomeMetrics
}

export interface SelectionOutcomeConfusion {
  evaluated: number
  skipped: number
  true_positive: number
  true_negative: number
  false_positive: number
  false_negative: number
  false_positive_rate: number
  false_negative_rate: number
  precision: number
  recall: number
}

export interface SelectionOutcomeMetrics {
  outcome_count: number
  by_actual_outcome: Array<{ key: string; count: number }>
  by_agent_recommendation: Array<{ key: string; count: number }>
  confusion: SelectionOutcomeConfusion
}

export interface SelectionProfile {
  id: string
  name: string
  job_family: string | null
  job_title: string | null
  level: string | null
  locale: string | null
  profile: Record<string, unknown>
  source_type: string
  privacy_level: string
  synthetic: boolean
  version: number
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface SelectionProfilesResponse {
  total: number
  limit: number
  offset: number
  profiles: SelectionProfile[]
}

export interface SelectionCase {
  id: string
  profile_id: string | null
  case_id: string
  loop_type: string | null
  dataset_version: string | null
  case_path: string | null
  prompt_path: string | null
  prompt_text: string | null
  quality_passed: boolean | null
  tags: Record<string, unknown>
  expected_output: Record<string, unknown>
  case: Record<string, unknown>
  source_type: string
  privacy_level: string
  synthetic: boolean
  version: number
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface SelectionCasesResponse {
  total: number
  limit: number
  offset: number
  cases: SelectionCase[]
}

export interface SelectionOutcome {
  id: string
  eval_run_id: string | null
  case_id: string
  candidate_id: string | null
  loop_type: string | null
  dataset_version: string | null
  agent_recommendation: string | null
  actual_outcome: string | null
  hired: boolean | null
  offer_accepted: boolean | null
  performance_rating: number | null
  retention_days: number | null
  outcome_date: string | null
  source_type: string
  privacy_level: string
  synthetic: boolean
  import_batch_id: string | null
  version: number
  notes: string | null
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface SelectionOutcomesResponse {
  total: number
  limit: number
  offset: number
  outcomes: SelectionOutcome[]
}

export interface SelectionOutcomesImportResponse {
  import_batch_id: string
  imported_count: number
  outcomes: SelectionOutcome[]
}

export interface LoopEvalRunsResponse {
  total: number
  limit: number
  offset: number
  runs: LoopEvalRun[]
}

export interface LoopEvalResultsResponse {
  eval_run_id: string
  total: number
  limit: number
  offset: number
  results: LoopEvalResult[]
}

export interface LoopEvalTraceTask {
  id: number
  title: string
  status: string
  is_visible: boolean
  created_at: string | null
  updated_at: string | null
}

export interface LoopEvalTraceEvent {
  id: number
  task_id: number
  build_id: string | null
  event_id: string
  event_type: string
  loop_event_type: string | null
  timestamp: string | null
  step_id: string | null
  parent_event_id: string | null
  data: Record<string, unknown>
}

export interface LoopEvalTraceResponse {
  eval_run_id: string
  trace_task_id: number | null
  task: LoopEvalTraceTask | null
  total: number
  events: LoopEvalTraceEvent[]
}

export interface LoopEvalBudgetStatus {
  available: boolean
  reason?: string
  active: Array<{
    scope: string
    job: string | null
    ttl_seconds: number
  }>
  totals: Record<string, number>
  db?: {
    totals: Record<string, number>
    scopes: Array<Record<string, unknown>>
  }
}

export interface LoopEvalRunSelectionResponse {
  mode?: "background"
  job_id?: string
  job_status?: string
  queue?: string
  eval_run_id?: string
  trace_task_id?: number
  selected_case_ids?: string[] | null
  new_task_count?: number
  max_new_tasks?: number
  pass_rate?: number
  passed?: number
  failed?: number
  case_count?: number
}

export interface LoopEvalMetricsParams {
  agentId?: string
  datasetVersion?: string
  dryRun?: "all" | "true" | "false"
  recentLimit?: number
}

async function requestJson<T>(path: string): Promise<T> {
  const response = await apiRequest(`${getApiUrl()}${path}`)
  if (!response.ok) {
    const message = await response.text().catch(() => "")
    throw new Error(message || `Request failed with ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function getLoopEvalMetrics(params: LoopEvalMetricsParams = {}) {
  const search = new URLSearchParams()
  const agentId = params.agentId?.trim()
  const datasetVersion = params.datasetVersion?.trim()

  if (agentId) {
    search.set("agent_id", agentId)
  }
  if (datasetVersion) {
    search.set("dataset_version", datasetVersion)
  }
  if (params.dryRun && params.dryRun !== "all") {
    search.set("dry_run", params.dryRun)
  }
  if (params.recentLimit !== undefined) {
    search.set("recent_limit", String(params.recentLimit))
  }

  const suffix = search.toString() ? `?${search.toString()}` : ""
  return requestJson<LoopEvalMetrics>(`/api/loop-eval/db/metrics${suffix}`)
}

export function getLoopEvalRuns(limit = 20, offset = 0) {
  const search = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  return requestJson<LoopEvalRunsResponse>(`/api/loop-eval/db/runs?${search.toString()}`)
}

export function getLoopEvalResults(
  evalRunId: string,
  options: {
    limit?: number
    offset?: number
    loopType?: "loop1" | "loop2" | "loop3"
    passed?: boolean
  } = {}
) {
  const search = new URLSearchParams({
    limit: String(options.limit ?? 100),
    offset: String(options.offset ?? 0),
  })
  if (options.loopType) {
    search.set("loop_type", options.loopType)
  }
  if (options.passed !== undefined) {
    search.set("passed", String(options.passed))
  }
  return requestJson<LoopEvalResultsResponse>(
    `/api/loop-eval/db/runs/${encodeURIComponent(evalRunId)}/results?${search.toString()}`
  )
}

export function getLoopEvalTrace(evalRunId: string) {
  return requestJson<LoopEvalTraceResponse>(
    `/api/loop-eval/db/runs/${encodeURIComponent(evalRunId)}/trace`
  )
}

export function getLoopEvalBudgetStatus() {
  return requestJson<LoopEvalBudgetStatus>("/api/loop-eval/budget/status")
}

export async function runLoopEvalSelection(options: {
  datasetManifest: string
  outputSubdir?: string
  agentId: string
  selectionCaseIds?: string[]
  selectionProfileId?: string
  background?: boolean
}) {
  const body = {
    dataset_manifest: options.datasetManifest,
    output_subdir: options.outputSubdir?.trim() || undefined,
    agent_id: Number(options.agentId || 31),
    dry_run: true,
    selection_case_ids: options.selectionCaseIds?.length ? options.selectionCaseIds : undefined,
    selection_profile_id: options.selectionProfileId?.trim() || undefined,
    selection_cases_active_only: true,
    max_new_tasks: 0,
    background: Boolean(options.background),
  }
  const response = await apiRequest(`${getApiUrl()}/api/loop-eval/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const message = await response.text().catch(() => "")
    throw new Error(message || `Request failed with ${response.status}`)
  }
  return response.json() as Promise<LoopEvalRunSelectionResponse>
}

export function getSelectionProfiles(options: { limit?: number; isActive?: boolean } = {}) {
  const search = new URLSearchParams({
    limit: String(options.limit ?? 10),
    offset: "0",
  })
  if (options.isActive !== undefined) {
    search.set("is_active", String(options.isActive))
  }
  return requestJson<SelectionProfilesResponse>(`/api/selection-profiles?${search.toString()}`)
}

export function getSelectionCases(
  options: {
    limit?: number
    datasetVersion?: string
    isActive?: boolean
  } = {}
) {
  const search = new URLSearchParams({
    limit: String(options.limit ?? 10),
    offset: "0",
  })
  const datasetVersion = options.datasetVersion?.trim()
  if (datasetVersion) {
    search.set("dataset_version", datasetVersion)
  }
  if (options.isActive !== undefined) {
    search.set("is_active", String(options.isActive))
  }
  return requestJson<SelectionCasesResponse>(`/api/selection-cases?${search.toString()}`)
}

export function getSelectionOutcomes(
  options: {
    limit?: number
    datasetVersion?: string
    loopType?: "loop1" | "loop2" | "loop3"
    caseId?: string
  } = {}
) {
  const search = new URLSearchParams({
    limit: String(options.limit ?? 10),
    offset: "0",
  })
  const datasetVersion = options.datasetVersion?.trim()
  const caseId = options.caseId?.trim()
  if (datasetVersion) {
    search.set("dataset_version", datasetVersion)
  }
  if (options.loopType) {
    search.set("loop_type", options.loopType)
  }
  if (caseId) {
    search.set("case_id", caseId)
  }
  return requestJson<SelectionOutcomesResponse>(`/api/selection-outcomes?${search.toString()}`)
}

export async function importSelectionOutcomesCsv(
  file: File,
  options: {
    importBatchId?: string
    defaultDatasetVersion?: string
    defaultLoopType?: "loop1" | "loop2" | "loop3"
    defaultPrivacyLevel?: string
    defaultSynthetic?: boolean
  } = {}
) {
  const formData = new FormData()
  formData.append("file", file)
  const datasetVersion = options.defaultDatasetVersion?.trim()
  if (options.importBatchId?.trim()) {
    formData.append("import_batch_id", options.importBatchId.trim())
  }
  if (datasetVersion) {
    formData.append("default_dataset_version", datasetVersion)
  }
  if (options.defaultLoopType) {
    formData.append("default_loop_type", options.defaultLoopType)
  }
  if (options.defaultPrivacyLevel?.trim()) {
    formData.append("default_privacy_level", options.defaultPrivacyLevel.trim())
  }
  if (options.defaultSynthetic !== undefined) {
    formData.append("default_synthetic", String(options.defaultSynthetic))
  }

  const response = await apiRequest(`${getApiUrl()}/api/selection-outcomes/import-csv`, {
    method: "POST",
    body: formData,
  })
  if (!response.ok) {
    const message = await response.text().catch(() => "")
    throw new Error(message || `Request failed with ${response.status}`)
  }
  return response.json() as Promise<SelectionOutcomesImportResponse>
}
