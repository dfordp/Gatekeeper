// client/components/dashboard/tickets/IRDialog.tsx
"use client"

import { useState, useEffect } from "react"
import { irService, IncidentReport } from "@/services/ir.service"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Loader2, AlertCircle, CheckCircle, Clock, Trash2 } from "lucide-react"
import { toUTCISOString } from "@/lib/date-utils"

interface IRDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  ticketId: string
  ticketNo: string
  hasOpenIR: boolean
  irNumber?: string
  existingIR?: IncidentReport | null
  onIRUpdated: () => void
}

export default function IRDialog({
  open,
  onOpenChange,
  ticketId,
  ticketNo,
  hasOpenIR,
  irNumber,
  existingIR,
  onIRUpdated,
}: IRDialogProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Open IR form
  const [newIRNumber, setNewIRNumber] = useState("")
  const [vendor, setVendor] = useState("siemens")
  const [expectedDate, setExpectedDate] = useState("")
  const [irOpenedAt, setIROpenedAt] = useState("")
  const [irClosedAt, setIRClosedAt] = useState("")
  const [notes, setNotes] = useState("")

  // Manage IR form
  const [ir, setIR] = useState<IncidentReport | null>(null)
  const [irStatus, setIRStatus] = useState("")
  const [vendorStatus, setVendorStatus] = useState("")
  const [updateNotes, setUpdateNotes] = useState("")
  const [closedAt, setClosedAt] = useState("")

  // Delete confirmation state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

    // Add this helper function right after the imports, before the interface definition (after line 25):
  
  /**
   * Convert ISO UTC string to datetime-local format with proper timezone conversion
   * Converts "2026-01-21T04:28:00.000Z" to "2026-01-21T09:58" (for UTC+5:30)
   */
  const isoToDatetimeLocal = (isoString: string): string => {
    if (!isoString) return ""
    // Parse as UTC and extract local timezone components
    const date = new Date(isoString)
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    return `${year}-${month}-${day}T${hours}:${minutes}`
  }
  
  // Then replace the useEffect hook (lines 67-83) with:
  useEffect(() => {
    if (open && hasOpenIR && existingIR) {
      setIR(existingIR)
      setIRStatus(existingIR.status || "")
      setVendorStatus(existingIR.vendor_status || "")
      setUpdateNotes("")
      // Set closure date using proper timezone conversion
      setClosedAt(existingIR.resolved_at ? isoToDatetimeLocal(existingIR.resolved_at) : "")
      setShowDeleteConfirm(false)
      setError(null)
      setSuccess(null)
    } else if (open && !hasOpenIR) {
      // Reset form for new IR
      setNewIRNumber("")
      setVendor("siemens")
      setExpectedDate("")
      setIROpenedAt("")
      setIRClosedAt("")
      setNotes("")
      setClosedAt("")
      setShowDeleteConfirm(false)
      setError(null)
      setSuccess(null)
    }
  }, [open, hasOpenIR, existingIR])
  
  // Update handleCloseIR to pass the date
  const handleCloseIR = async () => {
    if (!ir) return
    if (!closedAt) {
      setError("Please select a closure date")
      return
    }
  
    setLoading(true)
    setError(null)
    setSuccess(null)
  
    try {
      // Convert closedAt to ISO string
      const closureDate = closedAt ? (closedAt + ':00.000Z') : toUTCISOString(new Date())
      
      // Call updateIRStatus with closed status (which uses current time)
      // Or call closeIR with the specific date
      await irService.closeIR(ir.id, {
        resolution_notes: updateNotes || undefined,
        closed_at: closureDate,  // ISO format with UTC
        closed_by_user_id: undefined,
      })
  
      setSuccess(`IR ${ir.ir_number} closed successfully`)
  
      setTimeout(() => {
        onIRUpdated()
        onOpenChange(false)
      }, 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to close IR")
    } finally {
      setLoading(false)
    }
  }

  const handleOpenIR = async () => {
    if (!newIRNumber.trim()) {
      setError("IR Number is required")
      return
    }

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      
      await irService.openIR(ticketId, {
        ir_number: newIRNumber.trim(),
        vendor,
        expected_resolution_date: expectedDate
          ? toUTCISOString(new Date(expectedDate))
          : undefined,
        ir_raised_at: irOpenedAt
          ? toUTCISOString(new Date(irOpenedAt))
          : undefined,
        closed_at: irClosedAt
          ? toUTCISOString(new Date(irClosedAt))
          : undefined,
        notes: notes.trim() || undefined,
      })

      setSuccess(`IR ${newIRNumber} opened successfully`)
      setNewIRNumber("")
      setVendor("siemens")
      setExpectedDate("")
      setIROpenedAt("")
      setIRClosedAt("")
      setNotes("")

      setTimeout(() => {
        onIRUpdated()
        onOpenChange(false)
      }, 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open IR")
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateIR = async () => {
    if (!ir) return
    if (!irStatus) {
      setError("Please select a status")
      return
    }

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      await irService.updateIRStatus(ir.id, {
        status: irStatus,
        vendor_status: vendorStatus || undefined,
        notes: updateNotes || undefined,
      })

      setSuccess(`IR status updated to ${irStatus}`)

      setTimeout(() => {
        onIRUpdated()
        onOpenChange(false)
      }, 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update IR")
    } finally {
      setLoading(false)
    }
  }


  const handleDeleteIR = async () => {
    if (!ir) return

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      await irService.deleteIR(ir.id)

      setSuccess(`IR ${ir.ir_number} deleted successfully`)
      setShowDeleteConfirm(false)

      setTimeout(() => {
        onIRUpdated()
        onOpenChange(false)
      }, 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete IR")
    } finally {
      setLoading(false)
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "open":
        return <Clock className="h-4 w-4 text-orange-500" />
      case "in_progress":
        return <Clock className="h-4 w-4 text-blue-500" />
      case "resolved":
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case "closed":
        return <CheckCircle className="h-4 w-4 text-gray-500" />
      default:
        return null
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Incident Report (IR) Management</DialogTitle>
          <DialogDescription>
            Manage vendor incident reports for ticket {ticketNo}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {success && (
            <Alert className="bg-green-50 border-green-200">
              <CheckCircle className="h-4 w-4 text-green-600" />
              <AlertDescription className="text-green-800">
                {success}
              </AlertDescription>
            </Alert>
          )}

          {!hasOpenIR ? (
            // Open new IR form
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="ir-number">IR Number *</Label>
                <Input
                  id="ir-number"
                  placeholder="e.g., SIEMENS-123456"
                  value={newIRNumber}
                  onChange={(e) => setNewIRNumber(e.target.value)}
                  disabled={loading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="vendor">Vendor</Label>
                <Select value={vendor} onValueChange={setVendor}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="siemens">Siemens</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="ir-opened-at">IR Opened Date</Label>
                <Input
                  id="ir-opened-at"
                  type="datetime-local"
                  value={irOpenedAt}
                  onChange={(e) => setIROpenedAt(e.target.value)}
                  disabled={loading}
                />
                <p className="text-xs text-gray-600">
                  The date when the IR was originally opened (if importing legacy data)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="expected-date">Expected Resolution Date</Label>
                <Input
                  id="expected-date"
                  type="datetime-local"
                  value={expectedDate}
                  onChange={(e) => setExpectedDate(e.target.value)}
                  disabled={loading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="ir-closed-at">IR Closed Date (if already closed)</Label>
                <Input
                  id="ir-closed-at"
                  type="datetime-local"
                  value={irClosedAt}
                  onChange={(e) => setIRClosedAt(e.target.value)}
                  disabled={loading}
                />
                <p className="text-xs text-gray-600">
                  Leave blank if IR is still open
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="ir-notes">Notes</Label>
                <Textarea
                  id="ir-notes"
                  placeholder="Any additional details about the IR..."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  disabled={loading}
                  rows={3}
                />
              </div>

              <Button
                onClick={handleOpenIR}
                disabled={loading || !newIRNumber.trim()}
                className="w-full"
              >
                {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Open Incident Report
              </Button>
            </div>
          ) : (
            // Manage existing IR form
            <div className="space-y-4">
              {ir && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2">
                      {getStatusIcon(ir.status)}
                      {ir.ir_number}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-gray-600">Status</p>
                        <p className="font-medium capitalize">{ir.status}</p>
                      </div>
                      <div>
                        <p className="text-gray-600">Vendor</p>
                        <p className="font-medium capitalize">{ir.vendor}</p>
                      </div>
                      {ir.expected_resolution_date && (
                        <div>
                          <p className="text-gray-600">Expected Resolution</p>
                          <p className="font-medium">
                            {new Date(ir.expected_resolution_date).toLocaleDateString()}
                          </p>
                        </div>
                      )}
                      {ir.resolved_at && (
                        <div>
                          <p className="text-gray-600">Resolved At</p>
                          <p className="font-medium">
                            {new Date(ir.resolved_at).toLocaleDateString()}
                          </p>
                        </div>
                      )}
                      {ir.last_vendor_update && (
                        <div>
                          <p className="text-gray-600">Last Update</p>
                          <p className="font-medium">
                            {new Date(ir.last_vendor_update).toLocaleDateString()}
                          </p>
                        </div>
                      )}
                    </div>
                    {ir.notes && (
                      <div className="pt-2 border-t">
                        <p className="text-gray-600">Notes</p>
                        <p className="text-gray-700 whitespace-pre-wrap">{ir.notes}</p>
                      </div>
                    )}
                    {ir.vendor_status && (
                      <div className="pt-2 border-t">
                        <p className="text-gray-600">Vendor Status</p>
                        <p className="font-medium">{ir.vendor_status}</p>
                      </div>
                    )}
                    {ir.vendor_notes && (
                      <div className="pt-2 border-t">
                        <p className="text-gray-600">Vendor Notes</p>
                        <p className="text-gray-700 whitespace-pre-wrap">{ir.vendor_notes}</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              <div className="space-y-2">
                <Label htmlFor="update-status">Update Status</Label>
                <Select value={irStatus} onValueChange={setIRStatus}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select new status..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">Open</SelectItem>
                    <SelectItem value="in_progress">In Progress</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="closed">Closed</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="vendor-status">Vendor Status</Label>
                <Input
                  id="vendor-status"
                  placeholder="e.g., Investigating, Awaiting parts, In test..."
                  value={vendorStatus}
                  onChange={(e) => setVendorStatus(e.target.value)}
                  disabled={loading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="update-notes">Internal Notes</Label>
                <Textarea
                  id="update-notes"
                  placeholder="Internal notes about this update..."
                  value={updateNotes}
                  onChange={(e) => setUpdateNotes(e.target.value)}
                  disabled={loading}
                  rows={2}
                />
              </div>

              {/* Closed Date - Only show if status is closed */}
              {(irStatus === "closed" || ir?.status === "closed") && (
                <div className="space-y-2 p-3 bg-gray-50 rounded border">
                  <Label htmlFor="closed-at">IR Closure Date</Label>
                  <Input
                    id="closed-at"
                    type="datetime-local"
                    value={closedAt}
                    onChange={(e) => setClosedAt(e.target.value)}
                    disabled={loading}
                  />
                  <p className="text-xs text-gray-600">
                    The date when the IR was closed/resolved
                  </p>
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  onClick={handleUpdateIR}
                  disabled={loading || !irStatus}
                  className="flex-1"
                >
                  {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Update Status
                </Button>
              </div>

              {/* Delete Button Section */}
              <div className="pt-4 border-t">
                {!showDeleteConfirm ? (
                  <Button
                    onClick={() => setShowDeleteConfirm(true)}
                    variant="destructive"
                    className="w-full"
                    disabled={loading}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete Incident Report
                  </Button>
                ) : (
                  <div className="space-y-3 p-4 bg-red-50 rounded border border-red-200">
                    <p className="text-sm font-medium text-red-900">
                      Are you sure you want to delete this IR? This action cannot be undone.
                    </p>
                    <p className="text-xs text-red-800">
                      The incident report will be permanently deleted, and all related embeddings will be removed.
                    </p>
                    <div className="flex gap-2">
                      <Button
                        onClick={handleDeleteIR}
                        variant="destructive"
                        disabled={loading}
                        className="flex-1"
                      >
                        {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                        Yes, Delete
                      </Button>
                      <Button
                        onClick={() => setShowDeleteConfirm(false)}
                        variant="outline"
                        disabled={loading}
                        className="flex-1"
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}