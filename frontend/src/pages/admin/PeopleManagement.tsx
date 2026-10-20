// SmartGuard AI — People Management Page (Phase 2)
import { useState, useEffect, useCallback } from 'react';
import {
  Users, Plus, Search, Edit2,
  Trash2, ChevronLeft, ChevronRight, ScanFace, X,
  Upload, CheckCircle2, AlertCircle, Loader2, User,
  GraduationCap, Briefcase, HardHat,
} from 'lucide-react';
import { peopleApi, type CampusPerson } from '../../api/phase2';
import { getErrorMessage } from '../../api/client';

// ── Helpers ─────────────────────────────────────────────────────────────────

const TYPE_META: Record<string, { icon: React.ElementType; label: string; color: string }> = {
  staff:      { icon: Briefcase,   label: 'Staff',      color: 'text-blue-400 bg-blue-400/10' },
  student:    { icon: GraduationCap, label: 'Student',  color: 'text-purple-400 bg-purple-400/10' },
  visitor:    { icon: User,        label: 'Visitor',    color: 'text-amber-400 bg-amber-400/10' },
  contractor: { icon: HardHat,     label: 'Contractor', color: 'text-orange-400 bg-orange-400/10' },
};

const STATUS_META: Record<string, { label: string; color: string }> = {
  active:    { label: 'Active',    color: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20' },
  inactive:  { label: 'Inactive', color: 'text-slate-400 bg-slate-400/10 border-slate-400/20' },
  suspended: { label: 'Suspended', color: 'text-red-400 bg-red-400/10 border-red-400/20' },
};

function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_META[status] ?? STATUS_META.inactive;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${meta.color}`}>
      {meta.label}
    </span>
  );
}

function TypeBadge({ type }: { type: string }) {
  const meta = TYPE_META[type] ?? TYPE_META.staff;
  const Icon = meta.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium ${meta.color}`}>
      <Icon size={12} />
      {meta.label}
    </span>
  );
}

// ── Create / Edit Modal ──────────────────────────────────────────────────────

interface PersonFormProps {
  initial?: Partial<CampusPerson>;
  onSave: (data: Partial<CampusPerson>) => Promise<void>;
  onClose: () => void;
}

function PersonFormModal({ initial, onSave, onClose }: PersonFormProps) {
  const [form, setForm] = useState({
    full_name: initial?.full_name ?? '',
    person_type: initial?.person_type ?? 'staff',
    employee_id: initial?.employee_id ?? '',
    department: initial?.department ?? '',
    email: initial?.email ?? '',
    phone: initial?.phone ?? '',
    status: initial?.status ?? 'active',
    notes: initial?.notes ?? '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handle = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.full_name.trim()) { setError('Full name is required'); return; }
    setLoading(true); setError('');
    try {
      await onSave(form);
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
            {initial ? 'Edit Person' : 'Register Person'}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={submit} className="p-6 space-y-4">
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              <AlertCircle size={16} /> {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Full Name *</label>
              <input
                value={form.full_name} onChange={handle('full_name')} required
                placeholder="e.g. Arjun Krishnamurthy"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Type</label>
              <select value={form.person_type} onChange={handle('person_type')}
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm focus:outline-none focus:border-cyan-500">
                <option value="staff">Staff</option>
                <option value="student">Student</option>
                <option value="visitor">Visitor</option>
                <option value="contractor">Contractor</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Status</label>
              <select value={form.status} onChange={handle('status')}
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm focus:outline-none focus:border-cyan-500">
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="suspended">Suspended</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Employee / Student ID</label>
              <input value={form.employee_id} onChange={handle('employee_id')}
                placeholder="Optional"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500" />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Department</label>
              <input value={form.department} onChange={handle('department')}
                placeholder="Optional"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500" />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Email</label>
              <input type="email" value={form.email} onChange={handle('email')}
                placeholder="Optional"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500" />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Phone</label>
              <input value={form.phone} onChange={handle('phone')}
                placeholder="Optional"
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500" />
            </div>

            <div className="col-span-2">
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Notes</label>
              <textarea value={form.notes} onChange={handle('notes')} rows={2}
                placeholder="Optional notes..."
                className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-cyan-500 resize-none" />
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors">
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

// ── Face Enroll Modal ────────────────────────────────────────────────────────

function FaceEnrollModal({ person, onClose }: { person: CampusPerson; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string; faces?: number } | null>(null);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
  };

  const enroll = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const res = await peopleApi.enrollFace(person.id, file);
      setResult({ success: true, message: `Face enrolled. Profile ID: ${res.data.profile_id}`, faces: res.data.faces_detected });
    } catch (err) {
      setResult({ success: false, message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-slate-800/50">
          <div>
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <ScanFace size={20} className="text-cyan-400" /> Enroll Face
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">{person.full_name}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X size={20} /></button>
        </div>

        <div className="p-6 space-y-4">
          {/* Upload area */}
          <label className="block w-full cursor-pointer">
            <div className={`relative rounded-xl border-2 border-dashed transition-colors overflow-hidden
              ${preview ? 'border-cyan-500/50' : 'border-slate-600 hover:border-slate-500'}`}
              style={{ minHeight: '180px' }}>
              {preview ? (
                <img src={preview} alt="Preview" className="w-full object-cover max-h-56" />
              ) : (
                <div className="flex flex-col items-center justify-center py-12 gap-3">
                  <div className="p-3 rounded-xl bg-slate-800 text-slate-400">
                    <Upload size={28} />
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-slate-300 font-medium">Click to upload face image</p>
                    <p className="text-xs text-slate-500 mt-1">JPEG, PNG, WebP — max 10 MB</p>
                  </div>
                </div>
              )}
            </div>
            <input type="file" className="sr-only" accept="image/jpeg,image/png,image/webp" onChange={handleFile} />
          </label>

          {result && (
            <div className={`flex items-start gap-2 p-3 rounded-lg text-sm border ${
              result.success
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                : 'bg-red-500/10 border-red-500/20 text-red-400'
            }`}>
              {result.success ? <CheckCircle2 size={16} className="mt-0.5 shrink-0" /> : <AlertCircle size={16} className="mt-0.5 shrink-0" />}
              <span>{result.message}</span>
            </div>
          )}

          <div className="flex gap-3">
            <button onClick={onClose} className="flex-1 py-2 text-sm text-slate-400 hover:text-white transition-colors">
              {result?.success ? 'Close' : 'Cancel'}
            </button>
            {!result?.success && (
              <button onClick={enroll} disabled={!file || loading}
                className="flex-1 flex items-center justify-center gap-2 py-2 bg-cyan-500 hover:bg-cyan-400 text-slate-900 font-semibold rounded-lg text-sm transition-colors disabled:opacity-40">
                {loading ? <Loader2 size={14} className="animate-spin" /> : <ScanFace size={14} />}
                {loading ? 'Processing...' : 'Enroll Face'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function PeopleManagement() {
  const [people, setPeople] = useState<CampusPerson[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  const [showCreate, setShowCreate] = useState(false);
  const [editPerson, setEditPerson] = useState<CampusPerson | null>(null);
  const [enrollPerson, setEnrollPerson] = useState<CampusPerson | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await peopleApi.list({
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        search: search || undefined,
        person_type: typeFilter || undefined,
        status: statusFilter || undefined,
      });
      setPeople(res.data.items);
      setTotal(res.data.total);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, search, typeFilter, statusFilter]);

  useEffect(() => { load(); }, [load]);

  const createPerson = async (data: Partial<CampusPerson>) => {
    await peopleApi.create(data as Parameters<typeof peopleApi.create>[0]);
    setShowCreate(false);
    load();
  };

  const updatePerson = async (data: Partial<CampusPerson>) => {
    if (!editPerson) return;
    await peopleApi.update(editPerson.id, data);
    setEditPerson(null);
    load();
  };

  const deletePerson = async (id: string) => {
    if (!confirm('Delete this person and all associated face profiles?')) return;
    try {
      await peopleApi.delete(id);
      load();
    } catch (err) {
      alert(getErrorMessage(err));
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="flex flex-col gap-6 p-6 min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400">
              <Users size={24} />
            </div>
            People Management
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Register and manage campus personnel, students, visitors, and contractors
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-cyan-500 hover:bg-cyan-400 text-slate-900 font-semibold rounded-xl text-sm transition-all hover:shadow-lg hover:shadow-cyan-500/20"
        >
          <Plus size={16} /> Register Person
        </button>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-4 gap-4">
        {Object.entries(TYPE_META).map(([type, meta]) => {
          const Icon = meta.icon;
          const count = people.filter(p => p.person_type === type).length;
          return (
            <div key={type} className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
              <div className={`p-2 rounded-lg ${meta.color}`}><Icon size={18} /></div>
              <div>
                <p className="text-2xl font-bold text-white">{count}</p>
                <p className="text-xs text-slate-400">{meta.label}s</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0); }}
            placeholder="Search name, ID, email…"
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
          />
        </div>
        <select value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(0); }}
          className="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm text-slate-300 focus:outline-none focus:border-cyan-500">
          <option value="">All Types</option>
          <option value="staff">Staff</option>
          <option value="student">Student</option>
          <option value="visitor">Visitor</option>
          <option value="contractor">Contractor</option>
        </select>
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(0); }}
          className="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm text-slate-300 focus:outline-none focus:border-cyan-500">
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
          <option value="suspended">Suspended</option>
        </select>
      </div>

      {/* Error */}
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
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Person</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Type</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Department</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Faces</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-400 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center">
                    <Loader2 size={24} className="animate-spin text-cyan-400 mx-auto" />
                  </td>
                </tr>
              ) : people.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-16 text-center">
                    <Users size={40} className="text-slate-600 mx-auto mb-3" />
                    <p className="text-slate-400 font-medium">No people found</p>
                    <p className="text-slate-500 text-xs mt-1">Register the first person to get started</p>
                  </td>
                </tr>
              ) : (
                people.map(person => (
                  <tr key={person.id} className="hover:bg-slate-700/20 transition-colors group">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border border-slate-600 flex items-center justify-center text-cyan-400 text-xs font-bold flex-shrink-0">
                          {person.full_name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-medium text-white">{person.full_name}</p>
                          <p className="text-xs text-slate-400">{person.employee_id ?? person.email ?? '—'}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3"><TypeBadge type={person.person_type} /></td>
                    <td className="px-4 py-3 text-slate-300">{person.department ?? '—'}</td>
                    <td className="px-4 py-3"><StatusBadge status={person.status} /></td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${
                        person.face_profile_count > 0
                          ? 'bg-cyan-400/10 text-cyan-400'
                          : 'bg-slate-700 text-slate-400'
                      }`}>
                        <ScanFace size={11} /> {person.face_profile_count}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => setEnrollPerson(person)}
                          title="Enroll Face"
                          className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-cyan-400/10 transition-colors">
                          <ScanFace size={15} />
                        </button>
                        <button
                          onClick={() => setEditPerson(person)}
                          title="Edit"
                          className="p-1.5 rounded-lg text-slate-400 hover:text-blue-400 hover:bg-blue-400/10 transition-colors">
                          <Edit2 size={15} />
                        </button>
                        <button
                          onClick={() => deletePerson(person.id)}
                          title="Delete"
                          className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-400/10 transition-colors">
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700">
            <p className="text-xs text-slate-400">
              Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="p-1 rounded text-slate-400 hover:text-white disabled:opacity-40 transition-colors">
                <ChevronLeft size={16} />
              </button>
              <span className="text-xs text-slate-400">Page {page + 1}/{totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="p-1 rounded text-slate-400 hover:text-white disabled:opacity-40 transition-colors">
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modals */}
      {showCreate && (
        <PersonFormModal onSave={createPerson} onClose={() => setShowCreate(false)} />
      )}
      {editPerson && (
        <PersonFormModal initial={editPerson} onSave={updatePerson} onClose={() => setEditPerson(null)} />
      )}
      {enrollPerson && (
        <FaceEnrollModal person={enrollPerson} onClose={() => { setEnrollPerson(null); load(); }} />
      )}
    </div>
  );
}
