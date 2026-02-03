// client/components/dashboard/AnalyticsCards.tsx
"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  BarChart3,
  AlertCircle,
  Clock,
  CheckCircle2,
  XCircle,
} from "lucide-react"

interface ResolutionTimeFormat {
  weeks: number
  days: number
  hours: number
  total_hours: number
  formatted: string
}

interface Analytics {
  total_tickets: number
  open_tickets: number
  in_progress: number
  resolved: number
  closed: number
  recent_tickets: number
  avg_resolution_time_hours?: number
  avg_resolution_time?: ResolutionTimeFormat | number
  categories: Record<string, number> | null
  levels: Record<string, number> | null
}

const formatValue = (value: string | number | null | undefined, defaultValue: string = "—"): string => {
  if (value === null || value === undefined) return defaultValue
  return String(value)
}

const getResolutionTimeDisplay = (resolutionTime: any): string => {
  // Handle new format (object with weeks, days, hours)
  if (typeof resolutionTime === 'object' && resolutionTime?.formatted) {
    return resolutionTime.formatted
  }
  
  // Handle legacy format (just hours as number)
  if (typeof resolutionTime === 'number') {
    const hours = resolutionTime
    const weeks = Math.floor(hours / (24 * 7))
    const remaining = hours % (24 * 7)
    const days = Math.floor(remaining / 24)
    const mins = Math.round((remaining % 24) * 100) / 100
    
    if (weeks > 0) {
      return `${weeks}w ${days}d ${mins}h`
    } else if (days > 0) {
      return `${days}d ${mins}h`
    } else {
      return `${mins}h`
    }
  }
  
  return "—"
}

const StatCard = ({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string
  value: string | number
  icon: React.ComponentType<{ className?: string }>
  color: string
}) => (
  <Card>
    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
      <CardTitle className="text-sm font-medium text-gray-600">{title}</CardTitle>
      <Icon className={`h-4 w-4 ${color}`} />
    </CardHeader>
    <CardContent>
      <div className="text-2xl font-bold">{formatValue(value, "0")}</div>
    </CardContent>
  </Card>
)

export default function AnalyticsCards({ analytics }: { analytics: Analytics | null }) {
  if (!analytics) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[...Array(6)].map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <div className="h-4 w-24 bg-gray-200 rounded animate-pulse"></div>
              <div className="h-4 w-4 bg-gray-200 rounded animate-pulse"></div>
            </CardHeader>
            <CardContent>
              <div className="h-8 w-12 bg-gray-200 rounded animate-pulse"></div>
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  const resolutionTimeDisplay = getResolutionTimeDisplay(
    analytics.avg_resolution_time || analytics.avg_resolution_time_hours
  )

  const cards = [
    {
      title: "Total Tickets",
      value: analytics.total_tickets ?? 0,
      icon: BarChart3,
      color: "bg-blue-50 text-blue-600",
    },
    {
      title: "Open",
      value: analytics.open_tickets ?? 0,
      icon: AlertCircle,
      color: "bg-red-50 text-red-600",
    },
    {
      title: "In Progress",
      value: analytics.in_progress ?? 0,
      icon: Clock,
      color: "bg-yellow-50 text-yellow-600",
    },
    {
      title: "Resolved",
      value: analytics.resolved ?? 0,
      icon: CheckCircle2,
      color: "bg-green-50 text-green-600",
    },
    {
      title: "Closed",
      value: analytics.closed ?? 0,
      icon: XCircle,
      color: "bg-gray-50 text-gray-600",
    },
    {
      title: "Avg Resolution Time",
      value: resolutionTimeDisplay,
      icon: Clock,
      color: "bg-purple-50 text-purple-600",
    },
  ]

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {cards.map((card) => (
        <StatCard key={card.title} {...card} />
      ))}
    </div>
  )
}