// client/hooks/useTicketCreation.ts - FIXED

"use client"

import { useState, useCallback, useRef, useEffect } from "react"
import { apiClient } from "@/lib/api-client"

export interface TaskStatus {
  task_id: string
  ticket_id: string
  task_type: string
  status: "pending" | "processing" | "completed" | "failed" | "skipped" | "retrying"
  error_message?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
  retry_count: number
}

export interface TicketCreationStatusResponse {
  ticket_id: string
  overall_status: "pending" | "processing" | "completed" | "error"
  task_breakdown: {
    pending: number
    processing: number
    completed: number
    failed: number
    skipped: number
    retrying: number
  }
  tasks: Record<string, TaskStatus>
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  in_progress_tasks: number
}

export interface TicketCreationStatus {
  ticket_id: string
  ticket_no?: string
  creation_status?: string
  overall_status: "pending" | "processing" | "completed" | "error"
  tasks: TaskStatus[]
  polling_url?: string
  all_completed: boolean
  success_count: number
  failed_count: number
  pending_count: number
}

export interface UseTicketCreationReturn {
  ticketId: string | null
  ticketNo: string | null
  status: TicketCreationStatus | null
  loading: boolean
  error: string | null
  isPolling: boolean
  startPolling: (id?: string) => void
  stopPolling: () => void
  reset: () => void
  setCreatedTicket: (id: string, no: string) => void
  getTaskProgress: () => {
    total: number
    completed: number
    percentage: number
  }
  getTasksByType: (type: string) => TaskStatus[]
}

export function useTicketCreation(): UseTicketCreationReturn {
  const [ticketId, setTicketId] = useState<string | null>(null)
  const [ticketNo, setTicketNo] = useState<string | null>(null)
  const [status, setStatus] = useState<TicketCreationStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isPolling, setIsPolling] = useState(false)
  
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const ticketIdRef = useRef<string | null>(null)

  // Keep ref in sync with state
  useEffect(() => {
    ticketIdRef.current = ticketId
  }, [ticketId])

  // Fetch ticket creation status
  const fetchTicketStatus = useCallback(
    async (id: string) => {
      try {
        const response = await apiClient.get<TicketCreationStatusResponse>(
          `/api/tickets/creation-status/${id}`
        )
        
        // Transform backend response to frontend format
        const tasks = Object.values(response.data.tasks || {})
        const formattedStatus: TicketCreationStatus = {
          ticket_id: response.data.ticket_id,
          overall_status: response.data.overall_status,
          tasks: tasks,
          all_completed: response.data.overall_status === "completed",
          success_count: response.data.completed_tasks,
          failed_count: response.data.failed_tasks,
          pending_count: response.data.task_breakdown.pending,
        }
        
        setStatus(formattedStatus)
        
        // ✅ FIXED: Stop polling when overall_status is "completed" or "error"
        if (response.data.overall_status === "completed" || response.data.overall_status === "error") {
          setIsPolling(false)
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current)
            pollIntervalRef.current = null
          }
        }
        
        return formattedStatus
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "Failed to fetch ticket status"
        setError(errorMessage)
        throw err
      }
    },
    []
  )

  // Start polling for status updates (with optional explicit ID)
  const startPolling = useCallback((id?: string) => {
    // Use provided ID or fall back to state
    const actualId = id || ticketIdRef.current
    
    if (!actualId || isPolling) {
      console.warn(`Cannot start polling: id=${actualId}, isPolling=${isPolling}`)
      return
    }

    console.log(`✓ Starting polling for ticket: ${actualId}`)
    setIsPolling(true)
    setError(null)

    // Initial fetch
    fetchTicketStatus(actualId)

    // Poll every 2 seconds
    pollIntervalRef.current = setInterval(() => {
      fetchTicketStatus(actualId)
    }, 2000)
  }, [isPolling, fetchTicketStatus])

  // Stop polling
  const stopPolling = useCallback(() => {
    setIsPolling(false)
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
  }, [])

  // Reset state
  const reset = useCallback(() => {
    stopPolling()
    setTicketId(null)
    ticketIdRef.current = null
    setTicketNo(null)
    setStatus(null)
    setLoading(false)
    setError(null)
  }, [stopPolling])

  // Get task progress
  const getTaskProgress = useCallback(() => {
    if (!status) {
      return { total: 0, completed: 0, percentage: 0 }
    }

    const total = status.tasks.length
    const completed = status.tasks.filter(
      (t) => t.status === "completed" || t.status === "skipped"
    ).length

    return {
      total,
      completed,
      percentage: total > 0 ? Math.round((completed / total) * 100) : 0,
    }
  }, [status])

  // Get tasks by type
  const getTasksByType = useCallback(
    (type: string) => {
      return status?.tasks.filter((t) => t.task_type === type) || []
    },
    [status]
  )

  // Set ticket ID when creation succeeds
  const setCreatedTicket = useCallback((id: string, no: string) => {
    console.log(`✓ Setting created ticket: ${id} (${no})`)
    setTicketId(id)
    ticketIdRef.current = id
    setTicketNo(no)
    setStatus(null)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  return {
    ticketId,
    ticketNo,
    status,
    loading,
    error,
    isPolling,
    startPolling,
    stopPolling,
    reset,
    setCreatedTicket,
    getTaskProgress,
    getTasksByType,
  }
}