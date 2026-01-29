'use client';

import React from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { useTicketCategories } from '@/lib/hooks/useAnalytics';
import { Loading } from '@/components/common/Loading';
import { EmptyState } from '@/components/common/EmptyState';

export default function CategoriesPage() {
  const { user } = useAuth();
  const { data: categories, isLoading, error } = useTicketCategories(
    user?.company_id || ''
  );

  if (isLoading) return <Loading />;

  if (error) {
    return (
      <EmptyState
        title="Error loading categories"
        description="Failed to load category distribution"
      />
    );
  }

  if (!categories || Object.keys(categories.categories).length === 0) {
    return (
      <EmptyState
        title="No category data"
        description="No tickets with categories exist yet"
      />
    );
  }

  const totalTickets = Object.values(categories.categories).reduce(
    (sum, count) => sum + count,
    0
  );

  const categoryList = Object.entries(categories.categories).sort(
    ([, a], [, b]) => (b as number) - (a as number)
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-800">
          Category Distribution
        </h1>
        <p className="text-gray-600 mt-2">
          {totalTickets} total tickets across {categoryList.length} categories
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Chart */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-6">
            Distribution
          </h2>
          <div className="space-y-4">
            {categoryList.map(([category, count]) => {
              const percentage = ((count as number) / totalTickets) * 100;
              return (
                <div key={category}>
                  <div className="flex justify-between mb-2">
                    <p className="text-sm font-medium text-gray-700 capitalize">
                      {category.replace('_', ' ')}
                    </p>
                    <p className="text-sm text-gray-600">
                      {count as number} ({percentage.toFixed(1)}%)
                    </p>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full transition-all"
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Stats */}
        <div className="space-y-4">
          {categoryList.map(([category, count]) => (
            <div
              key={category}
              className="bg-white rounded-lg shadow p-6 border-l-4 border-blue-500"
            >
              <p className="text-sm text-gray-600 capitalize">
                {category.replace('_', ' ')}
              </p>
              <p className="text-3xl font-bold text-gray-800 mt-2">
                {count as number}
              </p>
              <p className="text-xs text-gray-500 mt-2">
                {(
                  ((count as number) / totalTickets) *
                  100
                ).toFixed(1)}% of total
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}