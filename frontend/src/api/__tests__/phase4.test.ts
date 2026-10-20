// SmartGuard AI — Phase 4 Frontend API Client Unit Tests
import { describe, it, expect, vi, beforeEach } from 'vitest';
import apiClient from '../client';
import alertsApi from '../alerts';
import reportsApi from '../reports';
import contactsApi from '../contacts';
import notificationsApi from '../notifications';

describe('Phase 4 Frontend API Clients', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('alertsApi', () => {
    it('fetches alert metrics', async () => {
      const mockMetrics = {
        open: 3,
        acknowledged: 1,
        investigating: 2,
        resolved: 10,
        dismissed: 1,
        critical_high_unresolved: 2,
        total_unresolved: 6,
      };
      vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockMetrics });

      const res = await alertsApi.getMetrics();
      expect(apiClient.get).toHaveBeenCalledWith('/alerts/metrics');
      expect(res.open).toBe(3);
    });

    it('acknowledges an alert with optional reason', async () => {
      const mockDetail = { id: 'alert-1', status: 'ACKNOWLEDGED' };
      vi.spyOn(apiClient, 'post').mockResolvedValueOnce({ data: mockDetail });

      const res = await alertsApi.acknowledgeAlert('alert-1', 'Checked by officer');
      expect(apiClient.post).toHaveBeenCalledWith('/alerts/alert-1/acknowledge', { reason: 'Checked by officer' });
      expect(res.status).toBe('ACKNOWLEDGED');
    });

    it('resolves an alert with reason', async () => {
      const mockDetail = { id: 'alert-2', status: 'RESOLVED', resolution_reason: 'Vehicle allowed with guest pass' };
      vi.spyOn(apiClient, 'post').mockResolvedValueOnce({ data: mockDetail });

      const res = await alertsApi.resolveAlert('alert-2', 'Vehicle allowed with guest pass');
      expect(apiClient.post).toHaveBeenCalledWith('/alerts/alert-2/resolve', { reason: 'Vehicle allowed with guest pass' });
      expect(res.status).toBe('RESOLVED');
    });
  });

  describe('reportsApi', () => {
    it('fetches filtered access reports', async () => {
      const mockReport = {
        items: [{ id: 'att-1', direction: 'ENTRY', decision: 'ALLOW' }],
        total: 1,
        skip: 0,
        limit: 50,
      };
      vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockReport });

      const res = await reportsApi.listAccessReport({ decision: 'ALLOW', limit: 50 });
      expect(apiClient.get).toHaveBeenCalledWith('/reports/access', { params: { decision: 'ALLOW', limit: 50 } });
      expect(res.items.length).toBe(1);
    });

    it('fetches daily summary', async () => {
      const mockSummary = { date: '2026-10-15', total: 120, allowed: 110, denied: 10 };
      vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockSummary });

      const res = await reportsApi.getDailySummary('2026-10-15');
      expect(apiClient.get).toHaveBeenCalledWith('/reports/daily-summary', { params: { date: '2026-10-15' } });
      expect(res.total).toBe(120);
    });
  });

  describe('contactsApi', () => {
    it('lists security contacts', async () => {
      const mockContacts = [{ id: 'contact-1', full_name: 'Lead Officer', email: 'chief@campus.edu' }];
      vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockContacts });

      const res = await contactsApi.listContacts('chief');
      expect(apiClient.get).toHaveBeenCalledWith('/admin/security-contacts', { params: { search: 'chief', is_active: undefined } });
      expect(res.length).toBe(1);
    });

    it('sends test email to contact', async () => {
      vi.spyOn(apiClient, 'post').mockResolvedValueOnce({ data: { message: 'Test email sent.' } });

      const res = await contactsApi.sendTestEmail('contact-1');
      expect(apiClient.post).toHaveBeenCalledWith('/admin/security-contacts/contact-1/test-email');
      expect(res.message).toBe('Test email sent.');
    });
  });

  describe('notificationsApi', () => {
    it('retries a specific failed notification', async () => {
      const mockNotif = { id: 'notif-1', status: 'RETRY_SCHEDULED' };
      vi.spyOn(apiClient, 'post').mockResolvedValueOnce({ data: mockNotif });

      const res = await notificationsApi.retryNotification('notif-1');
      expect(apiClient.post).toHaveBeenCalledWith('/admin/notifications/notif-1/retry');
      expect(res.status).toBe('RETRY_SCHEDULED');
    });

    it('retries all failed notifications', async () => {
      vi.spyOn(apiClient, 'post').mockResolvedValueOnce({ data: { rescheduled: 4 } });

      const res = await notificationsApi.retryAllFailed();
      expect(apiClient.post).toHaveBeenCalledWith('/admin/notifications/retry-all');
      expect(res.rescheduled).toBe(4);
    });
  });
});
