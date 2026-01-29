'use client';

import React from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { useEmbeddingMetrics } from '@/lib/hooks/useAnalytics';
import { Button } from '@/components/common/Button';
import { Loading } from '@/components/common/Loading';
import { EmptyState } from '@/components/common/EmptyState';

export default function EmbeddingsPage() {
  const { user } = useAuth();
  const { data: embeddings, isLoading, error } = useEmbeddingMetrics(
    user?.company_id || ''
  );

  if (isLoading) return <Loading />;

  if (error) {
    return (
      <EmptyState
        title="Error loading embeddings"
        description="Failed to load embedding metrics"
      />
    );
  }

  const totalEmbeddings =
    (embeddings?.active_count || 0) + (embeddings?.deprecated_count || 0);

  const activePercentage =
    totalEmbeddings > 0
      ? ((embeddings?.active_count || 0) / totalEmbeddings) * 100
      : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-800">Embedding Metrics</h1>
        <p className="text-gray-600 mt-2">
          Vector storage and semantic search performance
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-6 border-l-4 border-green-500">
          <p className="text-gray-500 text-sm font-medium">Active Embeddings</p>
          <p className="text-3xl font-bold text-gray-800 mt-2">
            {embeddings?.active_count || 0}
          </p>
          <p className="text-gray-400 text-xs mt-2">
            {activePercentage.toFixed(1)}% of total
          </p>
        </div>

        <div className="bg-white rounded-lg shadow p-6 border-l-4 border-gray-400">
          <p className="text-gray-500 text-sm font-medium">Deprecated</p>
          <p className="text-3xl font-bold text-gray-800 mt-2">
            {embeddings?.deprecated_count || 0}
          </p>
          <p className="text-gray-400 text-xs mt-2">
            {(100 - activePercentage).toFixed(1)}% of total
          </p>
        </div>

        <div className="bg-white rounded-lg shadow p-6 border-l-4 border-blue-500">
          <p className="text-gray-500 text-sm font-medium">Total</p>
          <p className="text-3xl font-bold text-gray-800 mt-2">
            {totalEmbeddings}
          </p>
          <p className="text-gray-400 text-xs mt-2">All vectors</p>
        </div>
      </div>

      {/* Progress */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Vector Index Health
        </h2>
        <div className="space-y-4">
          <div>
            <div className="flex justify-between mb-2">
              <p className="text-sm font-medium text-gray-700">Active</p>
              <p className="text-sm text-gray-600">
                {embeddings?.active_count || 0}
              </p>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div
                className="bg-green-600 h-3 rounded-full transition-all"
                style={{ width: `${activePercentage}%` }}
              />
            </div>
          </div>

          <div>
            <div className="flex justify-between mb-2">
              <p className="text-sm font-medium text-gray-700">Deprecated</p>
              <p className="text-sm text-gray-600">
                {embeddings?.deprecated_count || 0}
              </p>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div
                className="bg-gray-400 h-3 rounded-full transition-all"
                style={{ width: `${100 - activePercentage}%` }}
              />
            </div>
          </div>
        </div>

        <Button variant="secondary" className="mt-6 w-full">
          Regenerate Embeddings
        </Button>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <p className="text-sm text-blue-800">
          <strong>ℹ️ About Embeddings:</strong> Embeddings are vector
          representations of RCAs used for semantic search and duplicate
          detection. Deprecated embeddings are kept for historical reference.
        </p>
      </div>
    </div>
  );
}