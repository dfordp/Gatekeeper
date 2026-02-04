// client/lib/date-utils.ts
/**
 * Utility functions to ensure dates are always sent in UTC ISO format
 */

/**
 * Convert any date to UTC ISO string with 'Z' suffix
 * Handles both datetime-local inputs and Date objects
 * 
 * For datetime-local inputs (YYYY-MM-DDTHH:mm):
 * - Interprets the value as UTC (not local browser time)
 * - This matches backend expectation for datetime-local fields
 * 
 * For Date objects:
 * - Converts to ISO string (which is already UTC)
 * 
 * @param date Date object, ISO string, or datetime-local string
 * @returns ISO string like "2026-01-21T13:58:00.000Z"
 */
export function toUTCISOString(date: Date | string): string {
  if (typeof date === 'string') {
    // Check if this is a datetime-local input (YYYY-MM-DDTHH:mm or YYYY-MM-DDTHH:mm:ss)
    // Regex matches: YYYY-MM-DDTHH:mm or YYYY-MM-DDTHH:mm:ss (no timezone info)
    if (date.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/)) {
      // This is a datetime-local value - treat it as UTC, not local browser time
      // Add :00.000Z to complete the ISO format
      if (date.length === 16) {
        // Format: YYYY-MM-DDTHH:mm
        return date + ':00.000Z'
      } else if (date.length === 19) {
        // Format: YYYY-MM-DDTHH:mm:ss
        return date + '.000Z'
      }
    }
  }
  
  // For all other cases (Date objects or full ISO strings), use standard conversion
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toISOString()
}

/**
 * Parse ISO date string safely
 * @param dateStr ISO format string
 * @returns Date object
 */
export function parseISODate(dateStr: string): Date {
  return new Date(dateStr)
}

/**
 * Validate date has timezone info
 * @param dateStr ISO format string
 * @returns true if has 'Z' or ±HH:MM
 */
export function hasTimezoneInfo(dateStr: string): boolean {
  return dateStr.endsWith('Z') || dateStr.includes('+') || (dateStr.match(/-/g) || []).length >= 2
}