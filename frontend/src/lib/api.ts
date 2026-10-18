// Shared GET helper for the backend API: on failure it surfaces the backend's
// detail message (FastAPI error body) instead of a generic fetch error.

export async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
	const response = await fetch(`/api${path}`, { signal });
	if (!response.ok) {
		const body = await response.json().catch(() => null);
		throw new Error(body?.detail ?? `HTTP ${response.status}`);
	}
	return (await response.json()) as T;
}
