// Response shape of GET /metadata (server/src/resistance/api/responses.py).

import { fetchJson } from './api.js';

export interface ScopeUnit {
	unit: string;
	label: string;
}

export interface Metadata {
	scopes: Record<string, ScopeUnit[]>;
	periods: string[];
	data_as_of: string | null;
}

export function fetchMetadata(signal?: AbortSignal): Promise<Metadata> {
	return fetchJson<Metadata>('/metadata', signal);
}
