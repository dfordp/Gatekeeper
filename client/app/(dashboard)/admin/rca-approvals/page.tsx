'use client';

import React from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/hooks/useAuth';
import {
  useDuplicateTickets,
  useTicketCategories,
  useEmbeddingMetrics,
  useApprovalMetrics,
} from '@/lib/hooks/useAnalytics';
import { Button } from '@/components/common/Button';

export default function AdminPage() {
  const { user } = useAuth();
  const { data: duplicates } = useDuplicateTickets(user?.company_id || '');
  const { data: categories } = useTicketCategories(user?.company_id || '');
  const { data: embeddings } = useEmbeddingMetrics(user?.company_id || '');
  const { data: approvals } = useApprovalMetrics(user?.company_id || '');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-800">Admin Dashboard</h1>
        <p className="text-gray-600 mt-2">
          View analytics and manage your support system
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-500 text-sm font-medium">Duplicate Groups</p>
          <p className="text-3xl font-bold text-gray-800 mt-2">
            {duplicates?.groups.length || 0}
          </p>
          <p className="text-gray-400 text-xs mt-2">Similar ticket clusters</p>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-500 text-sm font-medium">Categories</p>
          <p className="text-3xl font-bold text-gray-800 mt-2">
            {categories ? Object.keys(categories.categories).length : 0}
          </p>
          <p className="text-gray-400 text-xs mt-2">Active categories</p>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-500 text-sm font-medium">Embeddings</p>
          <p className="text-3xl font-bold text-gray-800 mt-2">
            {embeddings?.active_count || 0}
          </p>
          <p className="text-gray-400 text-xs mt-2">Active vectors</p>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-500 text-sm font-medium">Avg Turnaround</p>
          <p className="text-3xl font-bold text-gray-800 mt-2">
            {approvals?.avg_turnaround_hours.toFixed(1)}h
          </p>
          <p className="text-gray-400 text-xs mt-2">RCA approval time</p>
        </div>
      </div>

      {/* Quick Links */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            Quick Actions
          </h3>
          <div className="space-y-2">
            <Link href="/dashboard/admin/duplicates">
              <Button variant="secondary" className="w-full justify-start">
                View Duplicate Tickets
              </Button>
            </Link>
            <Link href="/dashboard/admin/categories">
              <Button variant="secondary" className="w-full justify-start">
                Category Distribution
              </Button>
            </Link>
            <Link href="/dashboard/admin/rca-approvals">
              <Button variant="primary" className="w-full justify-start">
                Review Pending RCAs
              </Button>
            </Link>
            <Link href="/dashboard/admin/embeddings">
              <Button variant="secondary" className="w-full justify-start">
                Embedding Metrics
              </Button>
            </Link>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            Approval Metrics
          </h3>
          <div className="space-y-3">
            <div>
              <p className="text-sm text-gray-600">Total Approved</p>
              <p className="text-2xl font-bold text-green-600">
                {approvals?.total_approved || 0}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Total Rejected</p>
              <p className="text-2xl font-bold text-red-600">
                {approvals?.total_rejected || 0}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Approval Rate</p>
              <p className="text-2xl font-bold text-blue-600">
                {(approvals?.approval_rate || 0).toFixed(1)}%
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}