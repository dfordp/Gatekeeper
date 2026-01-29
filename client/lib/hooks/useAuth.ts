'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { AxiosError } from 'axios';
import { User } from '@/lib/schemas/auth';
import { tokenStorage } from '@/lib/auth/storage';
import { jwtUtils } from '@/lib/auth/jwt';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import toast from 'react-hot-toast';

export const useAuth = () => {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // Check token on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const token = tokenStorage.getAccessToken();

        if (!token || jwtUtils.isExpired(token)) {
          setUser(null);
          setIsAuthenticated(false);
          tokenStorage.clear();
        } else {
          const user = tokenStorage.getUser() as User;
          setUser(user);
          setIsAuthenticated(true);
        }
      } catch (error) {
        console.error('Auth check failed:', error);
        setUser(null);
        setIsAuthenticated(false);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const response = await apiClient.post(API_ENDPOINTS.AUTH.LOGIN, {
        email,
        password,
      });

      const { access_token, refresh_token, user } = response.data.data;

      tokenStorage.setAccessToken(access_token);
      tokenStorage.setRefreshToken(refresh_token);
      tokenStorage.setUser(user);

      setUser(user);
      setIsAuthenticated(true);
      toast.success('Logged in successfully');
      router.push('/dashboard');
    } catch (error) {
      const axiosError = error as AxiosError<{ detail: string }>;
      console.error('Login failed:', error);
      toast.error(
        axiosError.response?.data?.detail || 'Login failed. Please try again.'
      );
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [router]);

  const logout = useCallback(() => {
    tokenStorage.clear();
    setUser(null);
    setIsAuthenticated(false);
    toast.success('Logged out successfully');
    router.push('/login');
  }, [router]);

  const refresh = useCallback(async () => {
    try {
      const response = await apiClient.post(API_ENDPOINTS.AUTH.REFRESH, {
        refresh_token: tokenStorage.getRefreshToken(),
      });

      const { access_token, refresh_token } = response.data.data;
      tokenStorage.setAccessToken(access_token);
      tokenStorage.setRefreshToken(refresh_token);
    } catch (error) {
      console.error('Token refresh failed:', error);
      logout();
    }
  }, [logout]);

  return {
    user,
    isLoading,
    isAuthenticated,
    login,
    logout,
    refresh,
  };
};