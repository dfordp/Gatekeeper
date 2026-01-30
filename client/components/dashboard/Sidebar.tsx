// client/components/dashboard/Sidebar.tsx
"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import { BarChart3, Ticket, Settings, Home, Users, Shield, Building2 } from "lucide-react"
import { cn } from "@/lib/utils"

export default function Sidebar() {
  const pathname = usePathname()
  const { admin } = useAuth()

  const items = [
    { name: "Dashboard", href: "/dashboard", icon: Home },
    { name: "Tickets", href: "/dashboard/tickets", icon: Ticket },
    { name: "Users", href: "/dashboard/users", icon: Users },
    ...(admin?.role === "admin" ? [{ name: "Admins", href: "/dashboard/admins", icon: Shield }] : []),
    { name: "Analytics", href: "/dashboard/analytics", icon: BarChart3 },
    { name: "Settings", href: "/dashboard/settings", icon: Settings },
    ...(admin?.role === "admin" || admin?.role === "manager" ? [{
      name: "Companies",
      href: "/dashboard/companies",
      label: "Companies",
      icon: Building2
    }] : []),
  ]

  return (
    <aside className="w-64 bg-gray-900 text-white">
      <div className="p-6">
        <h1 className="text-2xl font-bold">Gatekeeper</h1>
      </div>
      <nav className="space-y-2 px-4">
        {items.map((item) => {
          const Icon = item.icon
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-4 py-3 rounded-lg transition-colors",
                pathname === item.href
                  ? "bg-blue-600 text-white"
                  : "text-gray-300 hover:bg-gray-800"
              )}
            >
              <Icon className="h-5 w-5" />
              <span>{item.name}</span>
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}