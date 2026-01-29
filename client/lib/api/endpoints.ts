export const API_ENDPOINTS = {
  AUTH: {
    LOGIN: '/api/auth/login',
    REFRESH: '/api/auth/refresh',
    ME: '/api/auth/me',
  },
  TICKETS: {
    LIST: (companyId: string) => `/${companyId}/tickets`,
    CREATE: (companyId: string) => `/${companyId}/tickets`,
    DETAIL: (companyId: string, ticketId: string) =>
      `/${companyId}/tickets/${ticketId}`,
    UPDATE_STATUS: (companyId: string, ticketId: string) =>
      `/${companyId}/tickets/${ticketId}/status`,
    ASSIGN: (companyId: string, ticketId: string) =>
      `/${companyId}/tickets/${ticketId}/assign`,
    CHANGE_LEVEL: (companyId: string, ticketId: string) =>
      `/${companyId}/tickets/${ticketId}/level`,
    ADD_COMMENT: (companyId: string, ticketId: string) =>
      `/${companyId}/tickets/${ticketId}/comment`,
    EVENTS: (companyId: string, ticketId: string) =>
      `/${companyId}/tickets/${ticketId}/events`,
  },
  RCA: {
    GET: (companyId: string, ticketId: string) =>
      `/${companyId}/tickets/${ticketId}/rca`,
    CREATE: (companyId: string, ticketId: string) =>
      `/${companyId}/tickets/${ticketId}/rca`,
    UPDATE: (companyId: string, rcaId: string) => `/${companyId}/rca/${rcaId}`,
    SUBMIT: (companyId: string, rcaId: string) =>
      `/${companyId}/rca/${rcaId}/submit`,
    APPROVE: (companyId: string, rcaId: string) =>
      `/${companyId}/rca/${rcaId}/approve`,
    REJECT: (companyId: string, rcaId: string) =>
      `/${companyId}/rca/${rcaId}/reject`,
    EVENTS: (companyId: string, rcaId: string) =>
      `/${companyId}/rca/${rcaId}/events`,
  },
  ATTACHMENTS: {
    LIST: (companyId: string, ticketId: string) =>
      `/${companyId}/tickets/${ticketId}/attachments`,
    UPLOAD: (companyId: string, ticketId: string) =>
      `/${companyId}/tickets/${ticketId}/attachments`,
    DEPRECATE: (companyId: string, attachmentId: string) =>
      `/${companyId}/attachments/${attachmentId}/deprecate`,
    DOWNLOAD: (companyId: string, attachmentId: string) =>
      `/${companyId}/attachments/${attachmentId}/download`,
  },
  ANALYTICS: {
    DUPLICATES: (companyId: string) => `/${companyId}/analytics/duplicates`,
    CATEGORIES: (companyId: string) => `/${companyId}/analytics/categories`,
    EMBEDDINGS: (companyId: string) => `/${companyId}/analytics/embeddings`,
    APPROVALS: (companyId: string) => `/${companyId}/analytics/approvals`,
  },
};