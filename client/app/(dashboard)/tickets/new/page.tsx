'use client';

import React from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { TicketForm } from '@/components/tickets/TicketForm';

export default function CreateTicketPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-800">Create Ticket</h1>
        <p className="text-gray-600 mt-2">Create a new support request</p>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <TicketForm companyId={user?.company_id || ''} />
      </div>
    </div>
  );
}