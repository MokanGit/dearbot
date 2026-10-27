import { Configuration, LogLevel } from "@azure/msal-browser";

export const AUTH_MODE = process.env.NEXT_PUBLIC_AUTH_MODE || "disabled";

export const ENTRA_CLIENT_ID = process.env.NEXT_PUBLIC_ENTRA_CLIENT_ID || "";
export const ENTRA_TENANT_ID = process.env.NEXT_PUBLIC_ENTRA_TENANT_ID || "";
export const ENTRA_API_SCOPE =
  process.env.NEXT_PUBLIC_ENTRA_API_SCOPE ||
  (ENTRA_CLIENT_ID ? `api://${ENTRA_CLIENT_ID}/admin.access` : "");

export const msalConfig: Configuration = {
  auth: {
    clientId: ENTRA_CLIENT_ID,
    authority: `https://login.microsoftonline.com/${ENTRA_TENANT_ID}`,
    redirectUri:
      typeof window !== "undefined"
        ? `${window.location.origin}/admin`
        : "http://localhost:3000/admin",
    postLogoutRedirectUri:
      typeof window !== "undefined"
        ? `${window.location.origin}/admin`
        : "http://localhost:3000/admin",
  },
  cache: {
    cacheLocation: "memoryStorage",
  },
  system: {
    loggerOptions: {
      loggerCallback: (level, message, containsPii) => {
        if (containsPii) return;
        if (level === LogLevel.Error) {
          console.error("[MSAL Error]", message);
        }
      },
      logLevel: LogLevel.Warning,
    },
  },
};

export const loginRequest = {
  scopes: ENTRA_API_SCOPE ? [ENTRA_API_SCOPE] : [],
};
