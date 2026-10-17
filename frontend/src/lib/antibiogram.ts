// Response shape of GET /antibiogram (server/packages/api/src/resistance_api/responses.py).

export type TrafficLight = 'green' | 'yellow' | 'red' | 'none';

export interface AntibioticCell {
	antibiotic: string;
	antibiotic_code: string;
	class: string;
	reported_for: string;
	role: string;
	n: number;
	n_s: number;
	susceptibility_rate: number | null;
	ci_low: number | null;
	ci_high: number | null;
	traffic_light: TrafficLight;
}

export interface AntibiogramRow {
	organism: string;
	specimen: string;
	antibiotics: AntibioticCell[];
}

export interface AntibiogramResponse {
	scope: string;
	unit: string;
	period: string;
	data_as_of: string | null;
	organisms: AntibiogramRow[];
}

export interface AntibiogramFilters {
	unit: string;
	period: string;
	organism: string;
	specimen: string;
}

export async function fetchAntibiogram(
	filters: AntibiogramFilters,
	signal?: AbortSignal
): Promise<AntibiogramResponse> {
	const params = new URLSearchParams({
		scope: filters.unit === '-' ? 'hospital' : 'ward',
		unit: filters.unit
	});
	if (filters.period) params.set('period', filters.period);
	if (filters.organism) params.set('organism', filters.organism);
	if (filters.specimen) params.set('specimen', filters.specimen);

	const response = await fetch(`/api/antibiogram?${params}`, { signal });
	if (!response.ok) {
		const body = await response.json().catch(() => null);
		throw new Error(body?.detail ?? `HTTP ${response.status}`);
	}
	return response.json();
}
