// Response shape of GET /antibiogram (server/src/resistance/api/responses.py).

import { fetchJson } from './api.js';
import type { TrafficLight } from './trafficlight.js';

export interface AntibioticCell {
	antibiotic: string;
	antibiotic_code: string;
	class: string;
	reported_for: string;
	role: string;
	n: number;
	n_s: number;
	susceptibility_rate: number | null;
	traffic_light: TrafficLight;
}

// A cell is reportable only when it has a rate and a traffic light: a missing cell, a
// rate below the reporting floor or a non-reportable cell all count as "no result".
export function hasReportableRate(cell: AntibioticCell | undefined): boolean {
	return cell !== undefined && cell.susceptibility_rate !== null && cell.traffic_light !== 'none';
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
	scope: string;
	unit: string;
	period: string;
	organism: string;
	specimen: string;
}

export async function fetchAntibiogram(
	filters: AntibiogramFilters,
	signal?: AbortSignal
): Promise<AntibiogramResponse> {
	const params = new URLSearchParams({ scope: filters.scope, unit: filters.unit });
	if (filters.period) params.set('period', filters.period);
	if (filters.organism) params.set('organism', filters.organism);
	if (filters.specimen) params.set('specimen', filters.specimen);
	return fetchJson<AntibiogramResponse>(`/antibiogram?${params}`, signal);
}
