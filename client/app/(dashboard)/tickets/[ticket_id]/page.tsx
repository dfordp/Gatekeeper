'use client';

import React from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { TicketDetail } from '@/components/tickets/TicketDetail';

export default function TicketDetailPage({
  params,
}: {
  params: { ticket_id: string };
}) {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-800">Ticket Details</h1>
        <p className="text-gray-600 mt-2">View and manage ticket information</p>
      </div>

      <TicketDetail
        companyId={user?.company_id || ''}
        ticketId={params.ticket_id}
      />
    </div>
  );
}