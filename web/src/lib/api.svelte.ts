import { goto } from '$app/navigation';

export const auth = $state({ user: null as string | null, mode: 'password', checked: false });

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
	const headers = new Headers(init.headers);
	if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
	const res = await fetch(`/api${path}`, { credentials: 'same-origin', ...init, headers });
	if (res.status === 401 && !path.startsWith('/auth')) {
		auth.user = null;
		goto('/');
		throw new Error('Not logged in');
	}
	const data = res.headers.get('content-type')?.includes('json') ? await res.json() : await res.text();
	if (!res.ok) throw new Error((data as any)?.detail ?? res.statusText);
	return data as T;
}

export const post = <T = any>(path: string, body?: unknown) =>
	api<T>(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) });
export const patch = <T = any>(path: string, body: unknown) => api<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
export const del = <T = any>(path: string) => api<T>(path, { method: 'DELETE' });
