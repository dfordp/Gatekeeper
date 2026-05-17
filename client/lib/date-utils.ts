/**
 * Date-only utility functions (no time component)
 */

/**
 * Convert any input to ISO date string (YYYY-MM-DD)
 * Handles both date inputs and datetime inputs
 * 
 * @param date Date object, ISO string, or date string
 * @returns ISO date string like "2026-01-21"
 */
export function toISODateString(date: Date | string): string {
  if (typeof date === 'string') {
    // If it's a full ISO datetime, extract just the date part
    if (date.includes('T')) {
      return date.split('T')[0]
    }
    // If it's already YYYY-MM-DD format, return as-is
    if (date.match(/^\d{4}-\d{2}-\d{2}$/)) {
      return date
    }
    // Try parsing other formats
    const d = new Date(date)
    return d.toISOString().split('T')[0]
  }
  
  // For Date objects
  return date.toISOString().split('T')[0]
}

/**
 * Parse ISO date string safely
 * @param dateStr ISO date format string (YYYY-MM-DD)
 * @returns Date object (at midnight UTC)
 */
export function parseISODate(dateStr: string): Date {
  return new Date(dateStr + 'T00:00:00Z')
}

/**
 * Format date for display
 * @param dateStr ISO date string (YYYY-MM-DD)
 * @returns Localized date string
 */
export function formatDateForDisplay(dateStr: string | undefined): string {
  if (!dateStr) return ""
  try {
    const date = parseISODate(dateStr)
    return date.toLocaleDateString()
  } catch {
    return ""
  }
}

/**
 * Calculate how long a ticket has been open
 * @param createdAt ISO date string or Date object when ticket was created
 * @param closedAt Optional ISO date string or Date object when ticket was closed (defaults to now)
 * @returns Object with days and formatted string
 */
export interface TicketDuration {
  days: number
  formatted: string
}

export function calculateTicketOpenDuration(
  createdAt: string | Date,
  closedAt?: string | Date | null
): TicketDuration {
  if (!createdAt) {
    return {
      days: 0,
      formatted: "—"
    }
  }

  try {
    const startDate = typeof createdAt === 'string' ? new Date(createdAt) : createdAt
    const endDate = closedAt 
      ? (typeof closedAt === 'string' ? new Date(closedAt) : closedAt)
      : new Date()

    // Calculate difference in milliseconds
    const diffMs = endDate.getTime() - startDate.getTime()
    
    // Handle negative durations (shouldn't happen but just in case)
    if (diffMs < 0) {
      return {
        days: 0,
        formatted: "—"
      }
    }

    // Convert to total days
    const totalDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

    // Format: "<1 day" if less than 1 day, otherwise "X days"
    let formatted: string
    if (totalDays === 0) {
      formatted = "<1 day"
    } else if (totalDays === 1) {
      formatted = "1 day"
    } else {
      formatted = `${totalDays} days`
    }

    return {
      days: totalDays,
      formatted
    }
  } catch (error) {
    console.error('Error calculating ticket duration:', error)
    return {
      days: 0,
      formatted: "—"
    }
  }
}