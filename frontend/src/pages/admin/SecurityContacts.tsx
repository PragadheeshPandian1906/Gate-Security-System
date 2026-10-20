// SmartGuard AI — Phase 4 Security Contacts Management
// Manage external recipients, notification preferences, severity thresholds, and delivery test.

import React, { useState, useEffect, useCallback } from 'react';
import {
  UserPlus,
  Mail,
  Send,
  Edit2,
  Trash2,
  CheckCircle,
  Search,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import {
  contactsApi,
  type SecurityContact,
  type SecurityContactCreateInput,
  type EmailConfigStatus,
} from '../../api/contacts';
import { PageHeader } from '../../components/ui/PageHeader';
import { StatusBadge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardContent } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import { ShieldCheck, CheckCircle2, AlertTriangle, Key } from 'lucide-react';

const AVAILABLE_CATEGORIES = [
  { id: 'WATCHLIST_HIT', label: 'Watchlist Hit' },
  { id: 'REPEATED_DENIAL', label: 'Repeated Denial' },
  { id: 'DENIED_ACCESS', label: 'Denied Access' },
  { id: 'MANUAL_REVIEW', label: 'Manual Review' },
];

export default function SecurityContacts() {
  const [contacts, setContacts] = useState<SecurityContact[]>([]);
  const [configStatus, setConfigStatus] = useState<EmailConfigStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [testingId, setTestingId] = useState<string | null>(null);

  // Add / Edit Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editingContact, setEditingContact] = useState<SecurityContact | null>(null);
  const [formData, setFormData] = useState<SecurityContactCreateInput>({
    full_name: '',
    email: '',
    is_active: true,
    min_severity: 'HIGH',
    daily_summary_enabled: true,
    notify_categories: ['WATCHLIST_HIT', 'REPEATED_DENIAL'],
  });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadContacts = useCallback(async () => {
    setLoading(true);
    try {
      const [contactsData, configData] = await Promise.all([
        contactsApi.listContacts(search.trim() || undefined),
        contactsApi.getConfigStatus().catch(() => null),
      ]);
      setContacts(contactsData);
      if (configData) setConfigStatus(configData);
    } catch (err: any) {
      console.error('Failed to load security contacts:', err);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    loadContacts();
  }, [loadContacts]);

  const openAddModal = () => {
    setEditingContact(null);
    setFormData({
      full_name: '',
      email: '',
      is_active: true,
      min_severity: 'HIGH',
      daily_summary_enabled: true,
      notify_categories: ['WATCHLIST_HIT', 'REPEATED_DENIAL'],
    });
    setFormError(null);
    setModalOpen(true);
  };

  const openEditModal = (contact: SecurityContact) => {
    setEditingContact(contact);
    setFormData({
      full_name: contact.full_name,
      email: contact.email,
      is_active: contact.is_active,
      min_severity: contact.min_severity,
      daily_summary_enabled: contact.daily_summary_enabled,
      notify_categories: contact.notify_categories || [],
    });
    setFormError(null);
    setModalOpen(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      if (editingContact) {
        await contactsApi.updateContact(editingContact.id, formData);
      } else {
        await contactsApi.createContact(formData);
      }
      setModalOpen(false);
      loadContacts();
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Failed to save contact');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (contact: SecurityContact) => {
    if (!window.confirm(`Are you sure you want to delete ${contact.full_name} (${contact.email})?`)) {
      return;
    }
    try {
      await contactsApi.deleteContact(contact.id);
      loadContacts();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to delete contact');
    }
  };

  const handleTestEmail = async (id: string) => {
    setTestingId(id);
    try {
      const res = await contactsApi.sendTestEmail(id);
      alert(res.message || 'Test email dispatched successfully.');
      loadContacts();
    } catch (err: any) {
      alert('Test email failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setTestingId(null);
    }
  };

  const toggleCategory = (catId: string) => {
    const current = formData.notify_categories || [];
    if (current.includes(catId)) {
      setFormData({ ...formData, notify_categories: current.filter((c) => c !== catId) });
    } else {
      setFormData({ ...formData, notify_categories: [...current, catId] });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Security Contacts & Email Notifications"
        description="Manage external stakeholders, notification rules, severity thresholds, and delivery endpoints"
        action={
          <div className="flex items-center gap-3">
            <Button variant="primary" size="sm" onClick={openAddModal}>
              <UserPlus className="w-4 h-4 mr-1.5" />
              Add Contact
            </Button>
            <Button variant="secondary" size="sm" onClick={loadContacts} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        }
      />

      {/* Outgoing Email Gateway Status (.env backend configuration) */}
      <Card className="bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border-indigo-900/50 shadow-lg">
        <CardContent className="p-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-[#7565F5] shrink-0 mt-0.5">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-slate-200">
                    Active Email Dispatch Gateway (Sender Configuration)
                  </h3>
                  {configStatus?.email_enabled ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      <CheckCircle2 className="w-3 h-3" /> Live & Ready
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                      <AlertTriangle className="w-3 h-3" /> Disabled / Dry-run
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Alerts and reports are automatically dispatched from this authenticated gateway configured in your backend environment.
                </p>
                <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 mt-2.5 text-xs text-slate-300">
                  <div className="flex items-center gap-1.5">
                    <span className="text-slate-500">Sender:</span>
                    <span className="font-mono text-indigo-300 font-medium">
                      {configStatus?.from_address || 'Not configured in .env'}
                    </span>
                    {configStatus?.from_name && (
                      <span className="text-slate-500">({configStatus.from_name})</span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-slate-500">Provider:</span>
                    <span className="font-semibold uppercase tracking-wider text-slate-200 bg-slate-800 px-1.5 py-0.5 rounded text-[10px]">
                      {configStatus?.email_provider || 'CONSOLE'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-slate-500">API Key:</span>
                    <span className="inline-flex items-center gap-1 text-slate-300">
                      <Key className="w-3 h-3 text-emerald-400" />
                      {configStatus?.has_api_key ? 'Authenticated' : 'Missing'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {configStatus?.from_address && !contacts.some((c) => c.email.toLowerCase() === configStatus.from_address.toLowerCase()) && (
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 text-xs border-indigo-500/30 hover:bg-indigo-500/10 text-indigo-300"
                onClick={() => {
                  setEditingContact(null);
                  setFormData({
                    full_name: configStatus.from_name || 'System Admin',
                    email: configStatus.from_address,
                    is_active: true,
                    min_severity: 'HIGH',
                    daily_summary_enabled: true,
                    notify_categories: ['WATCHLIST_HIT', 'REPEATED_DENIAL'],
                  });
                  setFormError(null);
                  setModalOpen(true);
                }}
              >
                <UserPlus className="w-3.5 h-3.5 mr-1.5 text-[#7565F5]" />
                Add Sender to Recipient List
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Search Bar */}
      <Card className="bg-slate-900/70 border-slate-800">
        <CardContent className="p-4">
          <div className="relative max-w-md">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by name or email address..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
            />
          </div>
        </CardContent>
      </Card>

      {/* Contacts Table */}
      <Card className="bg-slate-900/60 border-slate-800">
        <CardContent className="p-0">
          {loading ? (
            <div className="py-20 flex justify-center items-center">
              <Loader2 className="w-8 h-8 text-[#7565F5] animate-spin" />
            </div>
          ) : contacts.length === 0 ? (
            <div className="py-16 text-center text-slate-400">
              <Mail className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <p className="text-base font-medium">No security contacts configured</p>
              <p className="text-xs text-slate-500 mt-1">
                Add an external contact to start receiving instant security alerts and daily summaries.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase tracking-wider bg-slate-950/40">
                    <th className="py-3.5 px-4">Contact</th>
                    <th className="py-3.5 px-4">Email</th>
                    <th className="py-3.5 px-4">Min. Severity</th>
                    <th className="py-3.5 px-4">Alert Categories</th>
                    <th className="py-3.5 px-4">Daily Briefing</th>
                    <th className="py-3.5 px-4">Status</th>
                    <th className="py-3.5 px-4">Last Notification</th>
                    <th className="py-3.5 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-xs">
                  {contacts.map((contact) => (
                    <tr key={contact.id} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-3.5 px-4 font-semibold text-slate-200">
                        {contact.full_name}
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-300">
                        {contact.email}
                      </td>
                      <td className="py-3.5 px-4">
                        <StatusBadge
                          variant={
                            contact.min_severity === 'CRITICAL'
                              ? 'error'
                              : contact.min_severity === 'HIGH'
                              ? 'warning'
                              : 'info'
                          }
                          size="sm"
                        >
                          {contact.min_severity}
                        </StatusBadge>
                      </td>
                      <td className="py-3.5 px-4 max-w-xs">
                        <div className="flex flex-wrap gap-1">
                          {contact.notify_categories && contact.notify_categories.length > 0 ? (
                            contact.notify_categories.map((cat) => (
                              <span
                                key={cat}
                                className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700 font-medium"
                              >
                                {cat.replace('_', ' ')}
                              </span>
                            ))
                          ) : (
                            <span className="text-slate-500 text-[11px]">All categories</span>
                          )}
                        </div>
                      </td>
                      <td className="py-3.5 px-4">
                        {contact.daily_summary_enabled ? (
                          <span className="text-emerald-400 font-medium flex items-center gap-1">
                            <CheckCircle className="w-3.5 h-3.5" /> Enabled
                          </span>
                        ) : (
                          <span className="text-slate-500">Disabled</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4">
                        <StatusBadge variant={contact.is_active ? 'success' : 'neutral'} size="sm">
                          {contact.is_active ? 'Active' : 'Inactive'}
                        </StatusBadge>
                      </td>
                      <td className="py-3.5 px-4 text-slate-400">
                        {contact.last_notified_at ? (
                          <span>
                            {new Date(contact.last_notified_at).toLocaleString([], {
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}{' '}
                            ({contact.last_notification_status || 'OK'})
                          </span>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant="secondary"
                            size="sm"
                            title="Send Test Email"
                            onClick={() => handleTestEmail(contact.id)}
                            disabled={testingId === contact.id}
                          >
                            <Send className={`w-3.5 h-3.5 ${testingId === contact.id ? 'animate-pulse' : ''}`} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            title="Edit Contact"
                            onClick={() => openEditModal(contact)}
                          >
                            <Edit2 className="w-3.5 h-3.5 text-slate-400 hover:text-white" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            title="Delete Contact"
                            onClick={() => handleDelete(contact)}
                          >
                            <Trash2 className="w-3.5 h-3.5 text-rose-400 hover:text-rose-300" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Add / Edit Contact Modal */}
      {modalOpen && (
        <Modal
          isOpen={modalOpen}
          onClose={() => setModalOpen(false)}
          title={editingContact ? 'Edit Security Contact' : 'New Security Contact'}
          maxWidth="md"
        >
          <form onSubmit={handleSave} className="space-y-4 text-xs">
            {formError && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400">
                {formError}
              </div>
            )}

            <div>
              <label className="text-slate-400 font-medium block mb-1">Full Name *</label>
              <input
                type="text"
                required
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                placeholder="Chief Security Officer"
                className="w-full px-3 py-2 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
              />
            </div>

            <div>
              <label className="text-slate-400 font-medium block mb-1">Email Address *</label>
              <input
                type="email"
                required
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="security@campus.edu"
                className="w-full px-3 py-2 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 font-medium block mb-1">Minimum Severity</label>
                <select
                  value={formData.min_severity}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      min_severity: e.target.value as any,
                    })
                  }
                  className="w-full px-2.5 py-2 text-xs bg-slate-800 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-[#7565F5]"
                >
                  <option value="LOW">LOW and above</option>
                  <option value="MEDIUM">MEDIUM and above</option>
                  <option value="HIGH">HIGH and above</option>
                  <option value="CRITICAL">CRITICAL only</option>
                </select>
              </div>

              <div className="flex flex-col justify-end">
                <label className="flex items-center gap-2 p-2 bg-slate-800/80 rounded-lg border border-slate-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    className="rounded border-slate-700 bg-slate-800 text-[#7565F5]"
                  />
                  <span className="text-slate-200 font-medium">Contact Active</span>
                </label>
              </div>
            </div>

            <div>
              <label className="text-slate-400 font-medium block mb-1">Alert Categories</label>
              <div className="grid grid-cols-2 gap-2 p-2.5 bg-slate-800/50 rounded-lg border border-slate-700">
                {AVAILABLE_CATEGORIES.map((cat) => (
                  <label key={cat.id} className="flex items-center gap-2 text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={(formData.notify_categories || []).includes(cat.id)}
                      onChange={() => toggleCategory(cat.id)}
                      className="rounded border-slate-700 bg-slate-800 text-[#7565F5]"
                    />
                    <span>{cat.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label className="flex items-center gap-2 p-2.5 bg-slate-800/80 rounded-lg border border-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.daily_summary_enabled}
                  onChange={(e) => setFormData({ ...formData, daily_summary_enabled: e.target.checked })}
                  className="rounded border-slate-700 bg-slate-800 text-[#7565F5]"
                />
                <div>
                  <span className="text-slate-200 font-medium block">Receive Daily Security Briefing</span>
                  <span className="text-slate-500 text-[11px]">Deliver summary email every evening</span>
                </div>
              </label>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-800">
              <Button variant="ghost" size="sm" type="button" onClick={() => setModalOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" type="submit" disabled={submitting}>
                {submitting ? 'Saving...' : editingContact ? 'Update Contact' : 'Create Contact'}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
