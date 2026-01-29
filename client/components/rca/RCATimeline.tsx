'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { rcaEventSchema } from '@/lib/schemas/rca';
import { z } from 'zod';
import { Loading } from '@/components/common/Loading';
import { helpers } from '@/lib/utils/helpers';

interface RCATimelineProps {
  companyId: string;
  rcaId: string;
}

export const RCATimeline: React.FC<RCATimelineProps> = ({
  companyId,
  rcaId,
}) => {
  const { data: events, isLoading, error } = useQuery({
    queryKey: ['rcaEvents', companyId, rcaId],
    queryFn: async () => {
      const response = await apiClient.get(
        API_ENDPOINTS.RCA.EVENTS(companyId, rcaId)
      );

      const schema = z.object({
        success: z.boolean(),
        data: z.object({
          items: z.array(rcaEventSchema),
        }),
      });

      return schema.parse(response.data).data.items;
    },
    staleTime: 1000 * 60 * 5,
  });

  if (isLoading) return <Loading />;

  if (error) {
    return (
      <div className="text-center py-8">
        <p className="text-red-600">Failed to load RCA timeline</p>
      </div>
    );
  }

  if (!events || events.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        <p>No events yet</p>
      </div>
    );
  }

  const getEventIcon = (eventType: string) => {
    switch (eventType) {
      case 'created':
        return '📋';
      case 'submitted':
        return '📤';
      case 'approved':
        return '✅';
      case 'rejected':
        return '❌';
      case 'deprecated':
        return '🗑️';
      default:
        return '📝';
    }
  };

  const getEventColor = (eventType: string) => {
    switch (eventType) {
      case 'created':
        return 'bg-blue-50 border-l-blue-500';
      case 'submitted':
        return 'bg-yellow-50 border-l-yellow-500';
      case 'approved':
        return 'bg-green-50 border-l-green-500';
      case 'rejected':
        return 'bg-red-50 border-l-red-500';
      case 'deprecated':
        return 'bg-gray-50 border-l-gray-500';
      default:
        return 'bg-gray-50 border-l-gray-500';
    }
  };

  return (
    <div className="space-y-4">
      {events.map((event) => (
        <div
          key={event.id}
          className={`border-l-4 p-4 rounded-lg ${getEventColor(
            event.event_type
          )}`}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-3">
              <span className="text-2xl">{getEventIcon(event.event_type)}</span>
              <div>
                <h4 className="font-semibold text-gray-800 capitalize">
                  {event.event_type.replace('_', ' ')}
                </h4>
                <p className="text-sm text-gray-600 mt-1">
                  by <strong>{event.actor_name}</strong>
                </p>
              </div>
            </div>
            <p className="text-xs text-gray-500">
              {helpers.formatDateTime(event.created_at)}
            </p>
          </div>

          {event.metadata && Object.keys(event.metadata).length > 0 && (
            <div className="mt-3 text-sm text-gray-700">
              {event.metadata.feedback && (
                <p>
                  <strong>Feedback:</strong> {event.metadata.feedback}
                </p>
              )}
              {event.metadata.reason && (
                <p>
                  <strong>Reason:</strong> {event.metadata.reason}
                </p>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};