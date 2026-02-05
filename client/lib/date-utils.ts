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