// SmartGuard AI — Premium Security Operations Center (SOC) Shell
import React, { useState, useEffect } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  Shield,
  LayoutDashboard,
  Users,
  Activity,
  LogOut,
  Menu,
  X,
  ChevronDown,
  Car,
  Zap,
  ScanFace,
  ShieldAlert,
  FileText,
  Calendar,
  Mail,
  Bell,
  QrCode,
  Radio,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { healthApi } from '../api/health';
import { StatusBadge } from '../components/ui/Badge';
import { UserAvatar } from '../components/ui/States';
import type { ReadinessResponse } from '../types';

interface NavItem {
  label: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  roles: string[];
  section?: string;
}

const NAV_ITEMS: NavItem[] = [
  // ── Operations ────────────────────────────────────────────────────────────
  {
    label: 'Overview',
    path: '/admin/dashboard',
    icon: LayoutDashboard,
    roles: ['ADMIN'],
    section: 'Operations',
  },
  {
    label: 'Overview',
    path: '/security/dashboard',
    icon: LayoutDashboard,
    roles: ['SECURITY'],
    section: 'Operations',
  },
  {
    label: 'Alert Center',
    path: '/security/alerts',
    icon: ShieldAlert,
    roles: ['SECURITY', 'ADMIN'],
    section: 'Operations',
  },
  {
    label: 'Visitor Passes',
    path: '/security/visitors',
    icon: QrCode,
    roles: ['SECURITY', 'ADMIN'],
    section: 'Operations',
  },
  {
    label: 'Gate Monitor',
    path: '/security/gate-monitor',
    icon: Radio,
    roles: ['SECURITY', 'ADMIN'],
    section: 'Operations',
  },
  {
    label: 'Security Accounts',
    path: '/admin/accounts',
    icon: Users,
    roles: ['ADMIN'],
    section: 'Operations',
  },
  {
    label: 'System Health',
    path: '/admin/health',
    icon: Activity,
    roles: ['ADMIN'],
    section: 'Operations',
  },
  {
    label: 'System Health',
    path: '/security/health',
    icon: Activity,
    roles: ['SECURITY'],
    section: 'Operations',
  },
  // Phase 2 — Campus Registry
  {
    label: 'People',
    path: '/admin/people',
    icon: ScanFace,
    roles: ['ADMIN'],
    section: 'Campus Registry',
  },
  {
    label: 'Vehicles',
    path: '/admin/vehicles',
    icon: Car,
    roles: ['ADMIN'],
    section: 'Campus Registry',
  },
  // Phase 2 — AI Tools
  {
    label: 'AI Verification Lab',
    path: '/security/ai-lab',
    icon: Zap,
    roles: ['SECURITY', 'ADMIN'],
    section: 'AI Tools',
  },
  // Phase 4 — Audit & Reports
  {
    label: 'Access Reports',
    path: '/admin/reports/access',
    icon: FileText,
    roles: ['ADMIN'],
    section: 'Audit & Reports',
  },
  {
    label: 'Daily Summary',
    path: '/admin/reports/daily-summary',
    icon: Calendar,
    roles: ['ADMIN'],
    section: 'Audit & Reports',
  },
  // Phase 4 — Notifications & Stakeholders
  {
    label: 'Security Contacts',
    path: '/admin/security-contacts',
    icon: Mail,
    roles: ['ADMIN'],
    section: 'Notifications',
  },
  {
    label: 'Delivery Logs',
    path: '/admin/notifications',
    icon: Bell,
    roles: ['ADMIN'],
    section: 'Notifications',
  },
];

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [healthStatus, setHealthStatus] = useState<ReadinessResponse | null>(null);

  // Poll system health for topbar indicator
  useEffect(() => {
    let mounted = true;
    const checkHealth = () => {
      healthApi
        .readiness()
        .then((data) => {
          if (mounted) setHealthStatus(data);
        })
        .catch(() => {
          if (mounted)
            setHealthStatus({ status: 'degraded', database: false, pgvector: false });
        });
    };

    checkHealth();
    const interval = setInterval(checkHealth, 60000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Filter navigation links for current role
  const userNav = NAV_ITEMS.filter((item) => item.roles.includes(user?.role ?? ''));

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  const isHealthy =
    healthStatus?.status === 'ready' &&
    healthStatus?.database &&
    healthStatus?.pgvector;

  const currentNavTitle =
    userNav.find((item) => item.path === location.pathname)?.label || 'Console';

  return (
    <div className="min-h-screen bg-[#0B0F19] text-slate-100 flex flex-col md:flex-row">
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/70 backdrop-blur-xs md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:sticky top-0 left-0 z-50 h-screen w-64 bg-[#0F172A] border-r border-white/[0.06] flex flex-col transition-transform duration-200 ease-in-out ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        {/* Brand Header */}
        <div className="p-5 border-b border-white/[0.06] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#7565F5] to-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/20 text-white shrink-0">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-sm text-slate-100 tracking-tight">
                  SmartGuard
                </span>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#7565F5]/20 text-[#A89CFC] border border-[#7565F5]/30">
                  AI
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-medium">
                Campus Security Operations
              </p>
            </div>
          </div>
          <button
            onClick={() => setMobileOpen(false)}
            className="md:hidden text-slate-400 hover:text-slate-200 p-1"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Role Badge Container */}
        <div className="px-5 py-3 border-b border-white/[0.04] bg-black/10">
          <div className="flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">
              Station Role
            </span>
            <StatusBadge
              variant={user?.role === 'ADMIN' ? 'primary' : 'info'}
              size="sm"
            >
              {user?.role === 'ADMIN' ? 'Administrator' : 'Security Officer'}
            </StatusBadge>
          </div>
        </div>

        {/* Navigation Links - grouped by section */}
        <nav className="flex-1 p-3.5 overflow-y-auto space-y-1">
          {(() => {
            const sections: string[] = [];
            userNav.forEach(item => {
              if (item.section && !sections.includes(item.section)) sections.push(item.section);
            });
            return sections.map(section => (
              <div key={section} className="mb-2">
                <div className="px-3 py-1.5 text-[10px] uppercase tracking-widest font-bold text-slate-500">
                  {section}
                </div>
                {userNav.filter(item => item.section === section).map((item) => {
                  const Icon = item.icon;
                  const isActive = location.pathname === item.path;
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      onClick={() => setMobileOpen(false)}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs sm:text-sm font-medium transition-all group ${
                        isActive
                          ? 'bg-[#7565F5]/10 text-white border-l-2 border-[#7565F5] font-semibold'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                      }`}
                    >
                      <Icon
                        className={`w-4 h-4 transition-colors ${
                          isActive ? 'text-[#9B8DFC]' : 'text-slate-400 group-hover:text-slate-300'
                        }`}
                      />
                      <span className="truncate">{item.label}</span>
                    </NavLink>
                  );
                })}
              </div>
            ));
          })()}
        </nav>

        {/* Sidebar Footer User Info */}
        <div className="p-3.5 border-t border-white/[0.06] bg-[#0E1524]">
          <div className="flex items-center justify-between gap-2 p-2 rounded-lg bg-white/[0.02]">
            <div className="flex items-center gap-2.5 min-w-0">
              <UserAvatar name={user?.full_name || 'U'} role={user?.role} size="sm" />
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-200 truncate">
                  {user?.full_name}
                </p>
                <p className="text-[11px] text-slate-500 truncate">
                  @{user?.username}
                </p>
              </div>
            </div>
            <button
              onClick={handleLogout}
              title="Logout"
              className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Topbar */}
        <header className="sticky top-0 z-30 h-14 bg-[#0B0F19]/90 backdrop-blur-md border-b border-white/[0.06] px-4 sm:px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileOpen(true)}
              className="md:hidden text-slate-400 hover:text-slate-200 p-1.5 rounded-lg hover:bg-white/[0.04]"
              aria-label="Open sidebar"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-2 text-xs sm:text-sm">
              <span className="text-slate-500">SmartGuard</span>
              <span className="text-slate-600">/</span>
              <span className="font-medium text-slate-200">{currentNavTitle}</span>
            </div>
          </div>

          {/* Right Topbar Actions */}
          <div className="flex items-center gap-3 sm:gap-4">
            {/* Live System Health Badge */}
            <div className="hidden sm:flex items-center">
              <StatusBadge
                variant={isHealthy ? 'success' : healthStatus ? 'warning' : 'neutral'}
                size="sm"
                pulse={isHealthy}
              >
                {isHealthy
                  ? 'Systems Operational'
                  : healthStatus
                  ? 'System Degraded'
                  : 'Checking Systems...'}
              </StatusBadge>
            </div>

            {/* Profile Dropdown */}
            <div className="relative">
              <button
                onClick={() => setProfileOpen(!profileOpen)}
                className="flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-white/[0.04] transition-colors text-left"
              >
                <UserAvatar name={user?.full_name || 'U'} role={user?.role} size="sm" />
                <div className="hidden sm:block text-right">
                  <p className="text-xs font-semibold text-slate-200 leading-tight">
                    {user?.full_name}
                  </p>
                  <p className="text-[10px] text-slate-500">{user?.role}</p>
                </div>
                <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
              </button>

              {/* Dropdown Menu */}
              {profileOpen && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setProfileOpen(false)}
                  />
                  <div className="absolute right-0 mt-1.5 w-48 bg-[#151C2C] border border-white/[0.08] rounded-xl shadow-xl shadow-black/50 py-1.5 z-20 animate-in fade-in zoom-in-95 duration-100">
                    <div className="px-3 py-2 border-b border-white/[0.06]">
                      <p className="text-xs font-medium text-slate-200">
                        {user?.full_name}
                      </p>
                      <p className="text-[11px] text-slate-400">@{user?.username}</p>
                    </div>
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-rose-400 hover:bg-rose-500/10 transition-colors"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                      <span>Sign Out</span>
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </header>

        {/* Page Content Viewport */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AppShell;
