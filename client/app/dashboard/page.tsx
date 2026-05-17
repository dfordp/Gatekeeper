// client/app/dashboard/page.tsx
"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import DashboardLayout from "@/components/dashboard/DashboardLayout"
import TicketsTable from "@/components/dashboard/TicketsTable"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock,
  FileCheck2,
  Loader2,
  ShieldAlert,
  TrendingUp,
} from "lucide-react"

interface Ticket {
  id: string
  ticket_no: string
  subject: string
  status: string
  created_at: string
  closed_at?: string | null
  level?: string | null
  company_name?: string | null
  created_by?: string | null
}

interface AttentionTicket {
  id: string
  ticket_no: string
  subject: string
  status: string
  level?: string | null
  company_name?: string | null
  age_days: number
}

interface CompanyHealth {
  company_name: string
  total: number
  open: number
  closed: number
  with_ir: number
  closure_rate_percent: number
  avg_resolution_hours: number
}

interface CategoryPerformance {
  category: string
  total: number
  open: number
  closed: number
  closure_rate_percent: number
  avg_resolution_hours: number
}

interface TrendPoint {
  date: string
  created: number
  closed: number
  net: number
}

interface QualityMetrics {
  rca_count: number
  resolution_note_count: number
  closed_missing_rca: number
  closed_missing_resolution: number
  rca_completion_rate_percent: number
  resolution_note_completion_rate_percent: number
}

interface Analytics {
  total_tickets: number
  open_tickets: number
  in_progress: number
  resolved: number
  closed: number
  reopened: number
  avg_resolution_time_hours: number
  median_resolution_time_hours: number
  resolution_rate_percent: number
  categories: Record<string, number>
  levels: Record<string, number>
  aging_buckets: Record<string, number>
  needs_attention: AttentionTicket[]
  stale_tickets_count: number
  open_irs: number
  overdue_irs: number
  quality: QualityMetrics
  company_health: CompanyHealth[]
  category_performance: CategoryPerformance[]
  trends: TrendPoint[]
}

const formatHours = (hours?: number) => {
  if (!hours) return "0h"
  if (hours < 24) return `${Math.round(hours)}h`
  const days = Math.floor(hours / 24)
  const remainingHours = Math.round(hours % 24)
  return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`
}

const formatPercent = (value?: number) => `${Number(value || 0).toFixed(1)}%`

const ProgressBar = ({ value, tone = "bg-blue-600" }: { value: number; tone?: string }) => (
  <div className="h-2 w-full rounded bg-gray-100">
    <div className={`h-2 rounded ${tone}`} style={{ width: `${Math.min(value, 100)}%` }} />
  </div>
)

const MetricCard = ({
  title,
  value,
  detail,
  icon: Icon,
  tone,
}: {
  title: string
  value: string | number
  detail: string
  icon: React.ComponentType<{ className?: string }>
  tone: string
}) => (
  <Card>
    <CardHeader className="flex flex-row items-center justify-between space-y-0 px-4 pb-2 pt-4">
      <CardTitle className="text-sm font-medium text-gray-600">{title}</CardTitle>
      <Icon className={`h-4 w-4 ${tone}`} />
    </CardHeader>
    <CardContent className="px-4 pb-4">
      <div className="text-2xl font-semibold text-gray-950">{value}</div>
      <p className="mt-1 text-sm text-gray-500">{detail}</p>
    </CardContent>
  </Card>
)

const RankedBarList = ({
  rows,
  valueKey,
  labelKey,
}: {
  rows: Array<Record<string, string | number>>
  valueKey: string
  labelKey: string
}) => {
  const max = Math.max(...rows.map((row) => Number(row[valueKey] || 0)), 1)

  return (
    <div className="space-y-4">
      {rows.map((row) => {
        const value = Number(row[valueKey] || 0)
        return (
          <div key={String(row[labelKey])} className="space-y-1">
            <div className="flex items-center justify-between gap-4">
              <span className="truncate text-sm font-medium text-gray-800">{row[labelKey]}</span>
              <span className="text-sm text-gray-500">{value}</span>
            </div>
            <ProgressBar value={(value / max) * 100} />
          </div>
        )
      })}
    </div>
  )
}

export default function DashboardPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading } = useAuth()
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [analyticsLoading, setAnalyticsLoading] = useState(true)
  const [ticketsLoading, setTicketsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isLoading, router])

  const fetchAnalytics = useCallback(async () => {
    try {
      setError(null)
      const token = localStorage.getItem("auth_token")
      const response = await fetch("/api/dashboard/analytics?days=365", {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error("Failed to fetch analytics")
      setAnalytics(await response.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
      setAnalytics(null)
    } finally {
      setAnalyticsLoading(false)
    }
  }, [])

  const fetchTickets = useCallback(async () => {
    try {
      setError(null)
      const token = localStorage.getItem("auth_token")
      const response = await fetch("/api/dashboard/tickets?limit=12", {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error("Failed to fetch tickets")
      const data = await response.json()
      setTickets(data.tickets || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
      setTickets([])
    } finally {
      setTicketsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isAuthenticated) {
      fetchAnalytics()
      fetchTickets()
    }
  }, [isAuthenticated, fetchAnalytics, fetchTickets])

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  if (!isAuthenticated) return null

  const openRiskCount = Object.entries(analytics?.aging_buckets || {})
    .filter(([bucket]) => bucket === "8-14 days" || bucket === "15+ days")
    .reduce((sum, [, count]) => sum + count, 0)
  const quality = analytics?.quality
  const trendTotals = analytics?.trends?.reduce(
    (totals, point) => ({
      created: totals.created + point.created,
      closed: totals.closed + point.closed,
    }),
    { created: 0, closed: 0 }
  )
  const monthlyTrend = Object.values(
    (analytics?.trends || []).reduce<Record<string, { month: string; created: number; closed: number }>>(
      (months, point) => {
        const month = point.date.slice(0, 7)
        if (!months[month]) {
          months[month] = { month, created: 0, closed: 0 }
        }
        months[month].created += point.created
        months[month].closed += point.closed
        return months
      },
      {}
    )
  ).filter((point) => point.created > 0 || point.closed > 0)
  const trendMax = Math.max(...monthlyTrend.map((point) => Math.max(point.created, point.closed)), 1)

  return (
    <DashboardLayout>
      <div className="space-y-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-950">Support Health</h1>
            <p className="text-gray-600">
              Operational risk, customer load, and knowledge quality across the support desk.
            </p>
          </div>
          <Button asChild variant="outline">
            <Link href="/dashboard/tickets">
              Open Ticket Queue <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {analyticsLoading ? (
          <div className="flex h-40 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                title="Open Backlog"
                value={analytics?.open_tickets || 0}
                detail={`${analytics?.in_progress || 0} in progress, ${analytics?.reopened || 0} reopened`}
                icon={Clock}
                tone="text-orange-600"
              />
              <MetricCard
                title="Aging Risk"
                value={openRiskCount}
                detail={`${analytics?.stale_tickets_count || 0} inactive for 7+ days`}
                icon={AlertTriangle}
                tone="text-red-600"
              />
              <MetricCard
                title="Resolution"
                value={formatPercent(analytics?.resolution_rate_percent)}
                detail={`Median ${formatHours(analytics?.median_resolution_time_hours)}`}
                icon={CheckCircle2}
                tone="text-green-600"
              />
              <MetricCard
                title="Vendor Exposure"
                value={analytics?.open_irs || 0}
                detail={`${analytics?.overdue_irs || 0} IRs past expected date`}
                icon={ShieldAlert}
                tone="text-blue-600"
              />
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
              <Card className="xl:col-span-3">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="h-5 w-5" />
                    Created vs Closed, last 365 days
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="mb-4 grid grid-cols-3 gap-4">
                    <div>
                      <p className="text-sm text-gray-500">Created</p>
                      <p className="text-2xl font-semibold">{trendTotals?.created || 0}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Closed</p>
                      <p className="text-2xl font-semibold">{trendTotals?.closed || 0}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Net Backlog</p>
                      <p className="text-2xl font-semibold">
                        {(trendTotals?.created || 0) - (trendTotals?.closed || 0)}
                      </p>
                    </div>
                  </div>
                  <div className="flex h-28 items-end gap-4 border-b border-gray-100 pb-2">
                    {monthlyTrend.length === 0 ? (
                      <div className="flex h-full flex-1 items-center justify-center text-sm text-gray-500">
                        No created or closed tickets in this period.
                      </div>
                    ) : (
                      monthlyTrend.map((point) => (
                        <div key={point.month} className="flex min-w-16 flex-1 flex-col items-center gap-2">
                          <div className="flex h-20 w-full items-end justify-center gap-1">
                            <div
                              className="w-4 rounded-t bg-blue-500"
                              title={`${point.month}: ${point.created} created`}
                              style={{ height: `${Math.max((point.created / trendMax) * 100, point.created ? 8 : 0)}%` }}
                            />
                            <div
                              className="w-4 rounded-t bg-green-500"
                              title={`${point.month}: ${point.closed} closed`}
                              style={{ height: `${Math.max((point.closed / trendMax) * 100, point.closed ? 8 : 0)}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500">
                            {new Date(`${point.month}-01T00:00:00`).toLocaleDateString(undefined, { month: "short" })}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                  <div className="mt-4 flex gap-5 text-sm text-gray-600">
                    <span className="flex items-center gap-2"><span className="h-2 w-2 rounded bg-blue-500" />Created</span>
                    <span className="flex items-center gap-2"><span className="h-2 w-2 rounded bg-green-500" />Closed</span>
                  </div>
                </CardContent>
              </Card>

              <Card className="xl:col-span-2">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2">
                    <FileCheck2 className="h-5 w-5" />
                    Knowledge Quality
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div>
                    <div className="mb-2 flex justify-between text-sm">
                      <span>RCA completion</span>
                      <span className="font-medium">{formatPercent(quality?.rca_completion_rate_percent)}</span>
                    </div>
                    <ProgressBar value={quality?.rca_completion_rate_percent || 0} tone="bg-emerald-600" />
                    <p className="mt-1 text-xs text-gray-500">{quality?.closed_missing_rca || 0} closed tickets missing RCA</p>
                  </div>
                  <div>
                    <div className="mb-2 flex justify-between text-sm">
                      <span>Resolution notes</span>
                      <span className="font-medium">{formatPercent(quality?.resolution_note_completion_rate_percent)}</span>
                    </div>
                    <ProgressBar value={quality?.resolution_note_completion_rate_percent || 0} tone="bg-blue-600" />
                    <p className="mt-1 text-xs text-gray-500">{quality?.closed_missing_resolution || 0} closed tickets missing notes</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 pt-2">
                    <div className="rounded border p-3">
                      <p className="text-xs text-gray-500">RCA records</p>
                      <p className="text-2xl font-semibold">{quality?.rca_count || 0}</p>
                    </div>
                    <div className="rounded border p-3">
                      <p className="text-xs text-gray-500">Resolution notes</p>
                      <p className="text-2xl font-semibold">{quality?.resolution_note_count || 0}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5" />
                    Needs Attention
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {(analytics?.needs_attention || []).length === 0 ? (
                    <p className="text-sm text-gray-500">No active tickets need attention.</p>
                  ) : (
                    analytics?.needs_attention.map((ticket) => (
                      <div key={ticket.id} className="rounded border p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <Link href={`/dashboard/tickets/${ticket.id}`} className="font-semibold text-blue-700 hover:underline">
                              {ticket.ticket_no}
                            </Link>
                            <p className="mt-1 line-clamp-2 text-sm text-gray-700">{ticket.subject}</p>
                            <p className="mt-1 text-xs text-gray-500">{ticket.company_name || "Unknown company"}</p>
                          </div>
                          <Badge variant="outline">{ticket.age_days}d</Badge>
                        </div>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2">
                    <Clock className="h-5 w-5" />
                    Open Age Buckets
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <RankedBarList
                    rows={Object.entries(analytics?.aging_buckets || {}).map(([bucket, count]) => ({
                      bucket,
                      count,
                    }))}
                    labelKey="bucket"
                    valueKey="count"
                  />
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5" />
                    Ticket Levels
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <RankedBarList
                    rows={Object.entries(analytics?.levels || {}).map(([level, count]) => ({
                      level,
                      count,
                    }))}
                    labelKey="level"
                    valueKey="count"
                  />
                </CardContent>
              </Card>
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
              <Card className="xl:col-span-2">
                <CardHeader className="pb-2">
                  <CardTitle>Company Health</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-gray-500">
                          <th className="py-2 pr-3 font-medium">Company</th>
                          <th className="py-2 pr-3 font-medium">Open</th>
                          <th className="py-2 pr-3 font-medium">Total</th>
                          <th className="py-2 pr-3 font-medium">Closure</th>
                          <th className="py-2 pr-3 font-medium">Avg Resolve</th>
                          <th className="py-2 pr-3 font-medium">IRs</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(analytics?.company_health || []).map((company) => (
                          <tr key={company.company_name} className="border-b">
                            <td className="py-3 pr-3 font-medium">{company.company_name}</td>
                            <td className="py-3 pr-3">{company.open}</td>
                            <td className="py-3 pr-3">{company.total}</td>
                            <td className="py-3 pr-3">{formatPercent(company.closure_rate_percent)}</td>
                            <td className="py-3 pr-3">{formatHours(company.avg_resolution_hours)}</td>
                            <td className="py-3 pr-3">{company.with_ir}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>

              <Card className="xl:col-span-3">
                <CardHeader className="pb-2">
                  <CardTitle>Category Performance</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 md:grid-cols-2">
                    {(analytics?.category_performance || []).map((category) => (
                      <div key={category.category} className="space-y-2">
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <p className="font-medium text-gray-900">{category.category}</p>
                            <p className="text-xs text-gray-500">
                              {category.open} open of {category.total} total
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-semibold">{formatPercent(category.closure_rate_percent)}</p>
                            <p className="text-xs text-gray-500">{formatHours(category.avg_resolution_hours)}</p>
                          </div>
                        </div>
                        <ProgressBar value={category.closure_rate_percent} tone="bg-slate-700" />
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          </>
        )}

        <div>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-gray-950">Recent Tickets</h2>
              <p className="text-sm text-gray-500">Latest operational context after the health indicators.</p>
            </div>
          </div>
          {ticketsLoading ? (
            <div className="flex h-32 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : (
            <TicketsTable tickets={tickets} onRefresh={fetchTickets} />
          )}
        </div>
      </div>
    </DashboardLayout>
  )
}
