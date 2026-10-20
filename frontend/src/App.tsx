// SmartGuard AI — Application Root & Routing (Phase 2)
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { RequireAuth, RequireRole, PublicOnly } from './routes/ProtectedRoutes';
import { AppShell } from './layouts/AppShell';

// Phase 1 pages
import LoginPage from './pages/auth/LoginPage';
import AdminDashboard from './pages/admin/AdminDashboard';
import AccountManagement from './pages/admin/AccountManagement';
import SystemHealth from './pages/admin/SystemHealth';
import SecurityDashboard from './pages/security/SecurityDashboard';
import SecurityHealth from './pages/security/SecurityHealth';

// Phase 2 pages
import PeopleManagement from './pages/admin/PeopleManagement';
import VehicleManagement from './pages/admin/VehicleManagement';
import AiVerificationLab from './pages/security/AiVerificationLab';

// Phase 4 pages
import AlertCenter from './pages/security/AlertCenter';
import AccessReports from './pages/admin/AccessReports';
import DailySummary from './pages/admin/DailySummary';
import SecurityContacts from './pages/admin/SecurityContacts';
import NotificationHistory from './pages/admin/NotificationHistory';

// Phase 5 pages
import VisitorManagement from './pages/security/VisitorManagement';

// IoT Integration page
import IotGateMonitor from './pages/security/IotGateMonitor';

function RootRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return (
    <Navigate
      to={user.role === 'ADMIN' ? '/admin/dashboard' : '/security/dashboard'}
      replace
    />
  );
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Auth Routes */}
          <Route element={<PublicOnly />}>
            <Route path="/login" element={<LoginPage />} />
          </Route>

          {/* Protected Routes inside SOC AppShell */}
          <Route element={<RequireAuth />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<RootRedirect />} />

              {/* Admin-only Routes */}
              <Route element={<RequireRole allowedRoles={['ADMIN']} />}>
                <Route path="/admin/dashboard" element={<AdminDashboard />} />
                <Route path="/admin/accounts" element={<AccountManagement />} />
                <Route path="/admin/health" element={<SystemHealth />} />
                {/* Phase 2: Admin */}
                <Route path="/admin/people" element={<PeopleManagement />} />
                <Route path="/admin/vehicles" element={<VehicleManagement />} />
                {/* Phase 4: Reports & Stakeholder Communications */}
                <Route path="/admin/reports/access" element={<AccessReports />} />
                <Route path="/admin/reports/daily-summary" element={<DailySummary />} />
                <Route path="/admin/security-contacts" element={<SecurityContacts />} />
                <Route path="/admin/notifications" element={<NotificationHistory />} />
              </Route>

              {/* Security Officer Routes (SECURITY + ADMIN) */}
              <Route element={<RequireRole allowedRoles={['SECURITY', 'ADMIN']} />}>
                <Route path="/security/dashboard" element={<SecurityDashboard />} />
                <Route path="/security/health" element={<SecurityHealth />} />
                {/* Phase 2: AI Lab */}
                <Route path="/security/ai-lab" element={<AiVerificationLab />} />
                {/* Phase 4: Security Alerts */}
                <Route path="/security/alerts" element={<AlertCenter />} />
                {/* Phase 5: Visitor Management & QR Passes */}
                <Route path="/security/visitors" element={<VisitorManagement />} />
                {/* IoT Gate Controller Monitor */}
                <Route path="/security/gate-monitor" element={<IotGateMonitor />} />
              </Route>
            </Route>
          </Route>

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
