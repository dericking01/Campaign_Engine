// Shared by services/api.ts (dispatches on any 401) and AuthProvider.tsx
// (listens, clears state, redirects to /login) - kept in its own module so
// neither side needs to import the other and create a cycle.
export const AUTH_EXPIRED_EVENT = "campaign-engine:auth-expired";
