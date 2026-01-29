export const dateUtils = {
  isToday: (date: Date | string): boolean => {
    const d = typeof date === 'string' ? new Date(date) : date;
    const today = new Date();
    return d.toDateString() === today.toDateString();
  },

  isYesterday: (date: Date | string): boolean => {
    const d = typeof date === 'string' ? new Date(date) : date;
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    return d.toDateString() === yesterday.toDateString();
  },

  daysAgo: (date: Date | string): number => {
    const d = typeof date === 'string' ? new Date(date) : date;
    const today = new Date();
    const diff = today.getTime() - d.getTime();
    return Math.floor(diff / (1000 * 60 * 60 * 24));
  },

  formatRelative: (date: Date | string): string => {
    const d = typeof date === 'string' ? new Date(date) : date;

    if (dateUtils.isToday(d)) return 'Today';
    if (dateUtils.isYesterday(d)) return 'Yesterday';

    const days = dateUtils.daysAgo(d);
    if (days < 7) return `${days}d ago`;
    if (days < 30) return `${Math.floor(days / 7)}w ago`;
    if (days < 365) return `${Math.floor(days / 30)}mo ago`;

    return `${Math.floor(days / 365)}y ago`;
  },
};