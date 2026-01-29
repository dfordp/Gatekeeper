'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/hooks/useAuth';
import { useTickets } from '@/lib/hooks/useTickets';
import { useDebounce } from '@/lib/hooks/useDebounce';
import { usePagination } from '@/lib/hooks/usePagination';
import { Badge } from '@/components/common/Badge';
import { Input } from '@/components/common/Input';
import { Select } from '@/components/common/Select';
import { Button } from '@/components/common/Button';
import { Pagination } from '@/components/common/Pagination';
import { Loading } from '@/components/common/Loading';
import { EmptyState } from '@/components/common/EmptyState';
import { helpers } from '@/lib/utils/helpers';

export const TicketList: React.FC = () => {
  const { user } = useAuth();
  const { currentPage, pageSize, goToPage } =
    usePagination();

  const [filters, setFilters] = useState({
    status: '',
    level: '',
    category: '',
    search: '',
  });

  const debouncedSearch = useDebounce(filters.search, 500);

  const { data, isLoading, error } = useTickets({
    companyId: user?.company_id || '',
    page: currentPage,
    limit: pageSize,
    status: filters.status || undefined,
    level: filters.level || undefined,
    category: filters.category || undefined,
    search: debouncedSearch || undefined,
  });

  const handleFilterChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setFilters((prev) => ({ ...prev, [name]: value }));
    goToPage(1); // Reset to first page when filtering
  };

  if (isLoading) return <Loading />;

  if (error) {
    return (
      <EmptyState
        title="Error loading tickets"
        description="Failed to load tickets. Please try again."
      />
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <EmptyState
        title="No tickets found"
        description="Create your first ticket to get started."
        action={{
          label: 'Create Ticket',
          onClick: () => (window.location.href = '/dashboard/tickets/new'),
        }}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <Input
            type="search"
            placeholder="Search tickets..."
            name="search"
            value={filters.search}
            onChange={handleFilterChange}
          />

          <Select
            name="status"
            value={filters.status}
            onChange={handleFilterChange}
            options={[
              { value: '', label: 'All Statuses' },
              { value: 'draft', label: 'Draft' },
              { value: 'open', label: 'Open' },
              { value: 'resolved', label: 'Resolved' },
              { value: 'closed', label: 'Closed' },
            ]}
          />

          <Select
            name="level"
            value={filters.level}
            onChange={handleFilterChange}
            options={[
              { value: '', label: 'All Levels' },
              { value: 'P0', label: 'P0 - Critical' },
              { value: 'P1', label: 'P1 - High' },
              { value: 'P2', label: 'P2 - Medium' },
              { value: 'P3', label: 'P3 - Low' },
            ]}
          />

          <Select
            name="category"
            value={filters.category}
            onChange={handleFilterChange}
            options={[
              { value: '', label: 'All Categories' },
              { value: 'bug', label: 'Bug' },
              { value: 'feature_request', label: 'Feature Request' },
              { value: 'documentation', label: 'Documentation' },
              { value: 'support', label: 'Support' },
              { value: 'other', label: 'Other' },
            ]}
          />

          <Link href="/dashboard/tickets/new">
            <Button variant="primary" className="w-full">
              New Ticket
            </Button>
          </Link>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                #
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                Title
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                Status
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                Level
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                Category
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                Created
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                Action
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {data.items.map((ticket) => (
              <tr
                key={ticket.id}
                className="hover:bg-gray-50 transition-colors"
              >
                <td className="px-6 py-4 text-sm font-medium text-blue-600">
                  {ticket.ticket_number}
                </td>
                <td className="px-6 py-4 text-sm text-gray-800">
                  {helpers.truncate(ticket.title, 50)}
                </td>
                <td className="px-6 py-4">
                  <Badge variant="status" value={ticket.status} size="sm" />
                </td>
                <td className="px-6 py-4">
                  <Badge variant="level" value={ticket.level} size="sm" />
                </td>
                <td className="px-6 py-4">
                  <Badge variant="category" value={ticket.category} size="sm" />
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {helpers.formatDate(ticket.created_at)}
                </td>
                <td className="px-6 py-4">
                  <Link href={`/dashboard/tickets/${ticket.id}`}>
                    <Button variant="secondary" size="sm">
                      View
                    </Button>
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <Pagination
        currentPage={data.page}
        totalPages={data.pages}
        onPageChange={goToPage}
      />
    </div>
  );
};