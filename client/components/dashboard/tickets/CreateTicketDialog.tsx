// client/components/dashboard/tickets/CreateTicketDialog.tsx
"use client"

import { useState, useEffect, useRef } from "react"
import { ticketService, CreateTicketRequest, AddAttachmentRequest, AddRCARequest } from "@/services/ticket.service"
import { userService, User } from "@/services/user.service"
import { companyService, Company } from "@/services/company.service"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
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
import { Loader2, Plus, AlertCircle, Calendar, Building2, Trash2, FileUp } from "lucide-react"

interface CreateTicketDialogProps {
  currentUserId: string
  onTicketCreated: () => void
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

const STATUS_OPTIONS = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
  { value: "reopened", label: "Reopened" },
]

export default function CreateTicketDialog({
  currentUserId,
  onTicketCreated,
}: CreateTicketDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Company state
  const [companies, setCompanies] = useState<Company[]>([])
  const [loadingCompanies, setLoadingCompanies] = useState(true)
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>("")
  
  // Engineers state
  const [engineers, setEngineers] = useState<User[]>([])
  const [loadingEngineers, setLoadingEngineers] = useState(true)

  // Form state
  const [subject, setSubject] = useState("")
  const [summary, setSummary] = useState("")
  const [description, setDescription] = useState("")
  const [category, setCategory] = useState("")
  const [level, setLevel] = useState("")
  const [assignedEngineer, setAssignedEngineer] = useState<string>("")
  const [isOlderTicket, setIsOlderTicket] = useState(false)
  const [createdAt, setCreatedAt] = useState<string>("")
  const [status, setStatus] = useState<string>("")
  const [ticketNo, setTicketNo] = useState<string>("")
  // RCA state (for older closed tickets)
  const [rootCauseDescription, setRootCauseDescription] = useState("")
  const [contributingFactors, setContributingFactors] = useState<string>("")
  const [preventionMeasures, setPreventionMeasures] = useState("")
  const [resolutionSteps, setResolutionSteps] = useState<string>("")
  
  // Attachments state
  const [attachments, setAttachments] = useState<AttachmentFile[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      fetchCompanies()
      fetchEngineers()
    }
  }, [open])

  const fetchCompanies = async () => {
    try {
      setLoadingCompanies(true)
      const result = await companyService.getCompanies(500)
      setCompanies(result.companies)
      if (result.companies.length > 0) {
        setSelectedCompanyId(result.companies[0].id)
      }
    } catch (err) {
      console.error("Failed to load companies:", err)
      setError("Failed to load companies")
    } finally {
      setLoadingCompanies(false)
    }
  }

  const fetchEngineers = async () => {
    try {
      setLoadingEngineers(true)
      const result = await userService.getUsers()
      setEngineers(
        result.users?.filter(
          (u) => u.role === "support_engineer" || u.role === "supervisor"
        ) || []
      )
    } catch (err) {
      console.error("Failed to load engineers:", err)
    } finally {
      setLoadingEngineers(false)
    }
  }

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    // Validation
    if (!selectedCompanyId) {
      setError("Please select a company")
      return
    }

    if (!subject.trim()) {
      setError("Subject is required")
      return
    }

    if (!description.trim()) {
      setError("Description is required")
      return
    }

    if (isOlderTicket && status === "closed") {
      if (!rootCauseDescription.trim()) {
        setError("Root cause description is required for closed tickets")
        return
      }
    }

    try {
      setLoading(true)

      // Create ticket
      const createRequest: CreateTicketRequest = {
        subject: subject.trim(),
        detailed_description: description.trim(),
        summary: summary.trim() || undefined,
        company_id: selectedCompanyId,
        raised_by_user_id: currentUserId,
        category: category || undefined,
        level: level || undefined,
        assigned_engineer_id: assignedEngineer || undefined,
        created_at: isOlderTicket && createdAt ? new Date(createdAt).toISOString() : undefined,
        ticket_no: ticketNo || undefined,
        status: isOlderTicket && status ? status : undefined,
      }

      const createdTicket = await ticketService.createTicket(createRequest)

      // Add attachments if any
      if (attachments.length > 0) {
        for (const attachment of attachments) {
          try {
            const attachmentRequest: AddAttachmentRequest = {
              file_path: attachment.file.name,
              file_name: attachment.file.name,
              attachment_type: "document",
              mime_type: attachment.file.type,
              file_size: attachment.file.size,
              created_by_user_id: currentUserId,
            }
            await ticketService.addAttachment(createdTicket.id, attachmentRequest)
          } catch (err) {
            console.error(`Failed to add attachment ${attachment.name}:`, err)
          }
        }
      }

      // Add RCA if older closed ticket
      if (isOlderTicket && status === "closed" && rootCauseDescription.trim()) {
        try {
          const rcaRequest: AddRCARequest = {
            root_cause_description: rootCauseDescription.trim(),
            created_by_user_id: currentUserId,
            contributing_factors: contributingFactors
              .split("\n")
              .map((f) => f.trim())
              .filter((f) => f.length > 0),
            prevention_measures: preventionMeasures.trim() || undefined,
            resolution_steps: resolutionSteps
              .split("\n")
              .map((s) => s.trim())
              .filter((s) => s.length > 0),
          }
          await ticketService.addRCA(createdTicket.id, rcaRequest)
        } catch (err) {
          console.error("Failed to add RCA:", err)
        }
      }

      // Reset form
      setSubject("")
      setSummary("")
      setDescription("")
      setCategory("")
      setLevel("")
      setAssignedEngineer("")
      setCreatedAt("")
      setIsOlderTicket(false)
      setStatus("")
      setTicketNo("")
      setRootCauseDescription("")
      setContributingFactors("")
      setPreventionMeasures("")
      setResolutionSteps("")
      setAttachments([])
      setError(null)

      setOpen(false)
      onTicketCreated()
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Failed to create ticket"
      const apiError = err as { response?: { data?: { detail?: string } } }
      setError(apiError?.response?.data?.detail || errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const shouldShowRCA = isOlderTicket && status === "closed"

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          Create Ticket
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-4xl max-h-[95vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create New Support Ticket</DialogTitle>
          <DialogDescription>
            Add a new support ticket to the system. Select a company for this ticket.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Company Selection */}
          <div className="space-y-3 bg-purple-50 border border-purple-200 rounded-lg p-4">
            <Label className="font-semibold flex items-center">
              <Building2 className="h-4 w-4 mr-2" />
              Company <span className="text-red-500">*</span>
            </Label>

            {loadingCompanies ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-4 w-4 animate-spin text-gray-600" />
              </div>
            ) : companies.length > 0 ? (
              <>
                <Select
                  value={selectedCompanyId}
                  onValueChange={setSelectedCompanyId}
                  disabled={loading}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a company..." />
                  </SelectTrigger>
                  <SelectContent>
                    {companies.map((company) => (
                      <SelectItem key={company.id} value={company.id}>
                        {company.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-gray-600">
                  {companies.length} compan{companies.length !== 1 ? "ies" : "y"} available
                </p>
              </>
            ) : (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  No companies available. Please contact an admin to add companies.
                </AlertDescription>
              </Alert>
            )}
          </div>

          {/* Subject */}
          <div className="space-y-2">
            <Label htmlFor="subject" className="font-semibold">
              Subject <span className="text-red-500">*</span>
            </Label>
            <Input
              id="subject"
              placeholder="Brief description of the issue"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              disabled={loading}
              className="min-h-10"
            />
            <p className="text-xs text-gray-500">Minimum 3 characters</p>
          </div>

          {/* Summary */}
          <div className="space-y-2">
            <Label htmlFor="summary" className="font-semibold">
              Summary
            </Label>
            <Input
              id="summary"
              placeholder="Optional short summary (2-3 sentences)"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              disabled={loading}
              className="min-h-10"
            />
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="description" className="font-semibold">
              Detailed Description <span className="text-red-500">*</span>
            </Label>
            <Textarea
              id="description"
              placeholder="Provide detailed information about the issue, including steps to reproduce, error messages, etc."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={5}
              disabled={loading}
              className="resize-none"
            />
            <p className="text-xs text-gray-500">Minimum 10 characters</p>
          </div>

          {/* Category and Priority */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="category" className="font-semibold">
                Category
              </Label>
              <Select value={category} onValueChange={setCategory} disabled={loading}>
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
              <Label htmlFor="level" className="font-semibold">
                Priority Level
              </Label>
              <Select value={level} onValueChange={setLevel} disabled={loading}>
                <SelectTrigger>
                  <SelectValue placeholder="Select level..." />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITY_LEVELS.map((lv) => (
                    <SelectItem key={lv.value} value={lv.value}>
                      {lv.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Assign Engineer */}
          <div className="space-y-2">
            <Label htmlFor="engineer" className="font-semibold">
              Assign To Support Engineer
            </Label>
            {loadingEngineers ? (
              <div className="flex items-center justify-center py-4 bg-gray-50 rounded">
                <Loader2 className="h-4 w-4 animate-spin text-gray-600" />
              </div>
            ) : engineers.length > 0 ? (
              <Select
                value={assignedEngineer || "unassigned"}
                onValueChange={(value) => setAssignedEngineer(value === "unassigned" ? "" : value)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select engineer..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="unassigned">Unassigned</SelectItem>
                  {engineers.map((eng) => (
                    <SelectItem key={eng.id} value={eng.id}>
                      {eng.name} ({eng.email})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <p className="text-sm text-gray-500 py-2">No engineers available</p>
            )}
          </div>

          {/* Older Ticket Option */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="olderTicket"
                checked={isOlderTicket}
                onChange={(e) => setIsOlderTicket(e.target.checked)}
                disabled={loading}
                className="h-4 w-4 rounded cursor-pointer"
              />
              <div className="flex-1">
                <Label htmlFor="olderTicket" className="cursor-pointer font-semibold">
                  <Calendar className="h-4 w-4 inline mr-2" />
                  This is an older ticket
                </Label>
                <p className="text-sm text-gray-600 mt-1">
                  Set a custom creation date for historical tickets or ticket migration
                </p>
              </div>
            </div>

            {isOlderTicket && (
              <div className="mt-4 pt-4 border-t border-blue-200 space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="ticketNo" className="font-semibold">
                      Ticket Number
                    </Label>
                    <Input
                      id="ticketNo"
                      placeholder="Auto-generated if empty"
                      value={ticketNo}
                      onChange={(e) => setTicketNo(e.target.value)}
                      disabled={loading}
                      className="min-h-10"
                    />
                    <p className="text-xs text-gray-500">Leave empty for auto-increment</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="createdAt" className="font-semibold">
                      Creation Date & Time
                    </Label>
                    <Input
                      id="createdAt"
                      type="datetime-local"
                      value={createdAt}
                      onChange={(e) => setCreatedAt(e.target.value)}
                      disabled={loading}
                      className="min-h-10"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="status" className="font-semibold">
                      Ticket Status
                    </Label>
                    <Select value={status} onValueChange={setStatus} disabled={loading}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select status..." />
                      </SelectTrigger>
                      <SelectContent>
                        {STATUS_OPTIONS.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <p className="text-xs text-gray-500">
                  Select the date and time when this ticket was originally created, and its final status
                </p>
              </div>
            )}
          </div>

          {/* RCA Section - shown only for closed older tickets */}
          {shouldShowRCA && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 space-y-4">
              <h3 className="font-semibold text-amber-900 flex items-center">
                <AlertCircle className="h-4 w-4 mr-2" />
                Root Cause Analysis (for closed ticket)
              </h3>

              <div className="space-y-2">
                <Label htmlFor="rootCause" className="font-semibold">
                  Root Cause Description <span className="text-red-500">*</span>
                </Label>
                <Textarea
                  id="rootCause"
                  placeholder="Describe the root cause of the issue..."
                  value={rootCauseDescription}
                  onChange={(e) => setRootCauseDescription(e.target.value)}
                  rows={3}
                  disabled={loading}
                  className="resize-none"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="factors" className="font-semibold">
                  Contributing Factors
                </Label>
                <Textarea
                  id="factors"
                  placeholder="Enter each contributing factor on a new line..."
                  value={contributingFactors}
                  onChange={(e) => setContributingFactors(e.target.value)}
                  rows={2}
                  disabled={loading}
                  className="resize-none"
                />
                <p className="text-xs text-gray-500">One factor per line</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="prevention" className="font-semibold">
                  Prevention Measures
                </Label>
                <Textarea
                  id="prevention"
                  placeholder="What measures can prevent this issue in the future..."
                  value={preventionMeasures}
                  onChange={(e) => setPreventionMeasures(e.target.value)}
                  rows={2}
                  disabled={loading}
                  className="resize-none"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="resolutionSteps" className="font-semibold">
                  Resolution Steps
                </Label>
                <Textarea
                  id="resolutionSteps"
                  placeholder="Enter each resolution step on a new line..."
                  value={resolutionSteps}
                  onChange={(e) => setResolutionSteps(e.target.value)}
                  rows={2}
                  disabled={loading}
                  className="resize-none"
                />
                <p className="text-xs text-gray-500">One step per line</p>
              </div>
            </div>
          )}

          {/* Attachments Section */}
          <div className="space-y-3 border border-gray-200 rounded-lg p-4">
            <Label className="font-semibold flex items-center">
              <FileUp className="h-4 w-4 mr-2" />
              Attachments
            </Label>
            <p className="text-sm text-gray-600">
              Add any relevant files, logs, or screenshots to help support the ticket
            </p>

            {/* File Input */}
            <div className="space-y-2">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleFileSelect}
                disabled={loading}
                className="hidden"
                accept="*/*"
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading}
                className="w-full"
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Files
              </Button>
            </div>

            {/* Attachments List */}
            {attachments.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-gray-700">
                  {attachments.length} file{attachments.length !== 1 ? "s" : ""} selected
                </p>
                <div className="space-y-2 max-h-40 overflow-y-auto">
                  {attachments.map((att) => (
                    <div
                      key={att.id}
                      className="flex items-center justify-between bg-gray-50 p-2 rounded border border-gray-200"
                    >
                      <span className="text-sm text-gray-700 truncate">{att.name}</span>
                      <button
                        type="button"
                        onClick={() => removeAttachment(att.id)}
                        disabled={loading}
                        className="text-red-500 hover:text-red-700"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={loading || companies.length === 0} className="min-w-32">
              {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Create Ticket
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}