// client/components/dashboard/users/AddUserDialog.tsx
"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Loader2 } from "lucide-react"
import { userService } from "@/services/user.service"
import { useAuth } from "@/hooks/useAuth"

interface AddUserDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onUserCreated: () => void
}

export default function AddUserDialog({ open, onOpenChange, onUserCreated }: AddUserDialogProps) {
  const { admin } = useAuth()
  
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    role: "support_engineer",
    phone_number: "",
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setFormData({
        name: "",
        email: "",
        role: "support_engineer",
        phone_number: "",
      })
      setError(null)
    }
  }, [open])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value,
    }))
  }

  const handleRoleChange = (value: string) => {
    setFormData(prev => ({
      ...prev,
      role: value,
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.name.trim()) {
      setError("Name is required")
      return
    }

    if (!formData.email.trim() || !formData.email.includes("@")) {
      setError("Valid email is required")
      return
    }

    if (!admin?.company_id) {
      setError("Company information not found. Please log in again.")
      return
    }

    try {
      setLoading(true)
      setError(null)

      await userService.createUser({
        name: formData.name.trim(),
        email: formData.email.trim(),
        company_id: admin.company_id,
        role: formData.role,
        phone_number: formData.phone_number?.trim() || undefined,
      })

      setFormData({
        name: "",
        email: "",
        role: "support_engineer",
        phone_number: "",
      })

      onUserCreated()
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create user"
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Add Team Member</DialogTitle>
          <DialogDescription>
            Create a new support team member for Future Tech Design
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700">Name *</label>
            <Input
              name="name"
              value={formData.name}
              onChange={handleChange}
              placeholder="John Doe"
              disabled={loading}
              autoFocus
              required
            />
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700">Email *</label>
            <Input
              name="email"
              type="email"
              value={formData.email}
              onChange={handleChange}
              placeholder="john@company.com"
              disabled={loading}
              required
            />
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700">Role *</label>
            <Select value={formData.role} onValueChange={handleRoleChange} disabled={loading}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="support_engineer">Support Engineer</SelectItem>
                <SelectItem value="supervisor">Supervisor</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700">Phone (Optional)</label>
            <Input
              name="phone_number"
              value={formData.phone_number}
              onChange={handleChange}
              placeholder="+1 (555) 123-4567"
              disabled={loading}
            />
          </div>

          <div className="flex gap-3 justify-end pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={loading || !admin?.company_id} className="flex items-center gap-2">
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              Add Team Member
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}