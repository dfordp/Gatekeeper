// client/src/lib/constants.ts
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export const ROUTES = {
  HOME: "/",
  LOGIN: "/login",
  REGISTER: "/register",
  DASHBOARD: "/dashboard",
  TICKETS: "/dashboard/tickets",
  IMPORT: "/dashboard/import",
  ANALYTICS: "/dashboard/analytics",
  RCA: "/dashboard/rca",
}