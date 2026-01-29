declare global {
  interface Window {
    gtag?: (command: string, eventName: string, properties?: Record<string, string | number | boolean | null>) => void;
  }
}

export const analytics = {
  trackEvent: (eventName: string, properties?: Record<string, string | number | boolean | null>) => {
    if (typeof window === 'undefined') return;

    const event = {
      name: eventName,
      timestamp: new Date().toISOString(),
      properties,
    };

    console.log('[Analytics]', event);

    // Send to analytics service (GA, Mixpanel, etc.)
    if (window.gtag) {
      window.gtag('event', eventName, properties);
    }
  },

  trackPageView: (pageName: string) => {
    analytics.trackEvent('page_view', { page_name: pageName });
  },

  trackError: (error: Error, context?: string) => {
    analytics.trackEvent('error', {
      message: error.message,
      stack: error.stack ?? null,
      context: context ?? null,
    });
  },
};