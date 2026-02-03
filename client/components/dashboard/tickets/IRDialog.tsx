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
import { Loader2, AlertCircle, CheckCircle, Clock } from "lucide-react"

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
  const [notes, setNotes] = useState("")

  // Manage IR form
  const [ir, setIR] = useState<IncidentReport | null>(null)
  const [irStatus, setIRStatus] = useState("")
  const [vendorStatus, setVendorStatus] = useState("")
  const [vendorNotes, setVendorNotes] = useState("")
  const [updateNotes, setUpdateNotes] = useState("")

  // Load existing IR data when dialog opens
  useEffect(() => {
    if (open && hasOpenIR && existingIR) {
      setIR(existingIR)
      setIRStatus(existingIR.status || "")
      setVendorStatus(existingIR.vendor_status || "")
      setVendorNotes(existingIR.vendor_notes || "")
      setUpdateNotes("")
      setError(null)
      setSuccess(null)
    } else if (open && !hasOpenIR) {
      // Reset form for new IR
      setNewIRNumber("")
      setVendor("siemens")
      setExpectedDate("")
      setNotes("")
      setError(null)
      setSuccess(null)
    }
  }, [open, hasOpenIR, existingIR])

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
          ? new Date(expectedDate).toISOString()
          : undefined,
        notes: notes.trim() || undefined,
      })

      setSuccess(`IR ${newIRNumber} opened successfully`)
      setNewIRNumber("")
      setVendor("siemens")
      setExpectedDate("")
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
        vendor_notes: vendorNotes || undefined,
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
                <Label htmlFor="vendor-notes">Vendor Notes</Label>
                <Textarea
                  id="vendor-notes"
                  placeholder="Notes from vendor..."
                  value={vendorNotes}
                  onChange={(e) => setVendorNotes(e.target.value)}
                  disabled={loading}
                  rows={3}
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
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}