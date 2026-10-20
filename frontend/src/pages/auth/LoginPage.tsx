// SmartGuard AI — Premium Security Operations Center Login
import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Shield,
  Lock,
  User,
  Eye,
  EyeOff,
  CheckCircle2,
  KeyRound,
  Fingerprint,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { authApi } from '../../api/auth';
import { extractApiError } from '../../api/client';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { AlertBanner } from '../../components/ui/Alert';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Please provide both username and password.');
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const response = await authApi.login({ username: username.trim(), password });
      login(response.access_token, response.user);

      if (from) {
        navigate(from, { replace: true });
      } else if (response.user.role === 'ADMIN') {
        navigate('/admin/dashboard', { replace: true });
      } else {
        navigate('/security/dashboard', { replace: true });
      }
    } catch (err: unknown) {
      const msg = extractApiError(err);
      setError(msg || 'Authentication failed. Please verify your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#0B0F19] flex items-center justify-center p-4 sm:p-6 lg:p-8 relative overflow-hidden">
      {/* Background Ambience */}
      <div className="absolute top-1/4 -left-32 w-96 h-96 bg-[#7565F5]/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 -right-32 w-96 h-96 bg-sky-500/10 rounded-full blur-3xl pointer-events-none" />

      {/* Main Container */}
      <div className="w-full max-w-4xl bg-[#151C2C] border border-white/[0.08] rounded-2xl shadow-2xl shadow-black/60 overflow-hidden grid grid-cols-1 lg:grid-cols-12 z-10">
        {/* Left Side: Brand & Product Overview (Desktop) */}
        <div className="hidden lg:flex lg:col-span-6 bg-[#0E1524] p-8 lg:p-10 flex-col justify-between border-r border-white/[0.06] relative">
          <div>
            {/* Logo */}
            <div className="flex items-center gap-3 mb-8">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-[#7565F5] to-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/25 text-white">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-bold text-base text-slate-100 tracking-tight">
                    SmartGuard
                  </span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#7565F5]/20 text-[#A89CFC] border border-[#7565F5]/30">
                    AI
                  </span>
                </div>
                <p className="text-xs text-slate-400">Campus Security & Surveillance</p>
              </div>
            </div>

            {/* Headline */}
            <div className="space-y-2 mb-8">
              <h2 className="text-2xl font-bold text-slate-100 tracking-tight">
                Secure Perimeter Control & Access Intelligence
              </h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                Integrated platform for gate security officers and system administrators.
              </p>
            </div>

            {/* Architecture Highlights */}
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-6 h-6 rounded-md bg-[#7565F5]/10 border border-[#7565F5]/30 flex items-center justify-center text-[#9B8DFC] shrink-0 mt-0.5">
                  <KeyRound className="w-3.5 h-3.5" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-slate-200">
                    Encrypted Token Protocol
                  </h4>
                  <p className="text-[11px] text-slate-400">
                    Stateless HMAC-SHA256 tokens with short-lived validity.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <div className="w-6 h-6 rounded-md bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 shrink-0 mt-0.5">
                  <Fingerprint className="w-3.5 h-3.5" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-slate-200">
                    pgvector AI Acceleration
                  </h4>
                  <p className="text-[11px] text-slate-400">
                    Sub-millisecond similarity indexing for facial recognition.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <div className="w-6 h-6 rounded-md bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0 mt-0.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-slate-200">
                    Partitioned Operational Roles
                  </h4>
                  <p className="text-[11px] text-slate-400">
                    Strict boundary isolation between Admin and Security Guard profiles.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Footer Status */}
          <div className="pt-6 border-t border-white/[0.04]">
            <div className="flex items-center justify-between text-[11px] text-slate-500">
              <span>Security Terminal Protocol</span>
              <span className="font-mono text-slate-400">v1.0.0-PROD</span>
            </div>
          </div>
        </div>

        {/* Right Side: Login Form */}
        <div className="lg:col-span-6 p-6 sm:p-8 lg:p-10 flex flex-col justify-center">
          {/* Mobile Header Branding */}
          <div className="flex items-center gap-3 mb-6 lg:hidden">
            <div className="w-8 h-8 rounded-lg bg-[#7565F5] flex items-center justify-center text-white shrink-0">
              <Shield className="w-4 h-4 text-white" />
            </div>
            <div>
              <span className="font-bold text-sm text-slate-100">SmartGuard AI</span>
              <p className="text-[11px] text-slate-400">Campus Security Portal</p>
            </div>
          </div>

          <div className="mb-6">
            <h1 className="text-xl sm:text-2xl font-bold text-slate-100 tracking-tight">
              Sign In to Terminal
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Enter your assigned station credentials to access the console.
            </p>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mb-4">
              <AlertBanner variant="error" onClose={() => setError(null)}>
                {error}
              </AlertBanner>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Username"
              id="username"
              name="username"
              type="text"
              placeholder="e.g. admin or officer1"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              leftIcon={<User className="w-4 h-4 text-slate-400" />}
              required
            />

            <Input
              label="Password"
              id="password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Enter your security password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              leftIcon={<Lock className="w-4 h-4 text-slate-400" />}
              rightIcon={
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="text-slate-400 hover:text-slate-200 transition-colors p-1"
                  tabIndex={-1}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              }
              required
            />

            <div className="pt-2">
              <Button
                type="submit"
                variant="primary"
                size="md"
                isLoading={loading}
                className="w-full py-2.5 text-sm font-semibold tracking-wide"
              >
                Sign In to Console
              </Button>
            </div>
          </form>

          {/* Security Notice */}
          <div className="mt-8 pt-4 border-t border-white/[0.06] text-center">
            <p className="text-[11px] text-slate-500 leading-normal">
              Authorized access only. All authorization attempts and IP sessions are recorded.
              Contact administrator for credential provisioning.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
