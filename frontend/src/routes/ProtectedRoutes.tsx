// SmartGuard AI — Protected Routes
// Redirects unauthenticated users to /login.
// Redirects authenticated users to the correct dashboard based on role.

import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import type { Role } from '../types';

// Shows a centered spinner while auth state is being restored from localStorage
function LoadingScreen() {
  return (
    <div className="min-h-screen bg-[#0B0F19] flex flex-col items-center justify-center p-4">
      <Loader2 className="w-8 h-8 text-[#7565F5] animate-spin mb-3" />
      <p className="text-xs font-medium text-slate-400">Verifying session...</p>
    </div>
  );
}

// Require authentication — if not logged in, redirect to /login
export function RequireAuth() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return <LoadingScreen />;
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <Outlet />;
}

// Require a specific role — if wrong role, redirect to correct dashboard
interface RequireRoleProps {
  allowedRoles: Role[];
}

export function RequireRole({ allowedRoles }: RequireRoleProps) {
  const { user } = useAuth();

  if (!user || !allowedRoles.includes(user.role)) {
    // Redirect to the correct dashboard for the user's actual role
    const fallback = user?.role === 'ADMIN' ? '/admin/dashboard' : '/security/dashboard';
    return <Navigate to={fallback} replace />;
  }
  return <Outlet />;
}

// Redirect logged-in users away from /login to their dashboard
export function PublicOnly() {
  const { isAuthenticated, isLoading, user } = useAuth();

  if (isLoading) return <LoadingScreen />;
  if (isAuthenticated && user) {
    const dest = user.role === 'ADMIN' ? '/admin/dashboard' : '/security/dashboard';
    return <Navigate to={dest} replace />;
  }
  return <Outlet />;
}
