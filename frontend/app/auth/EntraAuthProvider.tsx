'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import {
  PublicClientApplication,
  EventType,
  AccountInfo,
  AuthenticationResult,
} from '@azure/msal-browser';
import { MsalProvider } from '@azure/msal-react';
import { AUTH_MODE, ENTRA_CLIENT_ID, ENTRA_TENANT_ID, msalConfig, loginRequest } from './msalConfig';

interface EntraAuthContextType {
  authMode: string;
  account: AccountInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  getAccessToken: () => Promise<string | null>;
  getAuthHeaders: () => Promise<Record<string, string>>;
}

const EntraAuthContext = createContext<EntraAuthContextType>({
  authMode: AUTH_MODE,
  account: null,
  isAuthenticated: false,
  isLoading: true,
  login: async () => {},
  logout: async () => {},
  getAccessToken: async () => null,
  getAuthHeaders: async () => ({}),
});

export const useEntraAuth = () => useContext(EntraAuthContext);

let msalInstance: PublicClientApplication | null = null;

function getMsalInstance() {
  if (
    AUTH_MODE === 'entra' &&
    ENTRA_CLIENT_ID &&
    ENTRA_TENANT_ID &&
    !msalInstance &&
    typeof window !== 'undefined'
  ) {
    msalInstance = new PublicClientApplication(msalConfig);
  }
  return msalInstance;
}

export function EntraAuthProvider({ children }: { children: React.ReactNode }) {
  const [instance, setInstance] = useState<PublicClientApplication | null>(null);
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (AUTH_MODE === 'disabled') {
      setIsLoading(false);
      return;
    }

    const pca = getMsalInstance();
    if (!pca) {
      setIsLoading(false);
      return;
    }

    pca
      .initialize()
      .then(() => {
        return pca.handleRedirectPromise();
      })
      .then((response: AuthenticationResult | null) => {
        if (response?.account) {
          pca.setActiveAccount(response.account);
          setAccount(response.account);
        } else {
          const activeAccount = pca.getActiveAccount();
          if (activeAccount) {
            setAccount(activeAccount);
          } else {
            const accounts = pca.getAllAccounts();
            if (accounts.length > 0) {
              pca.setActiveAccount(accounts[0]);
              setAccount(accounts[0]);
            }
          }
        }
        setInstance(pca);
        setIsLoading(false);
      })
      .catch((error) => {
        console.error('[MSAL] Initialization failed:', error);
        setInstance(pca);
        setIsLoading(false);
      });

    const callbackId = pca.addEventCallback((event) => {
      if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
        const payload = event.payload as AuthenticationResult;
        pca.setActiveAccount(payload.account);
        setAccount(payload.account);
      }
    });

    return () => {
      if (callbackId) pca.removeEventCallback(callbackId);
    };
  }, []);

  const login = async () => {
    const pca = instance || getMsalInstance();
    if (!pca) return;
    try {
      await pca.loginRedirect(loginRequest);
    } catch (err) {
      console.error('[MSAL] Login error:', err);
    }
  };

  const logout = async () => {
    const pca = instance || getMsalInstance();
    if (!pca) return;
    try {
      await pca.logoutRedirect({
        account: account || undefined,
      });
      setAccount(null);
    } catch (err) {
      console.error('[MSAL] Logout error:', err);
    }
  };

  const getAccessToken = async (): Promise<string | null> => {
    if (AUTH_MODE === 'disabled') return null;
    const pca = instance || getMsalInstance();
    if (!pca || !account) return null;
    try {
      const response = await pca.acquireTokenSilent({
        ...loginRequest,
        account,
      });
      return response.accessToken || null;
    } catch (silentErr) {
      console.warn('[MSAL] Silent token acquisition failed:', silentErr);
      return null;
    }
  };

  const getAuthHeaders = async (): Promise<Record<string, string>> => {
    const token = await getAccessToken();
    if (!token) return {};
    return {
      Authorization: `Bearer ${token}`,
    };
  };

  const contextValue = {
    authMode: AUTH_MODE,
    account,
    isAuthenticated: AUTH_MODE === 'disabled' || !!account,
    isLoading,
    login,
    logout,
    getAccessToken,
    getAuthHeaders,
  };

  if (!instance) {
    return (
      <EntraAuthContext.Provider value={contextValue}>
        {children}
      </EntraAuthContext.Provider>
    );
  }

  return (
    <MsalProvider instance={instance}>
      <EntraAuthContext.Provider value={contextValue}>
        {children}
      </EntraAuthContext.Provider>
    </MsalProvider>
  );
}
