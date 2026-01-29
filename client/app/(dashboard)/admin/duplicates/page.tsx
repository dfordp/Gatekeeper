'use client';

import Link from 'next/link';
import { useAuth } from '@/lib/hooks/useAuth';
import { useDuplicateTickets } from '@/lib/hooks/useAnalytics';
import { Loading } from '@/components/common/Loading';
import { EmptyState } from '@/components/common/EmptyState';

export default function DuplicatesPage() {
  const { user } = useAuth();
  const { data: duplicates, isLoading, error } = useDuplicateTickets(
    user?.company_id || ''
  );

  if (isLoading) return <Loading />;

  if (error) {
    return (
      <EmptyState
        title="Error loading duplicates"
        description="Failed to load duplicate ticket analysis"
      />
    );
  }

  if (!duplicates || duplicates.groups.length === 0) {
    return (
      <EmptyState
        title="No duplicates found"
        description="No similar tickets detected at this time"
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-800">Duplicate Tickets</h1>
        <p className="text-gray-600 mt-2">
          {duplicates.groups.length} groups of similar tickets detected
        </p>
      </div>

      <div className="space-y-4">
        {duplicates.groups.map((group, index) => (
          <div
            key={index}
            className="bg-white rounded-lg shadow p-6 border-l-4 border-orange-500"
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-800">
                  Similarity Group {index + 1}
                </h3>
                <p className="text-sm text-gray-600 mt-1">
                  {group.ticket_ids.length} similar tickets
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm text-gray-600">Similarity Score</p>
                <p className="text-2xl font-bold text-orange-600">
                  {(group.similarity_score * 100).toFixed(0)}%
                </p>
              </div>
            </div>

            <div className="space-y-2">
              {group.ticket_ids.map((ticketId) => (
                <Link
                  key={ticketId}
                  href={`/dashboard/tickets/${ticketId}`}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <span className="text-sm font-medium text-gray-800">
                    Ticket {ticketId.slice(0, 8)}
                  </span>
                  <svg
                    className="w-5 h-5 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}