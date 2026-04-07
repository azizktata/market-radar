export function clearAuth() {
  // Cookie is HttpOnly - cleared server-side via /api/auth/logout
  // This is just a placeholder for any client-side cleanup if needed
}

export function isAuthenticated(): boolean {
  return true; // Middleware handles redirect if not authenticated
}
