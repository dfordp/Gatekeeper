import { JWTPayload } from './types';

export const jwtUtils = {
  decode: (token: string): JWTPayload | null => {
    try {
      const parts = token.split('.');
      if (parts.length !== 3) return null;

      const decoded = JSON.parse(
        Buffer.from(parts[1], 'base64').toString('utf-8')
      );
      return decoded as JWTPayload;
    } catch (error) {
      console.error('Failed to decode JWT:', error);
      return null;
    }
  },

  isExpired: (token: string): boolean => {
    const payload = jwtUtils.decode(token);
    if (!payload) return true;

    const now = Math.floor(Date.now() / 1000);
    return payload.exp < now;
  },

  isExpiringSoon: (token: string, minutesBuffer: number = 5): boolean => {
    const payload = jwtUtils.decode(token);
    if (!payload) return true;

    const now = Math.floor(Date.now() / 1000);
    const expiringIn = payload.exp - now;
    return expiringIn < minutesBuffer * 60;
  },

  getPayload: (token: string): JWTPayload | null => {
    if (jwtUtils.isExpired(token)) return null;
    return jwtUtils.decode(token);
  },
};