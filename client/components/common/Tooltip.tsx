'use client';

import React, { useState } from 'react';
import clsx from 'clsx';

interface TooltipProps {
  content: string;
  children: React.ReactNode;
  position?: 'top' | 'right' | 'bottom' | 'left';
}

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  position = 'top',
}) => {
  const [isVisible, setIsVisible] = useState(false);

  const positionStyles = {
    top: '-top-12 left-1/2 -translate-x-1/2',
    right: 'top-1/2 -translate-y-1/2 left-full ml-2',
    bottom: 'top-full mt-2 left-1/2 -translate-x-1/2',
    left: 'top-1/2 -translate-y-1/2 right-full mr-2',
  };

  return (
    <div className="relative inline-block">
      <div
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
      >
        {children}
      </div>

      {isVisible && (
        <div
          className={clsx(
            'absolute z-50 px-2 py-1 text-xs font-medium text-white bg-gray-900 rounded whitespace-nowrap',
            positionStyles[position]
          )}
        >
          {content}
        </div>
      )}
    </div>
  );
};