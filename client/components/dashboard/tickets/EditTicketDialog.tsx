// client/components/dashboard/tickets/EditTicketDialog.tsx

"use client"

import { useState, useRef } from "react"
import { useAuth } from "@/hooks/useAuth"
import { TicketDetail } from "@/services/ticket.service"
import { ticketService, AddRCARequest } from "@/services/ticket.service"
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
import { Loader2, AlertCircle, Calendar, Trash2, Plus, FileUp } from "lucide-react"

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
    created_at?: string
    closed_at?:string
  }) => Promise<void>
  fetchTicket?: () => Promise<void>
  isLoading: boolean
}

interface AttachmentFile {
  id: string
  name: string
  file: File
}

const PRIORITY_LEVELS = [
  { value: "level-1", label: "Level 1 - Critical" },
  { value: "level-2", label: "Level 2 - High" },
  { value: "level-3", label: "Level 3 - Medium" },
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
  const { admin: currentUser } = useAuth()

  // Form state
  const [error, setError] = useState<string | null>(null)
  const [subject, setSubject] = useState(ticket.subject)
  const [summary, setSummary] = useState(ticket.summary || "")
  const [description, setDescription] = useState(ticket.detailed_description)
  const [category, setCategory] = useState(ticket.category || "")
  const [level, setLevel] = useState(ticket.level || "")

  // Ticket attachments state
  const [newAttachments, setNewAttachments] = useState<AttachmentFile[]>([])
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
  const [createdAt, setCreatedAt] = useState(
    new Date(ticket.created_at).toISOString().slice(0, 16)
  )

  const [rcaAttachments, setRcaAttachments] = useState<AttachmentFile[]>([])
  const [closedAt, setClosedAt] = useState(
    ticket.closed_at
      ? new Date(ticket.closed_at).toISOString().slice(0, 16)
      : ""
  )

  const rcaFileInputRef = useRef<HTMLInputElement>(null)

  

  // Handlers for RCA attachments
  const handleRcaFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.currentTarget.files
    if (!files) return

    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      const id = Math.random().toString(36).substring(2, 11)
      setRcaAttachments((prev) => [...prev, { id, name: file.name, file }])
    }

    if (rcaFileInputRef.current) {
      rcaFileInputRef.current.value = ""
    }
  }

  const removeRcaAttachment = (id: string) => {
    setRcaAttachments((prev) => prev.filter((att) => att.id !== id))
  }

  // Delete existing ticket attachment
  const handleDeleteAttachment = async (attachmentId: string) => {
    try {
      const token = localStorage.getItem("auth_token")
      if (!token) {
        throw new Error("Not authenticated. Please log in again.")
      }

      const response = await fetch(
        `/api/tickets/${ticket.id}/attachments/${attachmentId}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(
          errorData.detail || `Delete failed with status ${response.status}`
        )
      }

      if (fetchTicket) {
        await fetchTicket()
      }
      console.log(`✓ Attachment deleted`)
    } catch (err) {
      console.error(`Failed to delete attachment:`, err)
      setError(
        `Failed to delete attachment: ${
          err instanceof Error ? err.message : "Unknown error"
        }`
      )
    }
  }

  // Upload new ticket attachments
  const uploadTicketAttachments = async (): Promise<void> => {
    if (newAttachments.length === 0) return

    for (const attachment of newAttachments) {
      try {
        const formData = new FormData()
        formData.append("file", attachment.file)

        const token = localStorage.getItem("auth_token")

        const response = await fetch(
          `/api/tickets/${ticket.id}/upload-attachment`,
          {
            method: "POST",
            body: formData,
            headers: {
              ...(token && { Authorization: `Bearer ${token}` }),
            },
          }
        )

        if (!response.ok) {
          const error = await response.json()
          throw new Error(error.detail || "Failed to upload attachment")
        }

        console.log(`✓ Attachment uploaded: ${attachment.name}`)
      } catch (err) {
        console.error(`Failed to upload attachment ${attachment.name}:`, err)
        throw new Error(
          `Failed to upload ${attachment.name}: ${
            err instanceof Error ? err.message : "Unknown error"
          }`
        )
      }
    }
  }

  // Upload RCA attachments
  const uploadRcaAttachments = async (): Promise<string[]> => {
    const uploadedPaths: string[] = []

    for (const attachment of rcaAttachments) {
      try {
        const formData = new FormData()
        formData.append("file", attachment.file)

        const token = localStorage.getItem("auth_token")

        // Use a separate endpoint for RCA attachments
        const response = await fetch(
          `/api/tickets/${ticket.id}/upload-rca-attachment`,
          {
            method: "POST",
            body: formData,
            headers: {
              ...(token && { Authorization: `Bearer ${token}` }),
            },
          }
        )

        if (!response.ok) {
          console.warn(`Failed to upload RCA attachment ${attachment.name}`)
        } else {
          const data = await response.json()
          uploadedPaths.push(data.file_path || attachment.name)
          console.log(`✓ RCA Attachment uploaded: ${attachment.name}`)
        }
      } catch (err) {
        console.error(`Failed to upload RCA attachment ${attachment.name}:`, err)
      }
    }

    return uploadedPaths
  }

  // Main save handler
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
          created_at: new Date(createdAt).toISOString(),  
          closed_at : new Date(closedAt).toISOString(),
        })

      // Upload ticket attachments
      if (newAttachments.length > 0) {
        await uploadTicketAttachments()
      }
    // Add or update RCA if closed
    if (ticket.status === "closed" && rootCauseDescription.trim()) {
      if (rootCauseDescription.trim().length < 10) {
        setError("Root cause description must be at least 10 characters")
        return
      }

      if (currentUser?.id) {
        // Upload RCA attachments first
        const uploadedRcaPaths = await uploadRcaAttachments()

        // Pass uploaded paths to RCA creation
        // Use root_cause (not root_cause_description) for the API
        await ticketService.createRCA(ticket.id, {
          root_cause: rootCauseDescription.trim(),
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
          rca_attachments: uploadedRcaPaths,
        })

        setNewAttachments([])
        setRcaAttachments([])
      }
    } else {
      setNewAttachments([])
    }

    // Refresh ticket data before closing
    if (fetchTicket) {
      await fetchTicket()
    }

    onOpenChange(false)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Failed to save ticket"
      const apiError = err as { response?: { data?: { detail?: string } } }
      setError(apiError?.response?.data?.detail || errorMessage)
    }
  }


  // Delete existing RCA attachment
  const handleDeleteRcaAttachment = async (attachmentId: string) => {
    try {
      const token = localStorage.getItem("auth_token")
      if (!token) {
        throw new Error("Not authenticated. Please log in again.")
      }

      const response = await fetch(
        `/api/tickets/${ticket.id}/rca-attachments/${attachmentId}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(
          errorData.detail || `Delete failed with status ${response.status}`
        )
      }

      if (fetchTicket) {
        await fetchTicket()
      }
      console.log(`✓ RCA Attachment deleted`)
    } catch (err) {
      console.error(`Failed to delete RCA attachment:`, err)
      setError(
        `Failed to delete RCA attachment: ${
          err instanceof Error ? err.message : "Unknown error"
        }`
      )
    }
  }


  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[95vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Ticket</DialogTitle>
          <DialogDescription>
            Update ticket information, add attachments, or manage RCA for closed tickets
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
            <TabsList className="grid w-full gap-0" style={{ gridTemplateColumns: `repeat(${ticket.status === "closed" ? 3 : 2}, 1fr)` }}>
              <TabsTrigger value="details">Details</TabsTrigger>
              <TabsTrigger value="attachments">Attachments</TabsTrigger>
              {ticket.status === "closed" && (
                <TabsTrigger value="rca">RCA</TabsTrigger>
              )}
            </TabsList>

            {/* Details Tab */}
            <TabsContent value="details" className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="subject">Subject *</Label>
                <Input
                  id="subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  disabled={isLoading}
                  placeholder="Ticket subject"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="summary">Summary</Label>
                <Input
                  id="summary"
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  disabled={isLoading}
                  placeholder="Brief summary (optional)"
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
                  placeholder="Detailed description of the issue"
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

              <div className="space-y-2">
                <Label htmlFor="created-at" className="flex items-center gap-2">
                  <Calendar className="h-4 w-4" />
                  Date Created
                </Label>
                <Input
                  id="created-at"
                  type="datetime-local"
                  value={createdAt}
                  onChange={(e) => setCreatedAt(e.target.value)}
                  disabled={isLoading}
                />
              </div>
            </TabsContent>

          {/* Attachments Tab */}
            <TabsContent value="attachments" className="space-y-4 py-4">
              {/* New Attachments Section */}
              <div className="space-y-2 p-3 bg-purple-50 rounded border border-purple-200">
                <Label className="font-semibold flex items-center gap-2 text-purple-900">
                  <FileUp className="h-4 w-4" />
                  Add New Attachments
                </Label>
                <p className="text-xs text-purple-800">
                  Upload additional files to this ticket
                </p>
                <div className="space-y-3 mt-2">
                  {/* New attachments to upload */}
                  {newAttachments.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-purple-900">Files to Upload:</p>
                      {newAttachments.map((att) => (
                        <div
                          key={att.id}
                          className="flex items-center justify-between p-2 bg-white rounded border"
                        >
                          <span className="text-sm text-gray-700">{att.name}</span>
                          <button
                            type="button"
                            onClick={() => setNewAttachments((prev) => prev.filter((a) => a.id !== att.id))}
                            className="text-red-500 hover:text-red-700"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
            
                  {/* Add new files button */}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isLoading}
                    className="gap-2"
                  >
                    <Plus className="h-4 w-4" />
                    Add File
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    onChange={(e) => {
                      const files = e.currentTarget.files
                      if (!files) return
            
                      for (let i = 0; i < files.length; i++) {
                        const file = files[i]
                        const id = Math.random().toString(36).substring(2, 11)
                        setNewAttachments((prev) => [...prev, { id, name: file.name, file }])
                      }
            
                      if (fileInputRef.current) {
                        fileInputRef.current.value = ""
                      }
                    }}
                    className="hidden"
                    disabled={isLoading}
                  />
                </div>
              </div>
            
              {/* Existing Attachments Section */}
              <div>
                <h3 className="font-semibold mb-3 flex items-center gap-2">
                  <FileUp className="h-4 w-4" />
                  Existing Attachments
                </h3>
                {ticket.attachments && ticket.attachments.length > 0 && (
                  <div className="space-y-2 p-3 bg-blue-50 rounded border border-blue-200">
                    <h3 className="font-semibold flex items-center gap-2 text-blue-900">
                      <FileUp className="h-4 w-4" />
                      Ticket Attachments
                    </h3>
                    <p className="text-xs text-blue-700 mb-2">
                      These are attachments from the original ticket report
                    </p>
                    <div className="space-y-2">
                      {ticket.attachments.map((att) => {
                        const displayName = att.file_path?.split("/").pop() || att.file_path
                        return (
                          <div
                            key={att.id}
                            className="flex items-center justify-between p-2 bg-white rounded border"
                          >
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-gray-900 truncate">
                                {displayName}
                              </p>
                              <p className="text-xs text-gray-500">{att.type}</p>
                            </div>
                            <div className="flex gap-2 ml-2 flex-shrink-0">
                              <a
                                href={`/api/tickets/${ticket.id}/attachments/${att.id}/download`}
                                className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                                download
                              >
                                Download
                              </a>
                              <button
                                type="button"
                                onClick={() => handleDeleteAttachment(att.id)}
                                className="text-red-600 hover:text-red-800 text-xs font-medium"
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            </TabsContent>

            {/* RCA Tab */}
            {ticket.status === "closed" && (
              <TabsContent value="rca" className="space-y-4 py-4">
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
                    Root Cause Description *
                  </Label>
                  <Textarea
                    id="rca-description"
                    placeholder="What was the underlying cause of this issue?"
                    value={rootCauseDescription}
                    onChange={(e) => setRootCauseDescription(e.target.value)}
                    disabled={isLoading}
                    rows={3}
                  />
                  <p className="text-xs text-gray-500">Minimum 10 characters</p>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="contributing-factors">
                    Contributing Factors
                  </Label>
                  <Textarea
                    id="contributing-factors"
                    placeholder="List factors that contributed (one per line)"
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
                    placeholder="How can this issue be prevented in the future?"
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
                    placeholder="List the steps taken to resolve (one per line)"
                    value={resolutionSteps}
                    onChange={(e) => setResolutionSteps(e.target.value)}
                    disabled={isLoading}
                    rows={2}
                  />
                </div>
                
                {/* RCA Attachments Section */}
                <div className="space-y-2 p-3 bg-amber-50 rounded border border-amber-200">
                  <Label className="font-semibold flex items-center gap-2 text-amber-900">
                    <FileUp className="h-4 w-4" />
                    RCA Attachments
                  </Label>
                  <p className="text-xs text-amber-800">
                    Upload screenshots, guides, documentation, or reference materials specific to this RCA solution
                  </p>
                  <div className="space-y-3 mt-2">
                    {/* Display existing RCA attachments if any */}
                      {ticket.rca?.attachments && ticket.rca.attachments.length > 0 && (
                      <div className="space-y-2 p-2 bg-green-50 rounded">
                        <p className="text-xs font-medium text-green-900">Existing RCA Attachments:</p>
                          {ticket.rca.attachments.map((att) => {
                          const displayName = att.file_path?.split("/").pop() || att.file_path
                          return (
                            <div
                              key={att.id}
                              className="flex items-center justify-between p-2 bg-white rounded border border-green-200"
                            >
                              <span className="text-sm text-gray-700 truncate">{displayName}</span>
                              <button
                                type="button"
                                onClick={() => handleDeleteRcaAttachment(att.id)}
                                className="text-red-600 hover:text-red-800 text-xs font-medium ml-2 flex-shrink-0"
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </div>
                          )
                        })}
                      </div>
                    )}
                
                    {/* New RCA attachments to upload */}
                    {rcaAttachments.length > 0 && (
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-amber-900">New Files to Upload:</p>
                        {rcaAttachments.map((att) => (
                          <div
                            key={att.id}
                            className="flex items-center justify-between p-2 bg-white rounded border"
                          >
                            <span className="text-sm text-gray-700">{att.name}</span>
                            <button
                              type="button"
                              onClick={() => removeRcaAttachment(att.id)}
                              className="text-red-500 hover:text-red-700"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                
                    {/* Add new RCA files button */}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => rcaFileInputRef.current?.click()}
                      disabled={isLoading}
                      className="gap-2"
                    >
                      <Plus className="h-4 w-4" />
                      Add RCA File
                    </Button>
                    <input
                      ref={rcaFileInputRef}
                      type="file"
                      multiple
                      onChange={handleRcaFileSelect}
                      className="hidden"
                      disabled={isLoading}
                    />
                  </div>
                </div>
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
              {isLoading ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}