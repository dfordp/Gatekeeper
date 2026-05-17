"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCircle } from "lucide-react"

interface LevelsBreakdownProps {
  levels: Record<string, number>
}

const levelConfig: Record<string, { color: string; bgColor: string }> = {
  critical: { color: "#dc2626", bgColor: "bg-red-50" },
  high: { color: "#ea580c", bgColor: "bg-orange-50" },
  medium: { color: "#eab308", bgColor: "bg-yellow-50" },
  low: { color: "#3b82f6", bgColor: "bg-blue-50" },
}

export default function LevelsBreakdown({ levels }: LevelsBreakdownProps) {
  const entries = Object.entries(levels)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => {
      const priority = ["critical", "high", "medium", "low"]
      return priority.indexOf(a.name) - priority.indexOf(b.name)
    })

  if (entries.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5" />
            Ticket Levels
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-500">No level data available</p>
        </CardContent>
      </Card>
    )
  }

  const total = entries.reduce((sum, e) => sum + e.count, 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertCircle className="h-5 w-5" />
          Ticket Levels
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          {entries.map((level) => {
            const config = levelConfig[level.name.toLowerCase()]
            const percentage = ((level.count / total) * 100).toFixed(0)
            return (
              <div
                key={level.name}
                className={`p-4 rounded-lg ${config?.bgColor || "bg-gray-50"}`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs font-medium text-gray-600 uppercase">
                      {level.name}
                    </p>
                    <p className="text-2xl font-bold mt-1" style={{ color: config?.color }}>
                      {level.count}
                    </p>
                  </div>
                  <span className="text-sm font-medium text-gray-600">
                    {percentage}%
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
