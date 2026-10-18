// Response shape of GET /recommendations (server/src/resistance/api/responses.py).

import { fetchJson } from './api.js';

export interface RecommendationOption {
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
	traffic_light: string;
	source_scope: string;
	source_unit: string;
	source_period: string;
}

export interface RecommendationExcluded {
	antibiotic: string;
	antibiotic_code: string;
	reason: string;
	detail: string;
}

export interface RecommendationResponse {
	scope: string;
	unit: string;
	organism: string;
	specimen: string;
	data_as_of: string | null;
	options: RecommendationOption[];
	excluded: RecommendationExcluded[];
	limitations: string[];
}

export interface RecommendationFilters {
	scope: string;
	unit: string;
	organism: string;
	specimen: string;
	period: string;
}

export async function fetchRecommendations(
	filters: RecommendationFilters,
	signal?: AbortSignal
): Promise<RecommendationResponse> {
	const params = new URLSearchParams({
		scope: filters.scope,
		unit: filters.unit,
		organism: filters.organism,
		specimen: filters.specimen,
		period: filters.period
	});
	return fetchJson<RecommendationResponse>(`/recommendations?${params}`, signal);
}
