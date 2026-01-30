// client/components/dashboard/Navigation.tsx
"use client"

import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { LogOut, User } from "lucide-react"

export default function Navigation() {
  const router = useRouter()
  const { admin, logout } = useAuth()

  const handleLogout = async () => {
    logout()
    router.push("/login")
  }

  return (
    <nav className="bg-white border-b border-gray-200 px-8 py-4 flex justify-between items-center">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Gatekeeper</h2>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <User className="h-4 w-4 text-gray-600" />
          <span className="text-sm text-gray-700">{admin?.email}</span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleLogout}
          className="flex items-center gap-2"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </Button>
      </div>
    </nav>
  )
}