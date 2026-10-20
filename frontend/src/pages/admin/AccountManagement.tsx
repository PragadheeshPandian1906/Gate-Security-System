// SmartGuard AI — Premium Security Account Management
import React, { useState, useEffect, useCallback } from 'react';
import {
  UserPlus,
  KeyRound,
  ShieldAlert,
  ShieldCheck,
  RotateCcw,
} from 'lucide-react';
import { accountsApi } from '../../api/accounts';
import { extractApiError } from '../../api/client';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { SearchInput, Select, Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { StatusBadge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { AlertBanner } from '../../components/ui/Alert';
import { UserAvatar, EmptyState } from '../../components/ui/States';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/ui/Table';
import type { Account, Role, AccountCreate, AccountStatus } from '../../types';

export function AccountManagement() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  // Create Modal state
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<AccountCreate>({
    username: '',
    full_name: '',
    role: 'SECURITY',
    password: '',
  });
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Reset Password Modal state
  const [resetOpen, setResetOpen] = useState(false);
  const [targetAccount, setTargetAccount] = useState<Account | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [mustChange, setMustChange] = useState(true);
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  // Status toggle loading tracking
  const [statusTogglingId, setStatusTogglingId] = useState<string | null>(null);

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await accountsApi.list({
        search: search.trim() || undefined,
        role: roleFilter !== 'ALL' ? roleFilter : undefined,
        status: statusFilter !== 'ALL' ? statusFilter : undefined,
      });
      setAccounts(data.accounts || []);
    } catch (err) {
      setError(extractApiError(err) || 'Failed to load accounts list.');
    } finally {
      setLoading(false);
    }
  }, [search, roleFilter, statusFilter]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  const handleClearFilters = () => {
    setSearch('');
    setRoleFilter('ALL');
    setStatusFilter('ALL');
  };

  const handleToggleStatus = async (account: Account) => {
    const newStatus: AccountStatus = account.status === 'active' ? 'inactive' : 'active';
    setStatusTogglingId(account.id);
    try {
      await accountsApi.updateStatus(account.id, { status: newStatus });
      setSuccessMsg(
        `Account @${account.username} marked as ${newStatus.toUpperCase()}.`
      );
      fetchAccounts();
    } catch (err) {
      setError(extractApiError(err) || 'Failed to update account status.');
    } finally {
      setStatusTogglingId(null);
    }
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createForm.username.trim() || !createForm.full_name.trim() || !createForm.password) {
      setCreateError('All fields are required.');
      return;
    }
    if (createForm.password.length < 8) {
      setCreateError('Password must be at least 8 characters.');
      return;
    }

    setCreateSubmitting(true);
    setCreateError(null);
    try {
      await accountsApi.create({
        ...createForm,
        username: createForm.username.trim().toLowerCase(),
        full_name: createForm.full_name.trim(),
      });
      setSuccessMsg(`Account @${createForm.username} successfully provisioned.`);
      setCreateOpen(false);
      setCreateForm({ username: '', full_name: '', role: 'SECURITY', password: '' });
      fetchAccounts();
    } catch (err) {
      setCreateError(extractApiError(err) || 'Failed to create user account.');
    } finally {
      setCreateSubmitting(false);
    }
  };

  const handleResetPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetAccount) return;
    if (!newPassword || newPassword.length < 8) {
      setResetError('New password must be at least 8 characters.');
      return;
    }

    setResetSubmitting(true);
    setResetError(null);
    try {
      await accountsApi.resetPassword(targetAccount.id, {
        new_password: newPassword,
        must_change_password: mustChange,
      });
      setSuccessMsg(`Password reset for @${targetAccount.username}.`);
      setResetOpen(false);
      setNewPassword('');
      setTargetAccount(null);
    } catch (err) {
      setResetError(extractApiError(err) || 'Failed to reset user password.');
    } finally {
      setResetSubmitting(false);
    }
  };

  const hasActiveFilters = search || roleFilter !== 'ALL' || statusFilter !== 'ALL';

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Security Accounts"
        description="Provision personnel profiles, manage operational role assignments, and oversee account security status."
        badge={
          <StatusBadge variant="neutral" size="sm">
            {accounts.length} Total
          </StatusBadge>
        }
        action={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<UserPlus className="w-4 h-4" />}
            onClick={() => {
              setCreateError(null);
              setCreateOpen(true);
            }}
          >
            Create Account
          </Button>
        }
      />

      {/* Notifications */}
      {error && (
        <AlertBanner variant="error" onClose={() => setError(null)}>
          {error}
        </AlertBanner>
      )}
      {successMsg && (
        <AlertBanner variant="success" onClose={() => setSuccessMsg(null)}>
          {successMsg}
        </AlertBanner>
      )}

      {/* Filters Toolbar */}
      <Card>
        <CardContent className="p-3 sm:p-4">
          <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3">
            <div className="flex-1">
              <SearchInput
                placeholder="Search by username or personnel name..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onClear={() => setSearch('')}
              />
            </div>
            <div className="flex items-center gap-3">
              <div className="w-40">
                <Select
                  value={roleFilter}
                  onChange={(e) => setRoleFilter(e.target.value)}
                  aria-label="Filter by role"
                >
                  <option value="ALL">All Roles</option>
                  <option value="ADMIN">Administrator</option>
                  <option value="SECURITY">Security Officer</option>
                </Select>
              </div>
              <div className="w-36">
                <Select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  aria-label="Filter by status"
                >
                  <option value="ALL">All Status</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </Select>
              </div>
              {hasActiveFilters && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleClearFilters}
                  leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
                  className="shrink-0 text-slate-400 hover:text-slate-200"
                >
                  Reset
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Accounts Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-12 text-center text-xs text-slate-400">
              Loading personnel records...
            </div>
          ) : accounts.length === 0 ? (
            <EmptyState
              title="No accounts match your criteria"
              description={
                hasActiveFilters
                  ? 'Try adjusting your search query or role/status filters.'
                  : 'Start by creating your first personnel account.'
              }
              action={
                hasActiveFilters
                  ? { label: 'Clear Filters', onClick: handleClearFilters }
                  : { label: 'Create Account', onClick: () => setCreateOpen(true) }
              }
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User / Identity</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Password Policy</TableHead>
                  <TableHead>Registered</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {accounts.map((acc) => {
                  const isToggling = statusTogglingId === acc.id;

                  return (
                    <TableRow key={acc.id}>
                      {/* Name & Username */}
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <UserAvatar name={acc.full_name} role={acc.role} size="sm" />
                          <div className="min-w-0">
                            <p className="font-semibold text-xs text-slate-100 truncate">
                              {acc.full_name}
                            </p>
                            <p className="text-[11px] text-slate-400 font-mono truncate">
                              @{acc.username}
                            </p>
                          </div>
                        </div>
                      </TableCell>

                      {/* Role */}
                      <TableCell>
                        <StatusBadge
                          variant={acc.role === 'ADMIN' ? 'primary' : 'info'}
                          size="sm"
                        >
                          {acc.role === 'ADMIN' ? 'Administrator' : 'Security Officer'}
                        </StatusBadge>
                      </TableCell>

                      {/* Status */}
                      <TableCell>
                        <StatusBadge
                          variant={acc.status === 'active' ? 'success' : 'neutral'}
                          size="sm"
                          pulse={acc.status === 'active'}
                        >
                          {acc.status.toUpperCase()}
                        </StatusBadge>
                      </TableCell>

                      {/* Password Reset Flag */}
                      <TableCell>
                        {acc.must_change_password ? (
                          <StatusBadge variant="warning" size="sm">
                            Reset Required
                          </StatusBadge>
                        ) : (
                          <span className="text-xs text-slate-500 font-medium">Standard</span>
                        )}
                      </TableCell>

                      {/* Created At */}
                      <TableCell className="text-xs text-slate-400 font-mono">
                        {new Date(acc.created_at).toLocaleDateString()}
                      </TableCell>

                      {/* Actions */}
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Reset Password Button */}
                          <Button
                            variant="secondary"
                            size="sm"
                            leftIcon={<KeyRound className="w-3.5 h-3.5 text-slate-400" />}
                            onClick={() => {
                              setTargetAccount(acc);
                              setNewPassword('');
                              setResetError(null);
                              setResetOpen(true);
                            }}
                            title="Reset Password"
                          >
                            <span className="hidden sm:inline">Reset</span>
                          </Button>

                          {/* Activate/Deactivate Button */}
                          <Button
                            variant={acc.status === 'active' ? 'danger' : 'secondary'}
                            size="sm"
                            isLoading={isToggling}
                            onClick={() => handleToggleStatus(acc)}
                            leftIcon={
                              acc.status === 'active' ? (
                                <ShieldAlert className="w-3.5 h-3.5" />
                              ) : (
                                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                              )
                            }
                            title={acc.status === 'active' ? 'Deactivate' : 'Activate'}
                          >
                            <span className="hidden sm:inline">
                              {acc.status === 'active' ? 'Deactivate' : 'Activate'}
                            </span>
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Create Account Modal */}
      <Modal
        isOpen={createOpen}
        onClose={() => !createSubmitting && setCreateOpen(false)}
        title="Provision Personnel Account"
        description="Create credentials and assign an operational role."
        maxWidth="md"
        footer={
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setCreateOpen(false)}
              disabled={createSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleCreateSubmit}
              isLoading={createSubmitting}
            >
              Provision Account
            </Button>
          </>
        }
      >
        <form onSubmit={handleCreateSubmit} className="space-y-4">
          {createError && (
            <AlertBanner variant="error" onClose={() => setCreateError(null)}>
              {createError}
            </AlertBanner>
          )}

          <Input
            label="Full Name"
            placeholder="e.g. Johnathan Vance"
            value={createForm.full_name}
            onChange={(e) => setCreateForm({ ...createForm, full_name: e.target.value })}
            required
            disabled={createSubmitting}
            autoFocus
          />

          <Input
            label="Username"
            placeholder="e.g. jvance or officer2"
            value={createForm.username}
            onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })}
            required
            disabled={createSubmitting}
          />

          <Select
            label="Operational Role"
            value={createForm.role}
            onChange={(e) => setCreateForm({ ...createForm, role: e.target.value as Role })}
            disabled={createSubmitting}
          >
            <option value="SECURITY">Security Officer (Terminal & Gates)</option>
            <option value="ADMIN">System Administrator (Full Management)</option>
          </Select>

          <Input
            label="Initial Password"
            type="password"
            placeholder="Minimum 8 characters"
            value={createForm.password}
            onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
            required
            disabled={createSubmitting}
          />
        </form>
      </Modal>

      {/* Reset Password Modal */}
      <Modal
        isOpen={resetOpen}
        onClose={() => !resetSubmitting && setResetOpen(false)}
        title={`Reset Password for @${targetAccount?.username}`}
        description="Set a new temporary password for this user account."
        maxWidth="sm"
        footer={
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setResetOpen(false)}
              disabled={resetSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleResetPasswordSubmit}
              isLoading={resetSubmitting}
            >
              Update Password
            </Button>
          </>
        }
      >
        <form onSubmit={handleResetPasswordSubmit} className="space-y-4">
          {resetError && (
            <AlertBanner variant="error" onClose={() => setResetError(null)}>
              {resetError}
            </AlertBanner>
          )}

          <Input
            label="New Password"
            type="password"
            placeholder="Minimum 8 characters"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            disabled={resetSubmitting}
            autoFocus
          />

          <Select
            label="Force Password Reset on Next Login"
            value={mustChange ? 'true' : 'false'}
            onChange={(e) => setMustChange(e.target.value === 'true')}
            disabled={resetSubmitting}
          >
            <option value="true">Yes, user must change password</option>
            <option value="false">No, keep assigned password</option>
          </Select>
        </form>
      </Modal>
    </div>
  );
}

export default AccountManagement;
