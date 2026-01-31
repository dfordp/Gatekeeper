// client/components/dashboard/tickets/EditTicketDialog.tsx

"use client"

import { useState, useRef } from "react"
import { useAuth } from "@/hooks/useAuth"
import { TicketDetail } from "@/services/ticket.service"
import { ticketService, AddAttachmentRequest, AddRCARequest } from "@/services/ticket.service"
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
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { Loader2, AlertCircle, Calendar, Trash2, Plus } from "lucide-react"

interface EditTicketDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  ticket: TicketDetail
  onSave: (data: {
    subject: string
    summary?: string
    detailed_description: string
    category?: string
    level?: string
  }) => Promise<void>
  fetchTicket?: () => Promise<void>  // Add this
  isLoading: boolean
}

interface AttachmentFile {
  id: string
  name: string
  file: File
}

const PRIORITY_LEVELS = [
  { value: "level-1", label: "Level 1" },
  { value: "level-2", label: "Level 2" },
  { value: "level-3", label: "Level 3" },
]

const CATEGORIES = [
  { value: "login-access", label: "Login / Access" },
  { value: "license", label: "License" },
  { value: "installation", label: "Installation" },
  { value: "upload-save", label: "Upload or Save" },
  { value: "workflow", label: "Workflow" },
  { value: "performance", label: "Performance" },
  { value: "integration", label: "Integration" },
  { value: "data-configuration", label: "Data / Configuration" },
  { value: "other", label: "Other" },
]

export default function EditTicketDialog({
  open,
  onOpenChange,
  ticket,
  onSave,
  fetchTicket,
  isLoading,
}: EditTicketDialogProps) {
  // Get current user from auth
  const { admin: currentUser } = useAuth()

  // Form state
  const [error, setError] = useState<string | null>(null)
  const [subject, setSubject] = useState(ticket.subject)
  const [summary, setSummary] = useState(ticket.summary || "")
  const [description, setDescription] = useState(ticket.detailed_description)
  const [category, setCategory] = useState(ticket.category || "")
  const [level, setLevel] = useState(ticket.level || "")

  // Attachment state
  const [attachments, setAttachments] = useState<AttachmentFile[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  // RCA state
  const [rootCauseDescription, setRootCauseDescription] = useState(
    ticket.rca?.root_cause_description || ""
  )
  const [contributingFactors, setContributingFactors] = useState<string>(
    ticket.rca?.contributing_factors?.join("\n") || ""
  )
  const [preventionMeasures, setPreventionMeasures] = useState(
    ticket.rca?.prevention_measures || ""
  )
  const [resolutionSteps, setResolutionSteps] = useState<string>(
    ticket.rca?.resolution_steps?.join("\n") || ""
  )
  const [closedAt, setClosedAt] = useState(
    ticket.rca?.ticket_closed_at
      ? new Date(ticket.rca.ticket_closed_at).toISOString().slice(0, 16)
      : ticket.closed_at
      ? new Date(ticket.closed_at).toISOString().slice(0, 16)
      : ""
  )

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files) return

    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      const id = Math.random().toString(36).substring(2, 11)
      setAttachments((prev) => [...prev, { id, name: file.name, file }])
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((att) => att.id !== id))
  }

  const handleSave = async () => {
    setError(null)

    if (!subject.trim()) {
      setError("Subject is required")
      return
    }

    if (!description.trim()) {
      setError("Description is required")
      return
    }

    try {
      // Save basic ticket info
      await onSave({
        subject: subject.trim(),
        summary: summary.trim() || undefined,
        detailed_description: description.trim(),
        category: category || undefined,
        level: level || undefined,
      })

      // Add new attachments if any
      if (attachments.length > 0) {
        for (const attachment of attachments) {
          try {
            const formData = new FormData()
            formData.append('file', attachment.file)
            
            // Get auth token from localStorage
            const token = localStorage.getItem('auth_token')
            
            const response = await fetch(
              `/api/tickets/${ticket.id}/upload-attachment`,
              {
                method: 'POST',
                body: formData,
                headers: {
                  ...(token && { 'Authorization': `Bearer ${token}` }),
                },
              }
            )
            
            if (!response.ok) {
              const error = await response.json()
              throw new Error(error.detail || 'Failed to upload attachment')
            }
            
            const result = await response.json()
            console.log(`✓ Attachment uploaded: ${attachment.name}`)
          } catch (err) {
            console.error(`Failed to upload attachment ${attachment.name}:`, err)
            setError(`Failed to upload ${attachment.name}: ${err instanceof Error ? err.message : 'Unknown error'}`)
          }
        }
      }

      // Add or update RCA if closed
      if (ticket.status === "closed" && rootCauseDescription.trim()) {
        try {
          if (!ticket.rca) {
            // Validate root cause description length
            if (rootCauseDescription.trim().length < 10) {
              setError("Root cause description must be at least 10 characters")
              return
            }
            
            // Create new RCA
            if (currentUser?.id) {
              const rcaRequest: AddRCARequest = {
                root_cause_description: rootCauseDescription.trim(),
                created_by_user_id: currentUser.id,
                contributing_factors: contributingFactors.trim()
                  ? contributingFactors
                      .split("\n")
                      .map((f) => f.trim())
                      .filter((f) => f.length > 0)
                  : undefined,
                prevention_measures: preventionMeasures.trim() || undefined,
                resolution_steps: resolutionSteps.trim()
                  ? resolutionSteps
                      .split("\n")
                      .map((s) => s.trim())
                      .filter((s) => s.length > 0)
                  : undefined,
                ticket_closed_at: closedAt ? new Date(closedAt).toISOString() : null,
              }
              await ticketService.addRCA(ticket.id, rcaRequest)
            }
          }
        } catch (err) {
          console.error("Failed to add RCA:", err)
          setError(err instanceof Error ? err.message : "Failed to add RCA")
        }
      }

      setAttachments([])
      onOpenChange(false)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Failed to save ticket"
      const apiError = err as { response?: { data?: { detail?: string } } }
      setError(apiError?.response?.data?.detail || errorMessage)
    }
  }

    const handleDeleteAttachment = async (attachmentId: string) => {
      try {
        const token = localStorage.getItem('auth_token')
        if (!token) {
          throw new Error('Not authenticated. Please log in again.')
        }
        
        const response = await fetch(
          `/api/tickets/${ticket.id}/attachments/${attachmentId}`,
          {
            method: 'DELETE',
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          }
        )
        
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || `Delete failed with status ${response.status}`)
        }
        
        // Refresh ticket data after successful deletion
        if (fetchTicket) {
          await fetchTicket()
        }
        console.log(`✓ Attachment deleted`)
      } catch (err) {
        console.error(`Failed to delete attachment:`, err)
        setError(`Failed to delete attachment: ${err instanceof Error ? err.message : 'Unknown error'}`)
      }
    }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[95vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Ticket</DialogTitle>
          <DialogDescription>
            Update ticket information, add attachments, or add RCA for closed tickets
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <Tabs defaultValue="details" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="details">Details</TabsTrigger>
              <TabsTrigger value="attachments">Attachments</TabsTrigger>
              {ticket.status === "closed" && (
                <TabsTrigger value="rca">RCA</TabsTrigger>
              )}
            </TabsList>

            {/* Details Tab */}
            <TabsContent value="details" className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="subject">Subject *</Label>
                <Input
                  id="subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  disabled={isLoading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="summary">Summary</Label>
                <Input
                  id="summary"
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  disabled={isLoading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description *</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={isLoading}
                  rows={4}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="category">Category</Label>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select category..." />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map((cat) => (
                        <SelectItem key={cat.value} value={cat.value}>
                          {cat.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="level">Priority Level</Label>
                  <Select value={level} onValueChange={setLevel}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select priority..." />
                    </SelectTrigger>
                    <SelectContent>
                      {PRIORITY_LEVELS.map((prio) => (
                        <SelectItem key={prio.value} value={prio.value}>
                          {prio.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </TabsContent>

                        {/* Attachments Tab */}
            <TabsContent value="attachments" className="space-y-4">
              <div>
                <h3 className="font-semibold mb-3">Existing Attachments</h3>
                {ticket.attachments && ticket.attachments.length > 0 ? (
                  <div className="space-y-2 mb-4">
                    {ticket.attachments.map((att) => {
                      const displayName = att.file_path?.split("/").pop() || att.file_path
                      return (
                        <div
                          key={att.id}
                          className="flex items-center justify-between p-2 bg-gray-50 rounded border"
                        >
                          <div>
                            <p className="text-sm font-medium text-gray-900">
                              {displayName}
                            </p>
                            <p className="text-xs text-gray-500">{att.type}</p>
                          </div>
                          <div className="flex gap-2">
                            <a
                              href={`/api/tickets/${ticket.id}/attachments/${att.id}/download`}
                              className="text-blue-600 hover:text-blue-800 text-sm"
                              download
                            >
                              Download
                            </a>
                            <button
                              type="button"
                              onClick={() => handleDeleteAttachment(att.id)}
                              className="text-red-600 hover:text-red-800 text-sm"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500 mb-4">No attachments yet</p>
                )}
              </div>
            
              <div className="border-t pt-4">
                <h3 className="font-semibold mb-3">Add New Attachments</h3>
                {attachments.length > 0 && (
                  <div className="space-y-2 mb-4">
                    {attachments.map((att) => (
                      <div
                        key={att.id}
                        className="flex items-center justify-between p-2 bg-white rounded border"
                      >
                        <span className="text-sm text-gray-600">{att.name}</span>
                        <button
                          type="button"
                          onClick={() => removeAttachment(att.id)}
                          className="text-red-500 hover:text-red-700"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full"
                  disabled={isLoading}
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add File
                </Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  onChange={handleFileSelect}
                  className="hidden"
                  disabled={isLoading}
                />
              </div>
            </TabsContent>

            {/* RCA Tab - Only for closed tickets */}
            {ticket.status === "closed" && (
              <TabsContent value="rca" className="space-y-4">
                {ticket.rca ? (
                  <div className="p-4 bg-blue-50 rounded-lg mb-4">
                    <p className="text-sm text-blue-900">
                      RCA already exists for this ticket. You can view it in the RCA
                      tab on the ticket detail page.
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="closed-at" className="flex items-center gap-2">
                        <Calendar className="h-4 w-4" />
                        Ticket Closed Date
                      </Label>
                      <Input
                        id="closed-at"
                        type="datetime-local"
                        value={closedAt}
                        onChange={(e) => setClosedAt(e.target.value)}
                        disabled={isLoading}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="rca-description">
                        Root Cause Description
                      </Label>
                      <Textarea
                        id="rca-description"
                        placeholder="Describe the root cause of the issue..."
                        value={rootCauseDescription}
                        onChange={(e) => setRootCauseDescription(e.target.value)}
                        disabled={isLoading}
                        rows={3}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="contributing-factors">
                        Contributing Factors
                      </Label>
                      <Textarea
                        id="contributing-factors"
                        placeholder="List factors (one per line)..."
                        value={contributingFactors}
                        onChange={(e) => setContributingFactors(e.target.value)}
                        disabled={isLoading}
                        rows={2}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="prevention-measures">
                        Prevention Measures
                      </Label>
                      <Textarea
                        id="prevention-measures"
                        placeholder="What steps should be taken to prevent this in the future?..."
                        value={preventionMeasures}
                        onChange={(e) => setPreventionMeasures(e.target.value)}
                        disabled={isLoading}
                        rows={2}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="resolution-steps">
                        Resolution Steps Taken
                      </Label>
                      <Textarea
                        id="resolution-steps"
                        placeholder="List steps taken to resolve (one per line)..."
                        value={resolutionSteps}
                        onChange={(e) => setResolutionSteps(e.target.value)}
                        disabled={isLoading}
                        rows={2}
                      />
                    </div>
                  </>
                )}
              </TabsContent>
            )}
          </Tabs>

          {/* Action Buttons */}
          <div className="flex gap-2 justify-end border-t pt-4">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isLoading}>
              {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {isLoading ? "Saving..." : "Save"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}