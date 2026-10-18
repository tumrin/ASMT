// Response shape of GET /metadata (server/src/resistance/api/responses.py).

export interface ScopeUnit {
	unit: string;
	label: string;
}

export interface Metadata {
	scopes: Record<string, ScopeUnit[]>;
	periods: string[];
	data_as_of: string | null;
}

export async function fetchMetadata(signal?: AbortSignal): Promise<Metadata> {
	const response = await fetch('/api/metadata', { signal });
	if (!response.ok) {
		const body = await response.json().catch(() => null);
		throw new Error(body?.detail ?? `HTTP ${response.status}`);
	}
	return response.json();
}
