'use client';

import React from 'react';
import clsx from 'clsx';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hoverable?: boolean;
  borderColor?: 'blue' | 'green' | 'red' | 'yellow' | 'gray';
}

export const Card: React.FC<CardProps> = ({
  children,
  className,
  hoverable = false,
  borderColor,
}) => {
  const borderColorMap = {
    blue: 'border-l-blue-500',
    green: 'border-l-green-500',
    red: 'border-l-red-500',
    yellow: 'border-l-yellow-500',
    gray: 'border-l-gray-500',
  };

  return (
    <div
      className={clsx(
        'bg-white rounded-lg shadow p-6',
        borderColor && `border-l-4 ${borderColorMap[borderColor]}`,
        hoverable && 'hover:shadow-lg transition-shadow cursor-pointer',
        className
      )}
    >
      {children}
    </div>
  );
};