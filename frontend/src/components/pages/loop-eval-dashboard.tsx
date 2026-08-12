"use client"

import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Briefcase,
  CheckCircle2,
  ClipboardCheck,
  Database,
  Eye,
  ExternalLink,
  FileText,
  Play,
  RefreshCw,
  Search,
  Target,
  Upload,
  XCircle,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { Select } from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  getLoopEvalMetrics,
  getLoopEvalResults,
  getLoopEvalTrace,
  getLoopEvalRuns,
  getLoopEvalBudgetStatus,
  getSelectionCases,
  getSelectionOutcomes,
  getSelectionProfiles,
  importSelectionOutcomesCsv,
  runLoopEvalSelection,
  type LoopEvalBudgetStatus,
  type LoopEvalGroupMetric,
  type LoopEvalMetrics,
  type LoopEvalResult,
  type LoopEvalRun,
  type LoopEvalTraceEvent,
  type LoopEvalTraceResponse,
  type SelectionCase,
  type SelectionOutcome,
  type SelectionProfile,
} from "@/lib/loop-eval-api"
import { cn } from "@/lib/utils"

type DryRunFilter = "all" | "true" | "false"

interface MetricTileProps {
  label: string
  value: string
  sublabel: string
  icon: React.ComponentType<{ className?: string }>
  tone: string
}

function MetricTile({ label, value, sublabel, icon: Icon, tone }: MetricTileProps) {
  return (
    <Card className="gap-3 rounded-lg border-[rgba(255,255,255,0.08)] bg-[#161B22] p-5 py-5 shadow-none">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm text-[#8B949E]">{label}</p>
          <p className="mt-2 truncate text-2xl font-semibold text-[#E6EDF3]">{value}</p>
        </div>
        <span className={cn("rounded-md p-2", tone)}>
          <Icon className="h-5 w-5" />
        </span>
      </div>
      <p className="truncate text-xs text-[#8B949E]">{sublabel}</p>
    </Card>
  )
}

function formatPercent(value: number | undefined | null) {
  return `${Math.round((value || 0) * 1000) / 10}%`
}

function formatDateTime(value: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function compactLabel(value: unknown) {
  if (value === null || value === undefined || value === "") return "-"
  return String(value)
}

function groupLabel(metric: LoopEvalGroupMetric) {
  if (metric.loop_type) return metric.loop_type
  if (metric.key === true) return "dry-run"
  if (metric.key === false) return "real HTTP"
  if (metric.key === null || metric.key === undefined || metric.key === "") return "unknown"
  return String(metric.key)
}

function countFor(metric: LoopEvalGroupMetric) {
  return metric.result_count ?? metric.case_count ?? metric.run_count ?? 0
}

function tagsSummary(tags: Record<string, unknown>) {
  const entries = Object.entries(tags || {}).filter(([, value]) => value !== undefined && value !== null && value !== "")
  if (entries.length === 0) return "-"
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${key}=${compactLabel(value)}`)
    .join(" / ")
}

function byLoopOrder(metric: LoopEvalGroupMetric) {
  const label = groupLabel(metric)
  if (label === "loop1") return 1
  if (label === "loop2") return 2
  if (label === "loop3") return 3
  return 9
}

function traceEventLabel(event: LoopEvalTraceEvent) {
  return event.loop_event_type || event.event_type
}

function traceEventSummary(event: LoopEvalTraceEvent) {
  const data = event.data || {}
  const keys = [
    "job_id",
    "job_status",
    "queue",
    "case_count",
    "passed",
    "failed",
    "pass_rate",
    "new_task_count",
    "max_new_tasks",
    "error_message",
  ]
  const parts = keys
    .filter((key) => data[key] !== undefined && data[key] !== null && data[key] !== "")
    .map((key) => `${key}=${formatTraceValue(data[key])}`)

  if (Array.isArray(data.selected_case_ids)) {
    parts.push(`selected=${data.selected_case_ids.length}`)
  }
  if (Array.isArray(data.case_ids)) {
    parts.push(`cases=${data.case_ids.length}`)
  }
  return parts.join(" / ")
}

function formatTraceValue(value: unknown) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : String(Math.round(value * 1000) / 1000)
  }
  if (typeof value === "string") {
    return value.length > 80 ? `${value.slice(0, 77)}...` : value
  }
  return JSON.stringify(value)
}

function formatJsonBlock(value: unknown) {
  if (!value || (typeof value === "object" && Object.keys(value as Record<string, unknown>).length === 0)) {
    return "{}"
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function LoopEvalDashboardPage() {
  const [metrics, setMetrics] = useState<LoopEvalMetrics | null>(null)
  const [budgetStatus, setBudgetStatus] = useState<LoopEvalBudgetStatus | null>(null)
  const [runs, setRuns] = useState<LoopEvalRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [results, setResults] = useState<LoopEvalResult[]>([])
  const [trace, setTrace] = useState<LoopEvalTraceResponse | null>(null)
  const [profiles, setProfiles] = useState<SelectionProfile[]>([])
  const [profileTotal, setProfileTotal] = useState(0)
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null)
  const [cases, setCases] = useState<SelectionCase[]>([])
  const [caseTotal, setCaseTotal] = useState(0)
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const [selectedCaseOutcomes, setSelectedCaseOutcomes] = useState<SelectionOutcome[]>([])
  const [outcomes, setOutcomes] = useState<SelectionOutcome[]>([])
  const [outcomeTotal, setOutcomeTotal] = useState(0)
  const outcomeCsvInputRef = useRef<HTMLInputElement | null>(null)
  const [datasetManifest, setDatasetManifest] = useState("dataset_manifest.json")
  const [evalOutputSubdir, setEvalOutputSubdir] = useState("")
  const [agentId, setAgentId] = useState("31")
  const [datasetVersion, setDatasetVersion] = useState("")
  const [dryRun, setDryRun] = useState<DryRunFilter>("all")
  const [isLoading, setIsLoading] = useState(true)
  const [isResultsLoading, setIsResultsLoading] = useState(false)
  const [isTraceLoading, setIsTraceLoading] = useState(false)
  const [isOutcomeImporting, setIsOutcomeImporting] = useState(false)
  const [isCaseOutcomesLoading, setIsCaseOutcomesLoading] = useState(false)
  const [isSelectionEvalRunning, setIsSelectionEvalRunning] = useState(false)
  const [isProfileEvalRunning, setIsProfileEvalRunning] = useState(false)
  const [selectionEvalMessage, setSelectionEvalMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) || metrics?.recent_runs.find((run) => run.id === selectedRunId) || null,
    [metrics?.recent_runs, runs, selectedRunId]
  )

  const failedResults = useMemo(
    () => results.filter((result) => !result.passed),
    [results]
  )

  const selectedCase = useMemo(
    () => cases.find((loopCase) => loopCase.id === selectedCaseId) || null,
    [cases, selectedCaseId]
  )

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedProfileId) || null,
    [profiles, selectedProfileId]
  )

  const selectedCaseResults = useMemo(
    () => selectedCase ? results.filter((result) => result.case_id === selectedCase.case_id) : [],
    [results, selectedCase]
  )

  const refreshDashboard = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [metricsData, runsData, budgetData, profilesData, casesData, outcomesData] = await Promise.all([
        getLoopEvalMetrics({
          agentId,
          datasetVersion,
          dryRun,
          recentLimit: 10,
        }),
        getLoopEvalRuns(20, 0),
        getLoopEvalBudgetStatus(),
        getSelectionProfiles({ limit: 6, isActive: true }),
        getSelectionCases({ limit: 8, datasetVersion, isActive: true }),
        getSelectionOutcomes({ limit: 8, datasetVersion }),
      ])
      setMetrics(metricsData)
      setRuns(runsData.runs)
      setBudgetStatus(budgetData)
      setProfiles(profilesData.profiles)
      setProfileTotal(profilesData.total)
      setSelectedProfileId((current) => {
        if (current && profilesData.profiles.some((profile) => profile.id === current)) {
          return current
        }
        return profilesData.profiles[0]?.id || null
      })
      setCases(casesData.cases)
      setCaseTotal(casesData.total)
      setOutcomes(outcomesData.outcomes)
      setOutcomeTotal(outcomesData.total)
      setSelectedCaseId((current) => {
        if (current && casesData.cases.some((loopCase) => loopCase.id === current)) {
          return current
        }
        return casesData.cases[0]?.id || null
      })
      setSelectedRunId((current) => {
        if (current && runsData.runs.some((run) => run.id === current)) {
          return current
        }
        return metricsData.recent_runs[0]?.id || runsData.runs[0]?.id || null
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load loop evaluation data")
    } finally {
      setIsLoading(false)
    }
  }, [agentId, datasetVersion, dryRun])

  useEffect(() => {
    refreshDashboard()
  }, [refreshDashboard])

  const importOutcomeCsv = useCallback(
    async (file: File) => {
      setIsOutcomeImporting(true)
      setError(null)
      try {
        await importSelectionOutcomesCsv(file, {
          defaultDatasetVersion: datasetVersion,
          defaultPrivacyLevel: "synthetic",
          defaultSynthetic: true,
        })
        await refreshDashboard()
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to import outcome CSV")
      } finally {
        setIsOutcomeImporting(false)
      }
    },
    [datasetVersion, refreshDashboard]
  )

  const onOutcomeCsvSelected = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      event.target.value = ""
      if (file) {
        void importOutcomeCsv(file)
      }
    },
    [importOutcomeCsv]
  )

  const runSelectedCaseEval = useCallback(async () => {
    if (!selectedCase) return
    setIsSelectionEvalRunning(true)
    setSelectionEvalMessage(null)
    setError(null)
    try {
      const response = await runLoopEvalSelection({
        datasetManifest,
        outputSubdir: evalOutputSubdir,
        agentId,
        selectionCaseIds: [selectedCase.id],
      })
      setSelectionEvalMessage(
        response.eval_run_id
          ? `eval_run=${response.eval_run_id}`
          : response.job_id
            ? `job=${response.job_id}`
            : "eval started"
      )
      await refreshDashboard()
      if (response.eval_run_id) {
        setSelectedRunId(response.eval_run_id)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run selection case eval")
    } finally {
      setIsSelectionEvalRunning(false)
    }
  }, [agentId, datasetManifest, evalOutputSubdir, refreshDashboard, selectedCase])

  const runSelectedProfileEval = useCallback(async () => {
    if (!selectedProfile) return
    setIsProfileEvalRunning(true)
    setSelectionEvalMessage(null)
    setError(null)
    try {
      const response = await runLoopEvalSelection({
        datasetManifest,
        outputSubdir: evalOutputSubdir,
        agentId,
        selectionProfileId: selectedProfile.id,
      })
      setSelectionEvalMessage(
        response.eval_run_id
          ? `profile eval_run=${response.eval_run_id}`
          : response.job_id
            ? `profile job=${response.job_id}`
            : "profile eval started"
      )
      await refreshDashboard()
      if (response.eval_run_id) {
        setSelectedRunId(response.eval_run_id)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run selection profile eval")
    } finally {
      setIsProfileEvalRunning(false)
    }
  }, [agentId, datasetManifest, evalOutputSubdir, refreshDashboard, selectedProfile])

  useEffect(() => {
    if (!selectedRunId) {
      setResults([])
      setTrace(null)
      return
    }

    let cancelled = false
    setIsResultsLoading(true)
    setIsTraceLoading(true)
    getLoopEvalResults(selectedRunId, { limit: 100 })
      .then((data) => {
        if (!cancelled) {
          setResults(data.results)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load loop eval results")
          setResults([])
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsResultsLoading(false)
        }
      })

    getLoopEvalTrace(selectedRunId)
      .then((data) => {
        if (!cancelled) {
          setTrace(data)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load loop eval trace")
          setTrace(null)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsTraceLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [selectedRunId])

  useEffect(() => {
    if (!selectedCase) {
      setSelectedCaseOutcomes([])
      return
    }

    let cancelled = false
    setIsCaseOutcomesLoading(true)
    getSelectionOutcomes({
      limit: 20,
      datasetVersion: selectedCase.dataset_version || datasetVersion,
      caseId: selectedCase.case_id,
    })
      .then((data) => {
        if (!cancelled) {
          setSelectedCaseOutcomes(data.outcomes)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load case outcomes")
          setSelectedCaseOutcomes([])
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsCaseOutcomesLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [datasetVersion, selectedCase])

  const totals = metrics?.totals
  const loopMetrics = useMemo(
    () => [...(metrics?.by_loop || [])].sort((a, b) => byLoopOrder(a) - byLoopOrder(b)),
    [metrics?.by_loop]
  )
  const maxLoopCount = Math.max(1, ...loopMetrics.map(countFor))
  const outcomeConfusion = metrics?.outcomes?.confusion
  const budgetDbTotals = budgetStatus?.db?.totals || {}
  const registryDatasetLabel = datasetVersion.trim() || "all datasets"

  return (
    <div className="h-full overflow-auto bg-[#0E1117] text-[#E6EDF3]">
      <div className="space-y-6 p-6 lg:p-8">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm text-[#8B949E]">
              <Database className="h-4 w-4" />
              <span>Loop Eval DB</span>
            </div>
            <h1 className="mt-2 text-2xl font-semibold">Three Loops Evaluation</h1>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-[120px_minmax(200px,280px)_150px_auto]">
            <Input
              value={agentId}
              onChange={(event) => setAgentId(event.target.value)}
              placeholder="Agent ID"
              className="border-[rgba(255,255,255,0.12)] bg-[#161B22] text-[#E6EDF3]"
            />
            <Input
              value={datasetVersion}
              onChange={(event) => setDatasetVersion(event.target.value)}
              placeholder="Dataset version"
              className="border-[rgba(255,255,255,0.12)] bg-[#161B22] text-[#E6EDF3]"
            />
            <Select
              value={dryRun}
              onValueChange={(value) => setDryRun(value as DryRunFilter)}
              options={[
                { value: "all", label: "All runs" },
                { value: "false", label: "Real HTTP" },
                { value: "true", label: "Dry-run" },
              ]}
              className="text-[#E6EDF3]"
            />
            <Button onClick={refreshDashboard} disabled={isLoading} className="bg-[#2F81F7] text-white hover:bg-[#1f6feb]">
              <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span className="min-w-0 break-words">{error}</span>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
          <MetricTile
            label="Runs"
            value={isLoading ? "..." : String(totals?.run_count ?? 0)}
            sublabel={`${totals?.result_count ?? 0} persisted results`}
            icon={BarChart3}
            tone="bg-blue-500/10 text-blue-400"
          />
          <MetricTile
            label="Cases"
            value={isLoading ? "..." : String(totals?.case_count ?? 0)}
            sublabel={`${totals?.passed ?? 0} passed`}
            icon={Target}
            tone="bg-emerald-500/10 text-emerald-400"
          />
          <MetricTile
            label="Pass Rate"
            value={isLoading ? "..." : formatPercent(totals?.pass_rate)}
            sublabel={`${totals?.failed ?? 0} failed cases`}
            icon={CheckCircle2}
            tone="bg-lime-500/10 text-lime-400"
          />
          <MetricTile
            label="Failures"
            value={isLoading ? "..." : String(totals?.failed ?? 0)}
            sublabel={failedResults.length ? `${failedResults.length} in selected run` : "No selected-run failures"}
            icon={XCircle}
            tone="bg-red-500/10 text-red-400"
          />
          <MetricTile
            label="Budget"
            value={isLoading ? "..." : String(budgetDbTotals.new_tasks_planned ?? 0)}
            sublabel={`${budgetDbTotals.new_tasks_completed ?? 0} completed / ${budgetDbTotals.jobs_rejected_budget ?? 0} rejected`}
            icon={Activity}
            tone="bg-amber-500/10 text-amber-400"
          />
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <Card className="gap-0 rounded-lg border-[rgba(255,255,255,0.08)] bg-[#161B22] py-0 shadow-none">
            <div className="border-b border-[rgba(255,255,255,0.08)] px-5 py-4">
              <h2 className="text-base font-semibold">Loop Coverage</h2>
            </div>
            <div className="space-y-5 p-5">
              {loopMetrics.length === 0 ? (
                <p className="text-sm text-[#8B949E]">No loop metrics.</p>
              ) : (
                loopMetrics.map((metric) => {
                  const count = countFor(metric)
                  return (
                    <div key={groupLabel(metric)} className="space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="border-[rgba(255,255,255,0.14)] text-[#E6EDF3]">
                            {groupLabel(metric)}
                          </Badge>
                          <span className="text-sm text-[#8B949E]">{count} results</span>
                        </div>
                        <span className="text-sm text-[#E6EDF3]">{formatPercent(metric.pass_rate)}</span>
                      </div>
                      <Progress
                        value={(count / maxLoopCount) * 100}
                        className="bg-[#0E1117] [&>div]:bg-[#2F81F7]"
                      />
                    </div>
                  )
                })
              )}
            </div>
          </Card>

          <Card className="gap-0 rounded-lg border-[rgba(255,255,255,0.08)] bg-[#161B22] py-0 shadow-none">
            <div className="border-b border-[rgba(255,255,255,0.08)] px-5 py-4">
              <h2 className="text-base font-semibold">Dataset Groups</h2>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="border-[rgba(255,255,255,0.08)] hover:bg-transparent">
                  <TableHead className="text-[#8B949E]">Dataset</TableHead>
                  <TableHead className="text-right text-[#8B949E]">Runs</TableHead>
                  <TableHead className="text-right text-[#8B949E]">Cases</TableHead>
                  <TableHead className="text-right text-[#8B949E]">Pass</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(metrics?.by_dataset || []).slice(0, 6).map((metric) => (
                  <TableRow key={groupLabel(metric)} className="border-[rgba(255,255,255,0.08)] hover:bg-[#0E1117]">
                    <TableCell className="max-w-[260px] truncate text-[#E6EDF3]">{groupLabel(metric)}</TableCell>
                    <TableCell className="text-right text-[#8B949E]">{metric.run_count ?? 0}</TableCell>
                    <TableCell className="text-right text-[#8B949E]">{metric.case_count ?? 0}</TableCell>
                    <TableCell className="text-right text-[#E6EDF3]">{formatPercent(metric.pass_rate)}</TableCell>
                  </TableRow>
                ))}
                {!isLoading && (metrics?.by_dataset || []).length === 0 && (
                  <TableRow className="border-[rgba(255,255,255,0.08)]">
                    <TableCell colSpan={4} className="text-center text-[#8B949E]">No dataset groups.</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <Card className="gap-0 rounded-lg border-[rgba(255,255,255,0.08)] bg-[#161B22] py-0 shadow-none">
            <div className="flex items-center justify-between gap-3 border-b border-[rgba(255,255,255,0.08)] px-5 py-4">
              <div>
                <div className="flex items-center gap-2 text-sm text-[#8B949E]">
                  <Briefcase className="h-4 w-4" />
                  <span>Selection Profiles</span>
                </div>
                <p className="mt-1 text-sm text-[#8B949E]">
                  {selectedProfile ? selectedProfile.name : `${profileTotal} active profiles`}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!selectedProfile || isProfileEvalRunning}
                  onClick={runSelectedProfileEval}
                  className="border-[rgba(255,255,255,0.12)] bg-transparent text-[#E6EDF3] hover:bg-[#0E1117]"
                >
                  <Play className={cn("h-4 w-4", isProfileEvalRunning && "animate-pulse")} />
                  Profile
                </Button>
                <Badge className="bg-blue-500/10 text-blue-300">Active</Badge>
              </div>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="border-[rgba(255,255,255,0.08)] hover:bg-transparent">
                  <TableHead className="text-[#8B949E]">Name</TableHead>
                  <TableHead className="text-[#8B949E]">Family</TableHead>
                  <TableHead className="text-right text-[#8B949E]">Version</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {profiles.map((profile) => (
                  <TableRow
                    key={profile.id}
                    data-state={selectedProfileId === profile.id ? "selected" : undefined}
                    className="cursor-pointer border-[rgba(255,255,255,0.08)] hover:bg-[#0E1117] data-[state=selected]:bg-[#0E1117]"
                    onClick={() => setSelectedProfileId(profile.id)}
                  >
                    <TableCell className="max-w-[220px] truncate text-[#E6EDF3]">{profile.name}</TableCell>
                    <TableCell className="max-w-[160px] truncate text-[#8B949E]">
                      {profile.job_family || profile.job_title || "-"}
                    </TableCell>
                    <TableCell className="text-right text-[#8B949E]">v{profile.version}</TableCell>
                  </TableRow>
                ))}
                {!isLoading && profiles.length === 0 && (
                  <TableRow className="border-[rgba(255,255,255,0.08)]">
                    <TableCell colSpan={3} className="text-center text-[#8B949E]">No active profiles.</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>

          <Card className="gap-0 rounded-lg border-[rgba(255,255,255,0.08)] bg-[#161B22] py-0 shadow-none">
            <div className="flex items-center justify-between gap-3 border-b border-[rgba(255,255,255,0.08)] px-5 py-4">
              <div>
                <div className="flex items-center gap-2 text-sm text-[#8B949E]">
                  <FileText className="h-4 w-4" />
                  <span>Selection Cases</span>
                </div>
                <p className="mt-1 max-w-full truncate text-sm text-[#8B949E]">{caseTotal} active cases in {registryDatasetLabel}</p>
              </div>
              <Badge className="bg-emerald-500/10 text-emerald-300">Imported</Badge>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="border-[rgba(255,255,255,0.08)] hover:bg-transparent">
                  <TableHead className="text-[#8B949E]">Case</TableHead>
                  <TableHead className="text-[#8B949E]">Loop</TableHead>
                  <TableHead className="text-[#8B949E]">Tags</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cases.map((loopCase) => (
                  <TableRow
                    key={loopCase.id}
                    data-state={selectedCaseId === loopCase.id ? "selected" : undefined}
                    className="cursor-pointer border-[rgba(255,255,255,0.08)] hover:bg-[#0E1117] data-[state=selected]:bg-[#0E1117]"
                    onClick={() => setSelectedCaseId(loopCase.id)}
                  >
                    <TableCell className="max-w-[220px] truncate text-[#E6EDF3]">{loopCase.case_id}</TableCell>
                    <TableCell className="text-[#8B949E]">{loopCase.loop_type || "-"}</TableCell>
                    <TableCell className="max-w-[240px] truncate text-[#8B949E]">{tagsSummary(loopCase.tags)}</TableCell>
                  </TableRow>
                ))}
                {!isLoading && cases.length === 0 && (
                  <TableRow className="border-[rgba(255,255,255,0.08)]">
                    <TableCell colSpan={3} className="text-center text-[#8B949E]">No imported cases.</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>

          <Card className="gap-0 rounded-lg border-[rgba(255,255,255,0.08)] bg-[#161B22] py-0 shadow-none">
            <div className="flex items-center justify-between gap-3 border-b border-[rgba(255,255,255,0.08)] px-5 py-4">
              <div>
                <div className="flex items-center gap-2 text-sm text-[#8B949E]">
                  <ClipboardCheck className="h-4 w-4" />
                  <span>Outcome Feedback</span>
                </div>
                <p className="mt-1 text-sm text-[#8B949E]">{outcomeTotal} outcomes in {registryDatasetLabel}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <input
                  ref={outcomeCsvInputRef}
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={onOutcomeCsvSelected}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={isOutcomeImporting}
                  onClick={() => outcomeCsvInputRef.current?.click()}
                  className="border-[rgba(255,255,255,0.12)] bg-transparent text-[#E6EDF3] hover:bg-[#0E1117]"
                >
                  <Upload className={cn("h-4 w-4", isOutcomeImporting && "animate-pulse")} />
                  CSV
                </Button>
                <Badge className="bg-amber-500/10 text-amber-300">
                  FP {outcomeConfusion?.false_positive ?? 0} / FN {outcomeConfusion?.false_negative ?? 0}
                </Badge>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 border-b border-[rgba(255,255,255,0.08)] p-5">
              <div>
                <p className="text-xs text-[#8B949E]">Precision</p>
                <p className="mt-1 text-lg font-semibold text-[#E6EDF3]">{formatPercent(outcomeConfusion?.precision)}</p>
              </div>
              <div>
                <p className="text-xs text-[#8B949E]">Recall</p>
                <p className="mt-1 text-lg font-semibold text-[#E6EDF3]">{formatPercent(outcomeConfusion?.recall)}</p>
              </div>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="border-[rgba(255,255,255,0.08)] hover:bg-transparent">
                  <TableHead className="text-[#8B949E]">Case</TableHead>
                  <TableHead className="text-[#8B949E]">Agent</TableHead>
                  <TableHead className="text-[#8B949E]">Actual</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {outcomes.map((outcome) => (
                  <TableRow key={outcome.id} className="border-[rgba(255,255,255,0.08)] hover:bg-[#0E1117]">
                    <TableCell className="max-w-[180px] truncate text-[#E6EDF3]">{outcome.case_id}</TableCell>
                    <TableCell className="max-w-[130px] truncate text-[#8B949E]">{outcome.agent_recommendation || "-"}</TableCell>
                    <TableCell className="max-w-[130px] truncate text-[#8B949E]">{outcome.actual_outcome || "-"}</TableCell>
                  </TableRow>
                ))}
                {!isLoading && outcomes.length === 0 && (
                  <TableRow className="border-[rgba(255,255,255,0.08)]">
                    <TableCell colSpan={3} className="text-center text-[#8B949E]">No outcome feedback.</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </div>

        <Card className="gap-0 rounded-lg border-[rgba(255,255,255,0.08)] bg-[#161B22] py-0 shadow-none">
          <div className="flex flex-col gap-3 border-b border-[rgba(255,255,255,0.08)] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm text-[#8B949E]">
                <FileText className="h-4 w-4" />
                <span>Selection Case Drilldown</span>
              </div>
              <p className="mt-1 max-w-full truncate text-sm text-[#8B949E]">
                {selectedCase ? `${selectedCase.case_id} / ${selectedCase.dataset_version || "unknown dataset"}` : "No case selected"}
              </p>
            </div>
            {selectedCase ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge className="bg-emerald-500/10 text-emerald-300">{selectedCase.loop_type || "unknown"}</Badge>
                <Badge className={selectedCase.quality_passed === false ? "bg-red-500/10 text-red-300" : "bg-blue-500/10 text-blue-300"}>
                  {selectedCase.quality_passed === false ? "Gate failed" : "Gate ok"}
                </Badge>
                <Badge className="bg-amber-500/10 text-amber-300">{selectedCaseOutcomes.length} outcomes</Badge>
              </div>
            ) : null}
          </div>

          {selectedCase ? (
            <div className="grid grid-cols-1 gap-0 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <div className="space-y-4 border-b border-[rgba(255,255,255,0.08)] p-5 xl:border-b-0 xl:border-r">
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  <div>
                    <p className="text-xs text-[#8B949E]">Profile</p>
                    <p className="mt-1 truncate text-sm text-[#E6EDF3]">{selectedCase.profile_id || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-[#8B949E]">Source</p>
                    <p className="mt-1 truncate text-sm text-[#E6EDF3]">{selectedCase.source_type}</p>
                  </div>
                  <div>
                    <p className="text-xs text-[#8B949E]">Privacy</p>
                    <p className="mt-1 truncate text-sm text-[#E6EDF3]">{selectedCase.privacy_level}</p>
                  </div>
                </div>
                <div>
                  <p className="text-xs text-[#8B949E]">Tags</p>
                  <pre className="mt-2 max-h-[160px] overflow-auto rounded-md bg-[#0E1117] p-3 text-xs leading-5 text-[#C9D1D9]">
                    {formatJsonBlock(selectedCase.tags)}
                  </pre>
                </div>
                <div>
                  <p className="text-xs text-[#8B949E]">Expected Output</p>
                  <pre className="mt-2 max-h-[220px] overflow-auto rounded-md bg-[#0E1117] p-3 text-xs leading-5 text-[#C9D1D9]">
                    {formatJsonBlock(selectedCase.expected_output)}
                  </pre>
                </div>
              </div>

              <div className="space-y-4 p-5">
                <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                  <Input
                    value={datasetManifest}
                    onChange={(event) => setDatasetManifest(event.target.value)}
                    placeholder="Dataset manifest"
                    className="border-[rgba(255,255,255,0.12)] bg-[#0E1117] text-[#E6EDF3]"
                  />
                  <Input
                    value={evalOutputSubdir}
                    onChange={(event) => setEvalOutputSubdir(event.target.value)}
                    placeholder="Output subdir"
                    className="border-[rgba(255,255,255,0.12)] bg-[#0E1117] text-[#E6EDF3]"
                  />
                  <Button
                    type="button"
                    disabled={isSelectionEvalRunning}
                    onClick={runSelectedCaseEval}
                    className="bg-[#2F81F7] text-white hover:bg-[#1f6feb]"
                  >
                    <Play className={cn("h-4 w-4", isSelectionEvalRunning && "animate-pulse")} />
                    Dry-run
                  </Button>
                </div>
                {selectionEvalMessage ? (
                  <p className="truncate rounded-md bg-[#0E1117] px-3 py-2 text-sm text-[#8B949E]">{selectionEvalMessage}</p>
                ) : null}
                <div>
                  <p className="text-xs text-[#8B949E]">Prompt</p>
                  <pre className="mt-2 max-h-[180px] overflow-auto whitespace-pre-wrap rounded-md bg-[#0E1117] p-3 text-xs leading-5 text-[#C9D1D9]">
                    {selectedCase.prompt_text || "-"}
                  </pre>
                </div>
                <div>
                  <p className="text-xs text-[#8B949E]">Current Run Result</p>
                  <div className="mt-2 space-y-2">
                    {selectedCaseResults.map((result) => (
                      <div key={result.id} className="flex items-center justify-between gap-3 rounded-md bg-[#0E1117] px-3 py-2 text-sm">
                        <span className="min-w-0 truncate text-[#8B949E]">task {result.task_id ?? "-"}</span>
                        <Badge className={result.passed ? "bg-emerald-500/10 text-emerald-300" : "bg-red-500/10 text-red-300"}>
                          {result.passed ? "Passed" : "Failed"}
                        </Badge>
                      </div>
                    ))}
                    {!isResultsLoading && selectedCaseResults.length === 0 && (
                      <p className="rounded-md bg-[#0E1117] px-3 py-2 text-sm text-[#8B949E]">No result in selected run.</p>
                    )}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-[#8B949E]">Outcome Feedback</p>
                  <div className="mt-2 space-y-2">
                    {selectedCaseOutcomes.map((outcome) => (
                      <div key={outcome.id} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3 rounded-md bg-[#0E1117] px-3 py-2 text-sm">
                        <span className="truncate text-[#8B949E]">{outcome.agent_recommendation || "-"}</span>
                        <span className="truncate text-[#E6EDF3]">{outcome.actual_outcome || "-"}</span>
                      </div>
                    ))}
                    {isCaseOutcomesLoading && (
                      <p className="rounded-md bg-[#0E1117] px-3 py-2 text-sm text-[#8B949E]">Loading outcomes...</p>
                    )}
                    {!isCaseOutcomesLoading && selectedCaseOutcomes.length === 0 && (
                      <p className="rounded-md bg-[#0E1117] px-3 py-2 text-sm text-[#8B949E]">No outcome feedback for this case.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-5 text-sm text-[#8B949E]">No selection case loaded.</div>
          )}
        </Card>

        <Card className="gap-0 rounded-lg border-[rgba(255,255,255,0.08)] bg-[#161B22] py-0 shadow-none">
          <div className="flex flex-col gap-3 border-b border-[rgba(255,255,255,0.08)] px-5 py-4 md:flex-row md:items-center md:justify-between">
            <h2 className="text-base font-semibold">Recent Runs</h2>
            <div className="flex items-center gap-2 text-sm text-[#8B949E]">
              <Search className="h-4 w-4" />
              <span>{runs.length} loaded</span>
            </div>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="border-[rgba(255,255,255,0.08)] hover:bg-transparent">
                <TableHead className="text-[#8B949E]">Run</TableHead>
                <TableHead className="text-[#8B949E]">Dataset</TableHead>
                <TableHead className="text-right text-[#8B949E]">Cases</TableHead>
                <TableHead className="text-right text-[#8B949E]">Pass</TableHead>
                <TableHead className="text-[#8B949E]">Mode</TableHead>
                <TableHead className="text-[#8B949E]">Created</TableHead>
                <TableHead className="w-[76px] text-right text-[#8B949E]">View</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((run) => (
                <TableRow
                  key={run.id}
                  data-state={selectedRunId === run.id ? "selected" : undefined}
                  className="border-[rgba(255,255,255,0.08)] hover:bg-[#0E1117] data-[state=selected]:bg-[#0E1117]"
                >
                  <TableCell className="max-w-[180px] truncate font-mono text-xs text-[#E6EDF3]">{run.id}</TableCell>
                  <TableCell className="max-w-[260px] truncate text-[#8B949E]">{run.dataset_version || "-"}</TableCell>
                  <TableCell className="text-right text-[#8B949E]">{run.case_count}</TableCell>
                  <TableCell className="text-right text-[#E6EDF3]">{formatPercent(run.pass_rate)}</TableCell>
                  <TableCell>
                    <Badge className={run.dry_run ? "bg-sky-500/10 text-sky-300" : "bg-emerald-500/10 text-emerald-300"}>
                      {run.dry_run ? "Dry-run" : "Real HTTP"}
                    </Badge>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-[#8B949E]">{formatDateTime(run.created_at)}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" onClick={() => setSelectedRunId(run.id)} title="View results">
                      <Eye className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!isLoading && runs.length === 0 && (
                <TableRow className="border-[rgba(255,255,255,0.08)]">
                  <TableCell colSpan={7} className="text-center text-[#8B949E]">No runs found.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Card>

        <Card className="gap-0 rounded-lg border-[rgba(255,255,255,0.08)] bg-[#161B22] py-0 shadow-none">
          <div className="flex flex-col gap-3 border-b border-[rgba(255,255,255,0.08)] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm text-[#8B949E]">
                <Activity className="h-4 w-4" />
                <span>Trace Events</span>
              </div>
              <p className="mt-1 max-w-full truncate text-sm text-[#8B949E]">
                {trace?.trace_task_id ? `Task #${trace.trace_task_id} / ${trace.total} events` : "No trace task linked"}
              </p>
            </div>
            {trace?.trace_task_id ? (
              <Button asChild variant="outline" className="border-[rgba(255,255,255,0.12)] bg-transparent text-[#E6EDF3] hover:bg-[#0E1117]">
                <Link href={`/task/${trace.trace_task_id}`}>
                  <ExternalLink className="h-4 w-4" />
                  Open task
                </Link>
              </Button>
            ) : null}
          </div>
          <Table>
            <TableHeader>
              <TableRow className="border-[rgba(255,255,255,0.08)] hover:bg-transparent">
                <TableHead className="text-[#8B949E]">Time</TableHead>
                <TableHead className="text-[#8B949E]">Event</TableHead>
                <TableHead className="text-[#8B949E]">Step</TableHead>
                <TableHead className="text-[#8B949E]">Summary</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(trace?.events || []).map((event) => (
                <TableRow key={event.id} className="border-[rgba(255,255,255,0.08)] hover:bg-[#0E1117]">
                  <TableCell className="whitespace-nowrap text-[#8B949E]">{formatDateTime(event.timestamp)}</TableCell>
                  <TableCell className="max-w-[220px] truncate text-[#E6EDF3]">{traceEventLabel(event)}</TableCell>
                  <TableCell className="max-w-[220px] truncate font-mono text-xs text-[#8B949E]">{event.step_id || "-"}</TableCell>
                  <TableCell className="max-w-[520px] truncate text-[#8B949E]">{traceEventSummary(event) || "-"}</TableCell>
                </TableRow>
              ))}
              {isTraceLoading && (
                <TableRow className="border-[rgba(255,255,255,0.08)]">
                  <TableCell colSpan={4} className="text-center text-[#8B949E]">Loading trace...</TableCell>
                </TableRow>
              )}
              {!isTraceLoading && selectedRunId && (trace?.events || []).length === 0 && (
                <TableRow className="border-[rgba(255,255,255,0.08)]">
                  <TableCell colSpan={4} className="text-center text-[#8B949E]">No trace events for this run.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Card>

        <Card className="gap-0 rounded-lg border-[rgba(255,255,255,0.08)] bg-[#161B22] py-0 shadow-none">
          <div className="flex flex-col gap-2 border-b border-[rgba(255,255,255,0.08)] px-5 py-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-base font-semibold">Selected Run Results</h2>
              <p className="mt-1 max-w-full truncate text-sm text-[#8B949E]">
                {selectedRun ? `${selectedRun.dataset_version || "unknown dataset"} / ${selectedRun.id}` : "No run selected"}
              </p>
            </div>
            {failedResults.length > 0 ? (
              <Badge className="bg-red-500/10 text-red-300">{failedResults.length} failed</Badge>
            ) : (
              <Badge className="bg-emerald-500/10 text-emerald-300">No failures</Badge>
            )}
          </div>
          <Table>
            <TableHeader>
              <TableRow className="border-[rgba(255,255,255,0.08)] hover:bg-transparent">
                <TableHead className="text-[#8B949E]">Case</TableHead>
                <TableHead className="text-[#8B949E]">Loop</TableHead>
                <TableHead className="text-right text-[#8B949E]">Score</TableHead>
                <TableHead className="text-[#8B949E]">Task</TableHead>
                <TableHead className="text-[#8B949E]">Status</TableHead>
                <TableHead className="text-[#8B949E]">Failure Archive</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.map((result) => (
                <TableRow key={result.id} className="border-[rgba(255,255,255,0.08)] hover:bg-[#0E1117]">
                  <TableCell className="max-w-[300px] truncate text-[#E6EDF3]">{result.case_id}</TableCell>
                  <TableCell className="text-[#8B949E]">{result.loop_type || "-"}</TableCell>
                  <TableCell className="text-right text-[#8B949E]">{result.score ?? "-"}</TableCell>
                  <TableCell className="font-mono text-xs text-[#8B949E]">{result.task_id ?? "-"}</TableCell>
                  <TableCell>
                    <Badge className={result.passed ? "bg-emerald-500/10 text-emerald-300" : "bg-red-500/10 text-red-300"}>
                      {result.passed ? "Passed" : "Failed"}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-[260px] truncate text-[#8B949E]">{result.failed_case_path || "-"}</TableCell>
                </TableRow>
              ))}
              {isResultsLoading && (
                <TableRow className="border-[rgba(255,255,255,0.08)]">
                  <TableCell colSpan={6} className="text-center text-[#8B949E]">Loading results...</TableCell>
                </TableRow>
              )}
              {!isResultsLoading && selectedRunId && results.length === 0 && (
                <TableRow className="border-[rgba(255,255,255,0.08)]">
                  <TableCell colSpan={6} className="text-center text-[#8B949E]">No results for this run.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Card>
      </div>
    </div>
  )
}
