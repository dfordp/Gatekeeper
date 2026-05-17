"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CheckCircle2, TrendingUp } from "lucide-react"

interface ClosedRateProps {
  totalTickets: number
  closedTickets: number
  avgResolutionTime: number
}

export default function ClosedRateCard({
  totalTickets,
  closedTickets,
  avgResolutionTime,
}: ClosedRateProps) {
  const closedRate = totalTickets > 0 ? ((closedTickets / totalTickets) * 100).toFixed(1) : 0
  const resolutionDays = Math.floor(avgResolutionTime / 24)
  const resolutionHours = avgResolutionTime % 24

  return (
    <div className="grid grid-cols-2 gap-4">
      {/* Closed Rate */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CheckCircle2 className="h-5 w-5" />
            Closed Rate
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div>
              <p className="text-4xl font-bold text-green-600">{closedRate}%</p>
              <p className="text-sm text-gray-600 mt-1">
                {closedTickets} of {totalTickets} tickets closed
              </p>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="h-2 rounded-full bg-green-500"
                style={{ width: `${closedRate}%` }}
              ></div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
