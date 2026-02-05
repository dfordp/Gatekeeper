// client/components/dashboard/tickets/CreateTicketDialog.tsx
"use client"

import { useState, useEffect, useRef } from "react"
import { ticketService, CreateTicketRequest, AddRCARequest } from "@/services/ticket.service"
import { userService, User } from "@/services/user.service"
import { companyService, Company } from "@/services/company.service"
import { irService } from "@/services/ir.service"
import { useTicketCreation } from "@/hooks/useTicketCreation"
import TicketProgressCard from "./TicketProgressCard"
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
import { Loader2, Plus, AlertCircle, Calendar, Building2, Trash2, FileUp, X } from "lucide-react"
import { toISODateString } from "@/lib/date-utils"
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
  // Dialog state
  const [open, setOpen] = useState(false)
  const [dialogStep, setDialogStep] = useState<"form" | "progress">("form")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Ticket creation hook
  const ticketCreation = useTicketCreation()

  // Company state
  const [companies, setCompanies] = useState<Company[]>([])
  const [loadingCompanies, setLoadingCompanies] = useState(true)
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>("")

  // Users from selected company
  const [companyUsers, setCompanyUsers] = useState<User[]>([])
  const [loadingCompanyUsers, setLoadingCompanyUsers] = useState(false)
  const [userSearch, setUserSearch] = useState<string>("")

  // Create new user state
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [newUserName, setNewUserName] = useState<string>("")
  const [newUserEmail, setNewUserEmail] = useState<string>("")
  const [creatingUser, setCreatingUser] = useState(false)

  // Engineers state
  const [engineers, setEngineers] = useState<User[]>([])
  const [loadingEngineers, setLoadingEngineers] = useState(true)

  // Form state
  const [raisedByUserId, setRaisedByUserId] = useState<string>("")
  const [raisedByUserName, setRaisedByUserName] = useState<string>("")
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
  const [closedAt, setClosedAt] = useState<string>("")

  // IR state (for older tickets that had IR raised)
  const [hasIR, setHasIR] = useState(false)
  const [irNumber, setIrNumber] = useState<string>("")
  const [irVendor, setIrVendor] = useState<string>("siemens")
  const [irRaisedAt, setIrRaisedAt] = useState<string>("")
  const [irExpectedResolutionDate, setIrExpectedResolutionDate] = useState<string>("")
  const [irNotes, setIrNotes] = useState<string>("")
  const [irClosedAt, setIrClosedAt] = useState<string>("");

  // Attachments state
  const [attachments, setAttachments] = useState<AttachmentFile[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [rcaAttachments, setRcaAttachments] = useState<AttachmentFile[]>([])
  const rcaFileInputRef = useRef<HTMLInputElement>(null)

  // Load data when dialog opens
  useEffect(() => {
    if (open) {
      fetchCompanies()
      fetchEngineers()
    }
  }, [open])

  // Fetch users when company changes
  useEffect(() => {
    if (selectedCompanyId) {
      fetchCompanyUsers(selectedCompanyId)
    }
  }, [selectedCompanyId])

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

  const fetchCompanyUsers = async (companyId: string) => {
    try {
      setLoadingCompanyUsers(true)
      const result = await userService.getUsers(companyId, undefined, 500)
      setCompanyUsers(result.users || [])
      if (result.users && result.users.length > 0 && !raisedByUserId) {
        setRaisedByUserId(result.users[0].id)
        setRaisedByUserName(result.users[0].name)
      }
    } catch (err) {
      console.error("Failed to load company users:", err)
      setError("Failed to load users from company")
    } finally {
      setLoadingCompanyUsers(false)
    }
  }

  const fetchEngineers = async () => {
    try {
      setLoadingEngineers(true)
      const result = await userService.getUsers(undefined, undefined, 500)
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

  const handleCreateUser = async () => {
    if (!newUserName.trim()) {
      setError("User name is required")
      return
    }

    if (!newUserEmail.trim()) {
      setError("User email is required")
      return
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(newUserEmail)) {
      setError("Invalid email format")
      return
    }

    try {
      setCreatingUser(true)
      const newUser = await userService.createUser({
        name: newUserName.trim(),
        email: newUserEmail.trim(),
        company_id: selectedCompanyId,
        role: "external",
      })

      setCompanyUsers([...companyUsers, newUser])
      setRaisedByUserId(newUser.id)
      setRaisedByUserName(newUser.name)

      setNewUserName("")
      setNewUserEmail("")
      setShowCreateUser(false)
      setError(null)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Failed to create user"
      const apiError = err as { response?: { data?: { detail?: string } } }
      setError(apiError?.response?.data?.detail || errorMessage)
    } finally {
      setCreatingUser(false)
    }
  }

  const filteredUsers = userSearch.trim()
    ? companyUsers.filter(
        (u) =>
          u.name.toLowerCase().includes(userSearch.toLowerCase()) ||
          u.email.toLowerCase().includes(userSearch.toLowerCase())
      )
    : companyUsers

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

  const resetForm = () => {
    setRaisedByUserId("")
    setRaisedByUserName("")
    setSubject("")
    setSummary("")
    setDescription("")
    setCategory("")
    setLevel("")
    setAssignedEngineer("")
    setCreatedAt("")
    setIsOlderTicket(false)
    setStatus("")
    setClosedAt("")
    setTicketNo("")
    setRootCauseDescription("")
    setContributingFactors("")
    setPreventionMeasures("")
    setResolutionSteps("")
    setAttachments([])
    setUserSearch("")
    setError(null)
    setLoading(false)
    setRcaAttachments([])
    // Reset IR fields
    setHasIR(false)
    setIrNumber("")
    setIrVendor("siemens")
    setIrRaisedAt("")
    setIrExpectedResolutionDate("")
    setIrNotes("")
    setIrClosedAt("")
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    // Validation
    if (!selectedCompanyId) {
      setError("Please select a company")
      return
    }

    if (!raisedByUserId) {
      setError("Please select who raised this ticket")
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

      const createRequest: CreateTicketRequest = {
        subject: subject.trim(),
        detailed_description: description.trim(),
        summary: summary.trim() || undefined,
        company_id: selectedCompanyId,
        raised_by_user_id: raisedByUserId,
        category: category || undefined,
        level: level || undefined,
        assigned_engineer_id: assignedEngineer || undefined,
        created_at: isOlderTicket && createdAt ? createdAt : undefined,
        ticket_no: ticketNo || undefined,
        status: isOlderTicket && status ? status : undefined,
        closed_at: isOlderTicket && status === "closed" && closedAt ? closedAt : undefined,
      }

      // Debug log to verify
      console.log(`Ticket creation - isOlderTicket: ${isOlderTicket}, status: ${status}, closedAt: "${closedAt}", will send closed_at: ${createRequest.closed_at}`)

      // Create the ticket
      const createdTicket = await ticketService.createTicket(createRequest)

      // ✅ STEP 1: Switch to progress view immediately
      setDialogStep("progress")
      setLoading(false)

      // ✅ STEP 2: Queue all tasks BEFORE starting polling
      console.log(`✓ Ticket created: ${createdTicket.id}, now queueing all tasks...`)

      const attachmentPromise =
        attachments.length > 0 ? processAttachments(createdTicket.id) : Promise.resolve()

      const rcaPromise =
        isOlderTicket && status === "closed" && rootCauseDescription.trim()
          ? addRCAAsync(createdTicket.id)
          : Promise.resolve()

      const irPromise = hasIR && irNumber.trim() ? createIRAsync(createdTicket.id) : Promise.resolve()

      // Wait for all tasks to be queued
      await Promise.all([attachmentPromise, rcaPromise, irPromise])
      console.log(`✓ All tasks queued for ticket: ${createdTicket.id}`)

      // ✅ STEP 3: NOW start polling after all tasks are queued
      ticketCreation.startPolling(createdTicket.id)
      console.log(`✓ Polling started for ticket: ${createdTicket.id}`)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Failed to create ticket"
      const apiError = err as { response?: { data?: { detail?: string } } }
      setError(apiError?.response?.data?.detail || errorMessage)
      setLoading(false)
      setDialogStep("form")
    }
  }

  // Process attachments - MUST return a Promise
  const processAttachments = async (ticketId: string): Promise<void> => {
    try {
      for (const attachment of attachments) {
        try {
          const formData = new FormData()
          formData.append("file", attachment.file)

          const token = localStorage.getItem("auth_token")

          const response = await fetch(`/api/tickets/${ticketId}/upload-attachment`, {
            method: "POST",
            body: formData,
            headers: {
              ...(token && { Authorization: `Bearer ${token}` }),
            },
          })

          if (!response.ok) {
            const error = await response.json()
            console.warn(`Failed to upload attachment ${attachment.name}: ${error.detail}`)
          } else {
            console.log(`✓ Attachment uploaded: ${attachment.name}`)
          }
        } catch (err) {
          console.error(`Failed to upload attachment ${attachment.name}:`, err)
        }
      }
    } catch (err) {
      console.error("Error processing attachments:", err)
      throw err
    }
  }

  // Add RCA in background - MUST return a Promise
  const addRCAAsync = async (ticketId: string): Promise<void> => {
    try {
      if (rootCauseDescription.trim().length < 10) {
        console.warn("Root cause description too short")
        return
      }

      // Upload RCA attachments first
      const uploadedRcaPaths: string[] = []
      for (const attachment of rcaAttachments) {
        try {
          const formData = new FormData()
          formData.append("file", attachment.file)

          const token = localStorage.getItem("auth_token")

          const response = await fetch(`/api/tickets/${ticketId}/upload-attachment`, {
            method: "POST",
            body: formData,
            headers: {
              ...(token && { Authorization: `Bearer ${token}` }),
            },
          })

          if (!response.ok) {
            console.warn(`Failed to upload RCA attachment ${attachment.name}`)
          } else {
            const data = await response.json()
            uploadedRcaPaths.push(data.file_path || attachment.name)
            console.log(`✓ RCA Attachment uploaded: ${attachment.name}`)
          }
        } catch (err) {
          console.error(`Failed to upload RCA attachment ${attachment.name}:`, err)
        }
      }

      const rcaRequest: AddRCARequest = {
        root_cause: rootCauseDescription.trim(),
        created_by_user_id: raisedByUserId,
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
        ticket_closed_at: closedAt ? closedAt : null,
      }
      await ticketService.createRCA(ticketId, rcaRequest)
      console.log("✓ RCA added successfully")
    } catch (err) {
      console.error("Failed to add RCA:", err)
      throw err
    }
  }

  // Create IR for older ticket - MUST return a Promise
  const createIRAsync = async (ticketId: string): Promise<void> => {
    try {
      if (!hasIR || !irNumber.trim()) {
        console.log("No IR to create")
        return
      }
  
      const irRequest = {
        ir_number: irNumber.trim(),
        vendor: irVendor || "siemens",
        expected_resolution_date: irExpectedResolutionDate 
          ?irExpectedResolutionDate: undefined,
        closed_at: irClosedAt
          ? irClosedAt : undefined,
        notes: irNotes.trim() || undefined,
        created_by_user_id: raisedByUserId,
      }
  
      await irService.openIR(ticketId, irRequest)
      console.log(`✓ Incident Report created: ${irNumber}`)
    } catch (err) {
      console.error("Failed to create Incident Report:", err)
      throw err
    }
  }

  const shouldShowRCA = isOlderTicket && status === "closed"

  const handleCloseDialog = () => {
    if (ticketCreation.status?.all_completed) {
      // Only allow closing after completion
      resetForm()
      ticketCreation.reset()
      setDialogStep("form")
      setOpen(false)
      onTicketCreated()
    } else if (dialogStep === "form") {
      // Allow closing during form
      setOpen(false)
    }
  }

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
          <DialogTitle>
            {dialogStep === "form" ? "Create New Support Ticket" : "Ticket Creation Progress"}
          </DialogTitle>
          <DialogDescription>
            {dialogStep === "form"
              ? "Add a new support ticket to the system."
              : "Your ticket is being created and processed asynchronously."}
          </DialogDescription>
        </DialogHeader>

        {/* Progress View */}
        {dialogStep === "progress" && (
          <div className="space-y-6 py-4">
            <TicketProgressCard
              status={ticketCreation.status}
              isPolling={ticketCreation.isPolling}
              onClose={() => {
                resetForm()
                ticketCreation.reset()
                setDialogStep("form")
                setOpen(false)
                onTicketCreated()
              }}
            />
          </div>
        )}

        {/* Form View */}
        {dialogStep === "form" && (
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Company Selection */}
            <div className="space-y-2">
              <Label htmlFor="company" className="font-semibold flex items-center gap-2">
                <Building2 className="h-4 w-4" />
                Select Company *
              </Label>
              <Select value={selectedCompanyId} onValueChange={setSelectedCompanyId}>
                <SelectTrigger>
                  <SelectValue placeholder="Choose a company..." />
                </SelectTrigger>
                <SelectContent>
                  {loadingCompanies ? (
                    <SelectItem disabled value="loading">
                      Loading companies...
                    </SelectItem>
                  ) : (
                    companies.map((company) => (
                      <SelectItem key={company.id} value={company.id}>
                        {company.name}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>

            {/* Raised By User Selection */}
            <div className="space-y-2">
              <Label htmlFor="raised-by" className="font-semibold">
                Who is raising this ticket? *
              </Label>

              {showCreateUser ? (
                <div className="space-y-3 p-4 border rounded-lg bg-blue-50">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm">Create New User</span>
                    <button
                      type="button"
                      onClick={() => {
                        setShowCreateUser(false)
                        setNewUserName("")
                        setNewUserEmail("")
                        setError(null)
                      }}
                      className="text-gray-500 hover:text-gray-700"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="new-user-name" className="text-sm">
                      Full Name *
                    </Label>
                    <Input
                      id="new-user-name"
                      placeholder="e.g., John Doe"
                      value={newUserName}
                      onChange={(e) => setNewUserName(e.target.value)}
                      disabled={creatingUser}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="new-user-email" className="text-sm">
                      Email Address *
                    </Label>
                    <Input
                      id="new-user-email"
                      type="email"
                      placeholder="e.g., john@company.com"
                      value={newUserEmail}
                      onChange={(e) => setNewUserEmail(e.target.value)}
                      disabled={creatingUser}
                    />
                  </div>

                  <div className="flex gap-2 justify-end">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setShowCreateUser(false)
                        setNewUserName("")
                        setNewUserEmail("")
                        setError(null)
                      }}
                      disabled={creatingUser}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="button"
                      onClick={handleCreateUser}
                      disabled={creatingUser || !newUserName.trim() || !newUserEmail.trim()}
                    >
                      {creatingUser && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                      {creatingUser ? "Creating..." : "Create User"}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <Select
                    value={raisedByUserId}
                    onValueChange={(value) => {
                      if (value === "create-new") {
                        setShowCreateUser(true)
                      } else {
                        setRaisedByUserId(value)
                        const selectedUser = companyUsers.find((u) => u.id === value)
                        if (selectedUser) {
                          setRaisedByUserName(selectedUser.name)
                        }
                      }
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select person from company..." />
                    </SelectTrigger>
                    <SelectContent>
                      {loadingCompanyUsers ? (
                        <SelectItem disabled value="loading">
                          Loading users...
                        </SelectItem>
                      ) : (
                        <>
                          {filteredUsers.length > 0 &&
                            filteredUsers.map((user) => (
                              <SelectItem key={user.id} value={user.id}>
                                {user.name} ({user.email})
                              </SelectItem>
                            ))}
                          {filteredUsers.length === 0 && !userSearch && (
                            <SelectItem disabled value="none">
                              No users in this company
                            </SelectItem>
                          )}
                          {filteredUsers.length === 0 && userSearch && (
                            <SelectItem disabled value="none">
                              No users match your search
                            </SelectItem>
                          )}
                          <SelectItem value="create-new">
                            <Plus className="h-4 w-4 mr-2 inline" />
                            Create New User
                          </SelectItem>
                        </>
                      )}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>

            {/* Subject */}
            <div className="space-y-2">
              <Label htmlFor="subject" className="font-semibold">
                Subject *
              </Label>
              <Input
                id="subject"
                placeholder="Brief description of the issue"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                disabled={loading}
              />
            </div>

            {/* Summary */}
            <div className="space-y-2">
              <Label htmlFor="summary" className="font-semibold">
                Summary
              </Label>
              <Input
                id="summary"
                placeholder="Optional summary"
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                disabled={loading}
              />
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label htmlFor="description" className="font-semibold">
                Detailed Description *
              </Label>
              <Textarea
                id="description"
                placeholder="Provide detailed information about the issue..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={loading}
                rows={4}
              />
            </div>

            {/* Category & Priority */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="category" className="font-semibold">
                  Category
                </Label>
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
                <Label htmlFor="priority" className="font-semibold">
                  Priority Level
                </Label>
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

            {/* Assign Engineer */}
            <div className="space-y-2">
              <Label htmlFor="engineer" className="font-semibold">
                Assign Support Engineer
              </Label>
              <Select value={assignedEngineer} onValueChange={setAssignedEngineer}>
                <SelectTrigger>
                  <SelectValue placeholder="Leave unassigned..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="unassigned">Unassigned</SelectItem>
                  {engineers.map((eng) => (
                    <SelectItem key={eng.id} value={eng.id}>
                      {eng.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Attachments Section */}
            <div className="space-y-2 p-4 border rounded-lg bg-gray-50">
              <Label className="font-semibold flex items-center gap-2">
                <FileUp className="h-4 w-4" />
                Attachments
              </Label>
              <div className="space-y-3">
                {attachments.length > 0 && (
                  <div className="space-y-2">
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
                  disabled={loading}
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
                  disabled={loading}
                />
              </div>
            </div>

            {/* Older Ticket Section */}
            <div className="space-y-2 p-4 border rounded-lg bg-blue-50">
              <Label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={isOlderTicket}
                  onChange={(e) => setIsOlderTicket(e.target.checked)}
                  disabled={loading}
                  className="rounded"
                />
                <span className="font-semibold">This is an older ticket (import from legacy system)</span>
              </Label>

              {isOlderTicket && (
                <div className="space-y-4 mt-4">
                  <div className="space-y-2">
                    <Label htmlFor="created-at" className="flex items-center gap-2">
                      <Calendar className="h-4 w-4" />
                      Ticket Creation Date
                    </Label>
                    <Input
                      id="created-at"
                      type="date"
                      value={createdAt}
                      onChange={(e) => setCreatedAt(e.target.value)}
                      disabled={loading}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="ticket-no">Ticket Number (optional)</Label>
                    <Input
                      id="ticket-no"
                      placeholder="e.g., 917 or TKT-000917"
                      value={ticketNo}
                      onChange={(e) => setTicketNo(e.target.value)}
                      disabled={loading}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="status">Ticket Status</Label>
                    <Select value={status} onValueChange={setStatus}>
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

                  {/* IR Checkbox */}
                  <div className="space-y-2 p-3 bg-blue-100 rounded border border-blue-300 mt-4">
                    <Label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={hasIR}
                        onChange={(e) => setHasIR(e.target.checked)}
                        disabled={loading}
                        className="rounded"
                      />
                      <span className="font-semibold text-sm">
                        This ticket had an Incident Report (IR) raised
                      </span>
                    </Label>
                  </div>

                  {/* IR Section - Only when IR checkbox is checked */}
                  {hasIR && (
                    <div className="space-y-3 p-3 border rounded bg-cyan-50">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm text-cyan-900">Incident Report Details</span>
                        <button
                          type="button"
                          onClick={() => setHasIR(false)}
                          className="text-cyan-600 hover:text-cyan-800"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="ir-number">IR Number *</Label>
                        <Input
                          id="ir-number"
                          placeholder="e.g., IR-2025-001"
                          value={irNumber}
                          onChange={(e) => setIrNumber(e.target.value)}
                          disabled={loading}
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="ir-vendor">Vendor</Label>
                        <Select value={irVendor} onValueChange={setIrVendor}>
                          <SelectTrigger>
                            <SelectValue placeholder="Select vendor..." />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="siemens">Siemens</SelectItem>
                            <SelectItem value="other">Other</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="ir-raised-at">IR Raised Date</Label>
                        <Input
                          id="ir-raised-at"
                          type="date"
                          value={irRaisedAt}
                          onChange={(e) => setIrRaisedAt(e.target.value)}
                          disabled={loading}
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="ir-expected-resolution">Expected Resolution Date</Label>
                        <Input
                          id="ir-expected-resolution"
                          type="date"
                          value={irExpectedResolutionDate}
                          onChange={(e) => setIrExpectedResolutionDate(e.target.value)}
                          disabled={loading}
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="ir-notes">IR Notes</Label>
                        <Textarea
                          id="ir-notes"
                          placeholder="Notes about the incident report..."
                          value={irNotes}
                          onChange={(e) => setIrNotes(e.target.value)}
                          disabled={loading}
                          rows={2}
                        />
                      </div>

                      {/* NEW: IR Closure Date */}
                      <div className="space-y-2">
                        <Label htmlFor="ir-closed-at">IR Closed Date (if already resolved)</Label>
                        <Input
                          id="ir-closed-at"
                          type="date"
                          value={irClosedAt}
                          onChange={(e) => setIrClosedAt(e.target.value)}
                          disabled={loading}
                        />
                        <p className="text-xs text-gray-600">Leave blank if IR is still open</p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* RCA Section - Only for closed older tickets */}
            {shouldShowRCA && (
              <div className="space-y-4 p-4 border rounded-lg bg-amber-50">
                <div className="font-semibold text-amber-900">
                  Root Cause Analysis (Required for Closed Tickets)
                </div>

                <div className="space-y-2">
                  <Label htmlFor="closed-at" className="flex items-center gap-2">
                    <Calendar className="h-4 w-4" />
                    Ticket Closed Date
                  </Label>
                  <Input
                    id="closed-at"
                    type="date"
                    value={closedAt}
                    onChange={(e) => setClosedAt(e.target.value)}
                    disabled={loading}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="rca-description">Root Cause Description *</Label>
                  <Textarea
                    id="rca-description"
                    placeholder="Describe the root cause of the issue..."
                    value={rootCauseDescription}
                    onChange={(e) => setRootCauseDescription(e.target.value)}
                    disabled={loading}
                    rows={3}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="contributing-factors">Contributing Factors</Label>
                  <Textarea
                    id="contributing-factors"
                    placeholder="List factors (one per line)..."
                    value={contributingFactors}
                    onChange={(e) => setContributingFactors(e.target.value)}
                    disabled={loading}
                    rows={2}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="prevention-measures">Prevention Measures</Label>
                  <Textarea
                    id="prevention-measures"
                    placeholder="What steps should be taken to prevent this in the future?..."
                    value={preventionMeasures}
                    onChange={(e) => setPreventionMeasures(e.target.value)}
                    disabled={loading}
                    rows={2}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="resolution-steps">Resolution Steps Taken</Label>
                  <Textarea
                    id="resolution-steps"
                    placeholder="List steps taken to resolve (one per line)..."
                    value={resolutionSteps}
                    onChange={(e) => setResolutionSteps(e.target.value)}
                    disabled={loading}
                    rows={2}
                  />
                </div>

                {/* RCA Attachments */}
                <div className="space-y-2 p-3 bg-white rounded border">
                  <Label className="font-semibold flex items-center gap-2">
                    <FileUp className="h-4 w-4" />
                    RCA Attachments (Screenshots, Guides, etc.)
                  </Label>
                  <div className="space-y-3">
                    {rcaAttachments.length > 0 && (
                      <div className="space-y-2">
                        {rcaAttachments.map((att) => (
                          <div
                            key={att.id}
                            className="flex items-center justify-between p-2 bg-gray-50 rounded border"
                          >
                            <span className="text-sm text-gray-600">{att.name}</span>
                            <button
                              type="button"
                              onClick={() =>
                                setRcaAttachments((prev) =>
                                  prev.filter((a) => a.id !== att.id)
                                )
                              }
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
                      size="sm"
                      onClick={() => rcaFileInputRef.current?.click()}
                      disabled={loading}
                      className="gap-2"
                    >
                      <Plus className="h-4 w-4" />
                      Add RCA File
                    </Button>
                    <input
                      ref={rcaFileInputRef}
                      type="file"
                      multiple
                      onChange={(e) => {
                        const files = e.currentTarget.files
                        if (!files) return

                        for (let i = 0; i < files.length; i++) {
                          const file = files[i]
                          const id = Math.random().toString(36).substring(2, 11)
                          setRcaAttachments((prev) => [
                            ...prev,
                            { id, name: file.name, file },
                          ])
                        }

                        if (rcaFileInputRef.current) {
                          rcaFileInputRef.current.value = ""
                        }
                      }}
                      className="hidden"
                      disabled={loading}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Submit Button */}
            <div className="flex gap-2 justify-end">
              <Button type="button" variant="outline" onClick={handleCloseDialog} disabled={loading}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {loading ? "Creating..." : "Create Ticket"}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}