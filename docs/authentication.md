# Authentication

DearBot separates local convenience from production safety through an explicit authentication mode.

## Local development

```dotenv
ENV=development
AUTH_MODE=disabled
NEXT_PUBLIC_AUTH_MODE=disabled
```

The frontend skips Microsoft sign-in and the backend supplies a clearly marked local development principal. This mode is rejected when `ENV=production`.

## Microsoft Entra

Production currently supports Microsoft Entra as its administrative identity provider:

```dotenv
ENV=production
AUTH_MODE=entra
NEXT_PUBLIC_AUTH_MODE=entra
ENTRA_TENANT_ID=<tenant-id>
ENTRA_CLIENT_ID=<api-application-client-id>
ENTRA_AUDIENCE=api://<api-application-client-id>
ENTRA_REQUIRED_SCOPE=admin.access
ADMIN_ALLOWED_OBJECT_IDS=["<administrator-object-id>"]
NEXT_PUBLIC_ENTRA_TENANT_ID=<tenant-id>
NEXT_PUBLIC_ENTRA_CLIENT_ID=<spa-application-client-id>
NEXT_PUBLIC_ENTRA_API_SCOPE=api://<api-application-client-id>/admin.access
```

Use two app registrations or equivalent separation:

1. An API registration exposing the delegated `admin.access` scope.
2. A browser application authorized to request that scope using authorization code flow with PKCE.

Configure the browser redirect URI as `<origin>/admin`. Do not create or place a client secret in the frontend.

## Authorization rules

The backend accepts only RS256 access tokens with the configured issuer and DearBot API audience. The token must include `admin.access` in `scp` or `roles`, the configured tenant ID, and an immutable `oid` claim.

When `ADMIN_ALLOWED_OBJECT_IDS` is non-empty, the token's `oid` must appear in that list. An empty list permits any principal in the configured tenant that has explicitly received the required scope or application role.

Email addresses and display names are not authorization identifiers. Microsoft Graph access tokens and browser ID tokens are not DearBot API credentials.

## Token handling

MSAL stores tokens in memory rather than persistent browser storage. Tokens are sent only in the `Authorization: Bearer` header to the configured DearBot API origin.

## Planned provider support

A provider-neutral OIDC adapter and trusted-proxy mode are candidates for a later release. They should reuse the same internal principal model and fail-closed production rules rather than adding provider-specific authorization inside routes.
