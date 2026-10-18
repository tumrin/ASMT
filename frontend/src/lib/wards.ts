// Inpatient ward code (as served by the backend) -> Finnish display name (wards.csv ward_fi).
// Outpatient units (ward_type = out) are not wards in the antibiogram model; they are
// served through the region scope by the patient's home_area (spec.md §6.2).
export const WARD_NAMES: Record<string, string> = {
	'MED-A': 'Sisätaudit A',
	'MED-B': 'Sisätaudit B',
	SURG: 'Kirurgia',
	URO: 'Urologia',
	ICU: 'Teho-osasto',
	GER: 'Geriatria'
};

// Falls back to the code itself for wards missing from the map.
export function wardName(code: string): string {
	return WARD_NAMES[code] ?? code;
}
