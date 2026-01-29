'use client';

import Link from 'next/link';
import { useAuth } from '@/lib/hooks/useAuth';
import { Button } from '@/components/common/Button';

export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-800">
          Welcome back, {user?.name}!
        </h1>
        <p className="text-gray-600 mt-2">
          Here&apos;s what&apos;s happening with your support tickets today.
        </p>
      </div>

      {/* Quick Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-6 border-l-4 border-blue-500">
          <div className="text-gray-500 text-sm font-medium">Open Tickets</div>
          <div className="text-3xl font-bold text-gray-800 mt-2">12</div>
          <div className="text-gray-400 text-xs mt-2">3 assigned to you</div>
        </div>

        <div className="bg-white rounded-lg shadow p-6 border-l-4 border-yellow-500">
          <div className="text-gray-500 text-sm font-medium">Pending RCA</div>
          <div className="text-3xl font-bold text-gray-800 mt-2">5</div>
          <div className="text-gray-400 text-xs mt-2">Awaiting approval</div>
        </div>

        <div className="bg-white rounded-lg shadow p-6 border-l-4 border-green-500">
          <div className="text-gray-500 text-sm font-medium">Resolved</div>
          <div className="text-3xl font-bold text-gray-800 mt-2">28</div>
          <div className="text-gray-400 text-xs mt-2">This month</div>
        </div>

        <div className="bg-white rounded-lg shadow p-6 border-l-4 border-purple-500">
          <div className="text-gray-500 text-sm font-medium">Avg Resolution</div>
          <div className="text-3xl font-bold text-gray-800 mt-2">4.2h</div>
          <div className="text-gray-400 text-xs mt-2">↓ 12% vs last week</div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Quick Actions
        </h2>
        <div className="flex flex-wrap gap-3">
          <Link href="/dashboard/tickets?status=draft">
            <Button variant="primary">Create New Ticket</Button>
          </Link>
          <Link href="/dashboard/tickets">
            <Button variant="secondary">View All Tickets</Button>
          </Link>
          {(user?.role === 'company_admin' ||
            user?.role === 'platform_admin') && (
            <Link href="/dashboard/admin/duplicates">
              <Button variant="secondary">View Analytics</Button>
            </Link>
          )}
        </div>
      </div>

      {/* Recent Tickets Table (Placeholder) */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Recent Tickets
        </h2>
        <div className="text-center py-8 text-gray-500">
          <p>Loading recent tickets...</p>
        </div>
      </div>
    </div>
  );
}