"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Layers } from "lucide-react"

interface CategoriesBreakdownProps {
  categories: Record<string, number>
}

export default function CategoriesBreakdown({ categories }: CategoriesBreakdownProps) {
  const entries = Object.entries(categories)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)

  if (entries.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Layers className="h-5 w-5" />
            Top Categories
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-500">No category data available</p>
        </CardContent>
      </Card>
    )
  }

  const total = entries.reduce((sum, e) => sum + e.count, 0)
  const topCategories = entries.slice(0, 6)
  const colors = [
    "#3b82f6",
    "#8b5cf6",
    "#ec4899",
    "#f59e0b",
    "#10b981",
    "#06b6d4",
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Layers className="h-5 w-5" />
          Top Categories
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {topCategories.map((cat, idx) => {
            const percentage = ((cat.count / total) * 100).toFixed(1)
            return (
              <div key={cat.name}>
                <div className="flex justify-between mb-1">
                  <span className="text-sm font-medium text-gray-700">
                    {cat.name}
                  </span>
                  <span className="text-sm font-bold text-gray-900">
                    {cat.count} ({percentage}%)
                  </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="h-2 rounded-full"
                    style={{
                      width: `${percentage}%`,
                      backgroundColor: colors[idx % colors.length],
                    }}
                  ></div>
                </div>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
