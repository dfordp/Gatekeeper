"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface StatusData {
  status: string
  count: number
  color: string
  bgColor: string
}

interface TicketStatusBreakdownProps {
  open: number
  inProgress: number
  resolved: number
  closed: number
  reopened?: number
}

export default function TicketStatusBreakdown({
  open,
  inProgress,
  resolved,
  closed,
  reopened = 0,
}: TicketStatusBreakdownProps) {
  const statuses: StatusData[] = [
    { status: "Open", count: open, color: "text-red-800", bgColor: "bg-red-100" },
    {
      status: "In Progress",
      count: inProgress,
      color: "text-yellow-800",
      bgColor: "bg-yellow-100",
    },
    {
      status: "Resolved",
      count: resolved,
      color: "text-green-800",
      bgColor: "bg-green-100",
    },
    { status: "Closed", count: closed, color: "text-gray-800", bgColor: "bg-gray-100" },
    {
      status: "Reopened",
      count: reopened,
      color: "text-orange-800",
      bgColor: "bg-orange-100",
    },
  ].filter((s) => s.count > 0)

  const total = open + inProgress + resolved + closed + reopened
  const colors = ["#ef4444", "#eab308", "#22c55e", "#6b7280", "#f97316"]

  // Simple pie chart using CSS
  const getPercentage = (count: number) => ((count / total) * 100).toFixed(1)
  const cumulativePercentages: number[] = []
  let cumulative = 0

  statuses.forEach((s) => {
    cumulative += (s.count / total) * 100
    cumulativePercentages.push(cumulative)
  })

  // Build conic gradient
  const conicStops = statuses
    .map((s, idx) => {
      const startPercent = idx === 0 ? 0 : cumulativePercentages[idx - 1]
      const endPercent = cumulativePercentages[idx]
      return `${colors[idx]} ${startPercent}% ${endPercent}%`
    })
    .join(", ")

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ticket Status Distribution</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex gap-8">
          {/* Pie Chart */}
          <div className="flex-shrink-0">
            <div
              className="w-40 h-40 rounded-full"
              style={{
                background: `conic-gradient(${conicStops})`,
              }}
            ></div>
          </div>

          {/* Legend */}
          <div className="flex-1 space-y-3">
            {statuses.map((s, idx) => (
              <div key={s.status} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: colors[idx] }}
                  ></div>
                  <span className="text-sm font-medium">{s.status}</span>
                </div>
                <div className="text-right">
                  <p className="font-bold">{s.count}</p>
                  <p className="text-xs text-gray-500">{getPercentage(s.count)}%</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
