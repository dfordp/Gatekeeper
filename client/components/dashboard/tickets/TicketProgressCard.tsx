// client/components/dashboard/tickets/TicketProgressCard.tsx - FIXED

"use client"

import { useMemo } from "react"
import { TaskStatus, TicketCreationStatus } from "@/hooks/useTicketCreation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  SkipForward,
  AlertTriangle,
  X,
} from "lucide-react"

interface TicketProgressCardProps {
  status: TicketCreationStatus | null
  isPolling: boolean
  onClose?: () => void
}

const getTaskIcon = (task: TaskStatus) => {
  switch (task.status) {
    case "completed":
      return <CheckCircle2 className="w-4 h-4 text-green-600" />
    case "failed":
      return <AlertCircle className="w-4 h-4 text-red-600" />
    case "processing":
      return <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
    case "retrying":
      return <Clock className="w-4 h-4 text-yellow-600 animate-pulse" />
    case "skipped":
      return <SkipForward className="w-4 h-4 text-gray-400" />
    default:
      return <Clock className="w-4 h-4 text-gray-400" />
  }
}

const getTaskLabel = (type: string) => {
  const labels: Record<string, string> = {
    ticket_creation: "Creating Ticket",
    attachment_processing: "Processing Attachments",
    embedding_creation: "Creating Embeddings",
    rca_creation: "Creating RCA",
    qdrant_sync: "Syncing to Vector Database",
  }
  return labels[type] || type
}

const getTaskDescription = (task: TaskStatus) => {
  if (task.error_message) {
    return `Error: ${task.error_message}`
  }

  switch (task.status) {
    case "completed":
      return "Completed successfully"
    case "processing":
      return "Processing..."
    case "retrying":
      return `Retrying (attempt ${task.retry_count + 1})`
    case "failed":
      return "Failed"
    case "skipped":
      return "Skipped"
    default:
      return "Pending"
  }
}

const formatTime = (dateString: string | undefined) => {
  if (!dateString) return ""
  try {
    return new Date(dateString).toLocaleTimeString()
  } catch {
    return ""
  }
}

export default function TicketProgressCard({
  status,
  isPolling,
  onClose,
}: TicketProgressCardProps) {
  // Ensure tasks is an array
  const tasks = Array.isArray(status?.tasks) ? status.tasks : []

  // Calculate progress safely
  const progress = useMemo(() => {
    if (tasks.length === 0) return 0
    const completed = tasks.filter(
      (t) => t.status === "completed" || t.status === "skipped"
    ).length
    return Math.round((completed / tasks.length) * 100)
  }, [tasks])

  if (!status) return null

  const hasErrors = status.failed_count > 0
  const isComplete = status.all_completed

  return (
    <Card className="w-full border-l-4 border-l-blue-500">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="space-y-1 flex-1">
            <CardTitle className="flex items-center gap-2">
              {isComplete ? (
                <CheckCircle2 className="w-5 h-5 text-green-600" />
              ) : (
                <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
              )}
              {isComplete ? "Ticket Created Successfully" : "Creating Ticket"}
            </CardTitle>
            <CardDescription>
              {status.ticket_no ? `Ticket: ${status.ticket_no}` : "Processing..."}
              {isPolling && !isComplete && " • Updating..."}
            </CardDescription>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-2xl leading-none ml-4"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Overall Progress */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600">Overall Progress</span>
            <span className="font-medium">{progress}%</span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>

        {/* Status Summary */}
        <div className="grid grid-cols-3 gap-4">
          <div className="p-3 bg-green-50 rounded-lg border border-green-200">
            <p className="text-xs text-green-600 font-medium">Completed</p>
            <p className="text-2xl font-bold text-green-600 mt-1">{status.success_count}</p>
          </div>
          <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
            <p className="text-xs text-blue-600 font-medium">In Progress</p>
            <p className="text-2xl font-bold text-blue-600 mt-1">{status.pending_count}</p>
          </div>
          <div className="p-3 bg-red-50 rounded-lg border border-red-200">
            <p className="text-xs text-red-600 font-medium">Failed</p>
            <p className="text-2xl font-bold text-red-600 mt-1">{status.failed_count}</p>
          </div>
        </div>

        {/* Error Alert */}
        {hasErrors && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              {status.failed_count} task(s) failed. Check details below for more information.
            </AlertDescription>
          </Alert>
        )}

        {/* Task List */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-gray-900">Task Details</h4>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {tasks.length > 0 ? (
              tasks.map((task) => (
                <div
                  key={task.task_id}
                  className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200"
                >
                  <div className="flex-shrink-0 mt-0.5">
                    {getTaskIcon(task)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-gray-900">
                        {/* ✅ FIXED: Use task_type instead of task.type */}
                        {getTaskLabel(task.task_type)}
                      </p>
                      <span
                        className={`text-xs font-medium px-2 py-1 rounded-full whitespace-nowrap ${
                          task.status === "completed"
                            ? "bg-green-100 text-green-800"
                            : task.status === "failed"
                              ? "bg-red-100 text-red-800"
                              : task.status === "processing"
                                ? "bg-blue-100 text-blue-800"
                                : task.status === "retrying"
                                  ? "bg-yellow-100 text-yellow-800"
                                  : "bg-gray-100 text-gray-800"
                        }`}
                      >
                        {task.status}
                      </span>
                    </div>
                    <p className="text-xs text-gray-600 mt-1">
                      {getTaskDescription(task)}
                    </p>
                    {task.completed_at && (
                      <p className="text-xs text-gray-500 mt-1">
                        Completed at {formatTime(task.completed_at)}
                      </p>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-4 text-gray-500 text-sm">
                No tasks yet
              </div>
            )}
          </div>
        </div>

        {/* Success Message */}
        {isComplete && !hasErrors && (
          <Alert className="bg-green-50 border-green-200">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <AlertDescription className="text-green-800">
              Your ticket has been created successfully. All tasks completed without errors.
            </AlertDescription>
          </Alert>
        )}

        {/* Partial Success Message */}
        {isComplete && hasErrors && (
          <Alert className="bg-yellow-50 border-yellow-200">
            <AlertCircle className="h-4 w-4 text-yellow-600" />
            <AlertDescription className="text-yellow-800">
              Your ticket was created, but some async tasks failed. It&apos;s still usable, but some features may be limited.
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}