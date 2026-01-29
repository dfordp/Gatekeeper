'use client';

import React from 'react';
import clsx from 'clsx';

interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  maxLength?: number;
  showCount?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, maxLength, showCount, ...props }, ref) => {
    const currentLength = (props.value as string)?.length || 0;

    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          maxLength={maxLength}
          className={clsx(
            'w-full px-3 py-2 border rounded-lg',
            'focus:outline-none focus:ring-2 focus:ring-blue-500',
            'transition-colors duration-200 resize-vertical',
            {
              'border-gray-300': !error,
              'border-red-500': error,
            }
          )}
          {...props}
        />
        <div className="flex justify-between mt-1">
          {error && <p className="text-red-500 text-sm">{error}</p>}
          {showCount && maxLength && (
            <p className="text-xs text-gray-500 ml-auto">
              {currentLength} / {maxLength}
            </p>
          )}
        </div>
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';