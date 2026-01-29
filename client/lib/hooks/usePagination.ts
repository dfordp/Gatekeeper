'use client';

import { useState } from 'react';

export const usePagination = (initialPage: number = 1, pageSize: number = 20) => {
  const [currentPage, setCurrentPage] = useState(initialPage);

  return {
    currentPage,
    pageSize,
    setCurrentPage,
    goToNextPage: () => setCurrentPage((prev) => prev + 1),
    goToPreviousPage: () => setCurrentPage((prev) => Math.max(prev - 1, 1)),
    goToPage: (page: number) => setCurrentPage(Math.max(page, 1)),
  };
};