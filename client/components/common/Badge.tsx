'use client';

import React from 'react';
import clsx from 'clsx';

interface BadgeProps {
  variant: 'status' | 'level' | 'category';
  value: string;
  size?: 'sm' | 'md';
}

const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-800',
  open: 'bg-blue-100 text-blue-800',
  resolved: 'bg-green-100 text-green-800',
  closed: 'bg-gray-100 text-gray-800',
};

const levelColors: Record<string, string> = {
  P0: 'bg-red-100 text-red-800',
  P1: 'bg-orange-100 text-orange-800',
  P2: 'bg-yellow-100 text-yellow-800',
  P3: 'bg-green-100 text-green-800',
};

const categoryColors: Record<string, string> = {
  bug: 'bg-red-100 text-red-800',
  feature_request: 'bg-purple-100 text-purple-800',
  documentation: 'bg-blue-100 text-blue-800',
  support: 'bg-green-100 text-green-800',
  other: 'bg-gray-100 text-gray-800',
};

export const Badge: React.FC<BadgeProps> = ({
  variant,
  value,
  size = 'md',
}) => {
  let colorMap = statusColors;
  if (variant === 'level') colorMap = levelColors;
  if (variant === 'category') colorMap = categoryColors;

  const color = colorMap[value] || 'bg-gray-100 text-gray-800';

  return (
    <span
      className={clsx(
        'px-3 rounded-full font-medium',
        {
          'py-1 text-xs': size === 'sm',
          'py-1.5 text-sm': size === 'md',
        },
        color
      )}
    >
      {value.replace('_', ' ')}
    </span>
  );
};