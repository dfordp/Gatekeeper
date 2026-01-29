'use client';

import React from 'react';
import { TicketList } from '@/components/tickets/TicketList';

export default function TicketsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-800">Tickets</h1>
        <p className="text-gray-600 mt-2">Manage and track all support tickets</p>
      </div>

      <TicketList />
    </div>
  );
}