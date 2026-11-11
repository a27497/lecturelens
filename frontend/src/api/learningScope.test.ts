import { expect, it, vi } from 'vitest';
import { fetchScopeEvidence } from './learningScope';
import { http } from './http';
vi.mock('./http', () => ({ http: { get: vi.fn() } }));
vi.mock('./authToken', () => ({ authHeader: () => ({}) }));
it('does not enable new scope controls against a legacy Java gateway', async () => {
  vi.mocked(http.get).mockResolvedValue({ data: { data: { revision: 1, items: [], stale: false } } });
  await expect(fetchScopeEvidence('task')).rejects.toThrow('尚不支持');
});
