// client/components/dashboard/admins/AddAdminDialog.tsx
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
import { Loader2, Copy, Check } from "lucide-react"
import { adminService } from "@/services/admin.service"

interface AddAdminDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onAdminCreated: () => void
}

export default function AddAdminDialog({ open, onOpenChange, onAdminCreated }: AddAdminDialogProps) {
  const [formData, setFormData] = useState({
    email: "",
    full_name: "",
    role: "manager",
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tempPassword, setTempPassword] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (open) {
      setFormData({ email: "", full_name: "", role: "manager" })
      setError(null)
      setTempPassword(null)
      setCopied(false)
    }
  }, [open])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.email.trim() || !formData.email.includes("@")) {
      setError("Valid email is required")
      return
    }

    if (!formData.full_name.trim()) {
      setError("Full name is required")
      return
    }

    try {
      setLoading(true)
      setError(null)

      const result = await adminService.createAdmin({
        email: formData.email.trim(),
        full_name: formData.full_name.trim(),
        role: formData.role,
      })

      setTempPassword(result.temporary_password || "")
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create admin"
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleCopyPassword = () => {
    if (tempPassword) {
      navigator.clipboard.writeText(tempPassword)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleClose = () => {
    if (tempPassword) {
      onAdminCreated()
      onOpenChange(false)
    } else {
      onOpenChange(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Create Admin</DialogTitle>
          <DialogDescription>
            Create a new system administrator account
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {tempPassword ? (
          <div className="space-y-4">
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <p className="text-sm font-medium text-green-800 mb-2">✓ Admin Created Successfully</p>
              <p className="text-xs text-green-700 mb-3">Share this temporary password with the new admin. They must change it on first login.</p>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700">Email</label>
              <p className="text-sm text-gray-600 mt-1">{formData.email}</p>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700">Temporary Password</label>
              <div className="flex gap-2 mt-1">
                <input
                  type="text"
                  value={tempPassword}
                  readOnly
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm font-mono bg-gray-50"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleCopyPassword}
                  className="flex items-center gap-2"
                >
                  {copied ? (
                    <>
                      <Check className="h-4 w-4" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="h-4 w-4" />
                      Copy
                    </>
                  )}
                </Button>
              </div>
            </div>

            <div className="flex gap-3 justify-end pt-4">
              <Button onClick={() => onOpenChange(false)}>Done</Button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-gray-700">Email *</label>
              <Input
                name="email"
                type="email"
                value={formData.email}
                onChange={handleChange}
                placeholder="admin@example.com"
                disabled={loading}
                required
              />
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700">Full Name *</label>
              <Input
                name="full_name"
                value={formData.full_name}
                onChange={handleChange}
                placeholder="John Doe"
                disabled={loading}
                required
              />
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700">Role *</label>
              <Select value={formData.role} onValueChange={(value) => setFormData(prev => ({ ...prev, role: value }))}>
                <SelectTrigger disabled={loading}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin (Full System Access)</SelectItem>
                  <SelectItem value="manager">Manager (Limited Admin Access)</SelectItem>
                </SelectContent>
              </Select>
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
              <Button type="submit" disabled={loading} className="flex items-center gap-2">
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                Create Admin
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}