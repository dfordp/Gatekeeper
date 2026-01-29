export type UserRole = 'platform_admin' | 'company_admin' | 'engineer' | 'requester';

export interface User {
  id: string;
  email: string;
  name: string;
  company_id: string;
  role: UserRole;
  created_at: string;
  updated_at: string;
}

export interface Company {
  id: string;
  name: string;
  slug: string;
}

export interface JWTPayload {
  sub: string; // user_id
  company_id: string;
  role: UserRole;
  email: string;
  exp: number;
  iat: number;
}

export interface LoginResponse {
  success: boolean;
  data: {
    access_token: string;
    refresh_token: string;
    user: User;
  };
}

export interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}