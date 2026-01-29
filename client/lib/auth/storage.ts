import Cookies from 'js-cookie';

const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const USER_KEY = 'user';

export const tokenStorage = {
  setAccessToken: (token: string) => {
    // Using HttpOnly would be better but requires backend support
    // For now, store in both cookie and localStorage
    Cookies.set(ACCESS_TOKEN_KEY, token, {
      expires: 1, // 24 hours
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'Strict',
    });
    localStorage.setItem(ACCESS_TOKEN_KEY, token);
  },

  getAccessToken: () => {
    return Cookies.get(ACCESS_TOKEN_KEY) || localStorage.getItem(ACCESS_TOKEN_KEY);
  },

  setRefreshToken: (token: string) => {
    Cookies.set(REFRESH_TOKEN_KEY, token, {
      expires: 7, // 7 days
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'Strict',
      httpOnly: false, // Set to true in production with backend support
    });
    localStorage.setItem(REFRESH_TOKEN_KEY, token);
  },

  getRefreshToken: () => {
    return Cookies.get(REFRESH_TOKEN_KEY) || localStorage.getItem(REFRESH_TOKEN_KEY);
  },

  setUser: (user: Record<string, unknown>) => {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },

  getUser: (): Record<string, unknown> | null => {
    const user = localStorage.getItem(USER_KEY);
    return user ? JSON.parse(user) : null;
  },

  clear: () => {
    Cookies.remove(ACCESS_TOKEN_KEY);
    Cookies.remove(REFRESH_TOKEN_KEY);
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};