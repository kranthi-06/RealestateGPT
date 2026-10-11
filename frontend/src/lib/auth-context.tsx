"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import type { User } from "@/lib/types";
import { authApi, getStoredToken, setStoredToken, ApiError } from "@/lib/api";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (email: string, fullName: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  /**
   * Session restoration combines the HttpOnly session cookie and
   * the persistent client bearer token for resilient cross-environment auth.
   */
  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      authApi
        .getProfile()
        .then((profile) => {
          if (!cancelled) setUser(profile);
        })
        .catch((err) => {
          if (!cancelled) {
            if (err instanceof ApiError && err.status === 401) {
              setStoredToken(null);
            }
            setUser(null);
          }
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login({ email, password });
    if (response.access_token) {
      setStoredToken(response.access_token);
    }
    setUser(response.user);
    return response.user;
  }, []);

  const register = useCallback(async (email: string, fullName: string, password: string) => {
    const response = await authApi.register({
      email,
      full_name: fullName,
      password,
    });
    if (response.access_token) {
      setStoredToken(response.access_token);
    }
    setUser(response.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Even if the request fails, drop local state so the UI signs out.
    } finally {
      setStoredToken(null);
      setUser(null);
    }
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      const profile = await authApi.getProfile();
      setUser(profile);
    } catch {
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
