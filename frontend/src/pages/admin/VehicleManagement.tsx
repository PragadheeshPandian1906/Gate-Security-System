// SmartGuard AI — Vehicle Management Page (Phase 2)
import { useState, useEffect, useCallback } from 'react';
import {
  Car, Plus, Search, Trash2, Edit2, ChevronLeft, ChevronRight,
  AlertCircle, Loader2, X, Shield, AlertTriangle, User,
} from 'lucide-react';
import { vehiclesApi, peopleApi, type Vehicle, type CampusPerson } from '../../api/phase2';
import { getErrorMessage } from '../../api/client';

// ── Status helpers ───────────────────────────────────────────────────────────

const STATUS_META: Record<string, { label: string; color: string; dot: string }> = {
  active:   { label: 'Active',   color: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20', dot: 'bg-emerald-400' },
  inactive: { label: 'Inactive', color: 'text-slate-400 bg-slate-700 border-slate-600',              dot: 'bg-slate-400' },
  flagged:  { label: 'Flagged',  color: 'text-red-400 bg-red-400/10 border-red-400/20',              dot: 'bg-red-400' },
};

function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_META[status] ?? STATUS_META.inactive;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${meta.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}

// ── Vehicle Form Modal ────────────────────────────────────────────────────────

interface VehicleFormProps {
  initial?: Partial<Vehicle>;
  onSave: (data: Partial<Vehicle>) => Promise<void>;
  onClose: () => void;
}

function VehicleFormModal({ initial, onSave, onClose }: VehicleFormProps) {
  const [form, setForm] = useState({
    plate_number: initial?.plate_number ?? '',
    make: initial?.make ?? '',
    model: initial?.model ?? '',
    color: initial?.color ?? '',
    vehicle_type: initial?.vehicle_type ?? '',
    owner_name: initial?.owner_name ?? '',
    owner_person_id: initial?.owner_person_id ?? '',
    status: initial?.status ?? 'active',
    notes: initial?.notes ?? '',
  });
  const [registeredPeople, setRegisteredPeople] = useState<CampusPerson[]>([]);
  const [loadingPeople, setLoadingPeople] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let unmounted = false;
    setLoadingPeople(true);
    peopleApi.list({ limit: 200, status: 'active' })
      .then(res => {
        if (!unmounted) setRegisteredPeople(res.data.items);
      })
      .catch(() => {
        // Fallback gracefully if people listing fails
      })
      .finally(() => {
        if (!unmounted) setLoadingPeople(false);
      });
    return () => { unmounted = true; };
  }, []);

  const handle = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  const handlePersonSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const personId = e.target.value;
    if (!personId) {
      setForm(f => ({ ...f, owner_person_id: '' }));
    } else {
      const match = registeredPeople.find(p => p.id === personId);
      setForm(f => ({
        ...f,
        owner_person_id: personId,
        owner_name: match ? match.full_name : f.owner_name,
      }));
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.plate_number.trim()) { setError('Plate number is required'); return; }
    setLoading(true); setError('');
    try {
      const payload: Partial<Vehicle> = {
        ...form,
        owner_person_id: form.owner_person_id || undefined,
        owner_name: form.owner_name.trim() || undefined,
      };
      await onSave(payload);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-lg bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-slate-800/50">
          <h2 className="text-lg font-semibold text-white">
            {initial ? 'Edit Vehicle' : 'Register Vehicle'}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X size={20} /></button>
        </div>

        <form onSubmit={submit} className="p-6 space-y-4">
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              <AlertCircle size={16} /> {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-xs font-medium text-slate-400 mb-1.5">License Plate Number *</label>
              <input
                value={form.plate_number} onChange={handle('plate_number')} required
                placeholder="e.g. TN-38-BX-4791"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono uppercase"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Make</label>
              <input value={form.make} onChange={handle('make')} placeholder="e.g. Toyota"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500" />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Model</label>
              <input value={form.model} onChange={handle('model')} placeholder="e.g. Innova"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500" />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Color</label>
              <input value={form.color} onChange={handle('color')} placeholder="e.g. White"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500" />
            </div>

            <div className="col-span-2">
              <label className="block text-xs font-medium text-slate-400 mb-1.5 flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-cyan-400">
                  <User size={13} />
                  Link to Registered Campus Member (Owner)
                </span>
                {loadingPeople && <span className="text-[11px] text-slate-500 animate-pulse">Loading members...</span>}
              </label>
              <select
                value={form.owner_person_id}
                onChange={handlePersonSelect}
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm focus:outline-none focus:border-cyan-500"
              >
                <option value="">-- External / Unlinked Visitor --</option>
                {registeredPeople.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.full_name} ({p.person_type.toUpperCase()}{p.employee_id ? ` · ${p.employee_id}` : ''}{p.department ? ` · ${p.department}` : ''})
                  </option>
                ))}
              </select>
              <p className="text-[11px] text-slate-500 mt-1">
                Selecting a registered person links the vehicle to their profile and auto-fills their name.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Owner Name</label>
              <input value={form.owner_name} onChange={handle('owner_name')} placeholder="Owner or driver name"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500" />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Status</label>
              <select value={form.status} onChange={handle('status')}
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm focus:outline-none focus:border-cyan-500">
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="flagged">Flagged</option>
              </select>
            </div>

            <div className="col-span-2">
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Notes</label>
              <textarea value={form.notes} onChange={handle('notes')} rows={2}
                placeholder="Optional notes..."
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500 resize-none" />
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={loading}
              className="flex items-center gap-2 px-5 py-2 bg-cyan-500 hover:bg-cyan-400 text-slate-900 font-semibold rounded-lg text-sm transition-colors disabled:opacity-50">
              {loading && <Loader2 size={14} className="animate-spin" />}
              {initial ? 'Save Changes' : 'Register'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function VehicleManagement() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  const [showCreate, setShowCreate] = useState(false);
  const [editVehicle, setEditVehicle] = useState<Vehicle | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await vehiclesApi.list({
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        search: search || undefined,
        status: statusFilter || undefined,
      });
      setVehicles(res.data.items);
      setTotal(res.data.total);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const createVehicle = async (data: Partial<Vehicle>) => {
    await vehiclesApi.create(data as Parameters<typeof vehiclesApi.create>[0]);
    setShowCreate(false);
    load();
  };

  const updateVehicle = async (data: Partial<Vehicle>) => {
    if (!editVehicle) return;
    await vehiclesApi.update(editVehicle.id, data);
    setEditVehicle(null);
    load();
  };

  const deleteVehicle = async (id: string) => {
    if (!confirm('Delete this vehicle?')) return;
    try {
      await vehiclesApi.delete(id);
      load();
    } catch (err) {
      alert(getErrorMessage(err));
    }
  };

  const activeCount = vehicles.filter(v => v.status === 'active').length;
  const flaggedCount = vehicles.filter(v => v.status === 'flagged').length;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="flex flex-col gap-6 p-6 min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400"><Car size={24} /></div>
            Vehicle Management
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Register and manage campus vehicles and license plates for ALPR matching
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-cyan-500 hover:bg-cyan-400 text-slate-900 font-semibold rounded-xl text-sm transition-all hover:shadow-lg hover:shadow-cyan-500/20"
        >
          <Plus size={16} /> Register Vehicle
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400"><Car size={20} /></div>
          <div>
            <p className="text-2xl font-bold text-white">{total}</p>
            <p className="text-xs text-slate-400">Total Registered</p>
          </div>
        </div>
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400"><Shield size={20} /></div>
          <div>
            <p className="text-2xl font-bold text-white">{activeCount}</p>
            <p className="text-xs text-slate-400">Active</p>
          </div>
        </div>
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-red-500/10 text-red-400"><AlertTriangle size={20} /></div>
          <div>
            <p className="text-2xl font-bold text-white">{flaggedCount}</p>
            <p className="text-xs text-slate-400">Flagged</p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0); }}
            placeholder="Search plate, owner, make…"
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(0); }}
          className="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm text-slate-300 focus:outline-none focus:border-cyan-500">
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
          <option value="flagged">Flagged</option>
        </select>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-800/80">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Plate</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Vehicle</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Owner</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {loading ? (
                <tr><td colSpan={5} className="px-4 py-12 text-center"><Loader2 size={24} className="animate-spin text-cyan-400 mx-auto" /></td></tr>
              ) : vehicles.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-16 text-center">
                    <Car size={40} className="text-slate-600 mx-auto mb-3" />
                    <p className="text-slate-400 font-medium">No vehicles registered</p>
                    <p className="text-slate-500 text-xs mt-1">Register vehicles to enable ALPR matching at gates</p>
                  </td>
                </tr>
              ) : vehicles.map(v => (
                <tr key={v.id} className="hover:bg-slate-700/20 transition-colors group">
                  <td className="px-4 py-3">
                    <span className="font-mono font-bold text-white tracking-widest bg-slate-700 px-2.5 py-1 rounded text-sm">
                      {v.plate_number}
                    </span>
                    <p className="text-xs text-slate-500 mt-0.5 font-mono">{v.plate_normalized}</p>
                  </td>
                  <td className="px-4 py-3">
                    <p className="text-white font-medium">{[v.color, v.make, v.model].filter(Boolean).join(' ') || '—'}</p>
                    <p className="text-xs text-slate-400">{v.vehicle_type ?? ''}</p>
                  </td>
                  <td className="px-4 py-3">
                    <p className="text-white font-medium">{v.owner_name ?? '—'}</p>
                    {v.owner_person_id ? (
                      <span className="inline-flex items-center gap-1 text-[11px] text-cyan-400 font-mono mt-0.5 bg-cyan-400/10 px-2 py-0.5 rounded border border-cyan-400/20">
                        <User size={10} />
                        Mapped Member
                      </span>
                    ) : (
                      <span className="text-[11px] text-slate-500">Unlinked</span>
                    )}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={v.status} /></td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => setEditVehicle(v)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-blue-400 hover:bg-blue-400/10 transition-colors">
                        <Edit2 size={15} />
                      </button>
                      <button onClick={() => deleteVehicle(v.id)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-colors">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700">
            <p className="text-xs text-slate-400">Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}</p>
            <div className="flex items-center gap-2">
              <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                className="p-1 rounded text-slate-400 hover:text-white disabled:opacity-40"><ChevronLeft size={16} /></button>
              <span className="text-xs text-slate-400">Page {page + 1}/{totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                className="p-1 rounded text-slate-400 hover:text-white disabled:opacity-40"><ChevronRight size={16} /></button>
            </div>
          </div>
        )}
      </div>

      {showCreate && <VehicleFormModal onSave={createVehicle} onClose={() => setShowCreate(false)} />}
      {editVehicle && <VehicleFormModal initial={editVehicle} onSave={updateVehicle} onClose={() => setEditVehicle(null)} />}
    </div>
  );
}
