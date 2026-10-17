// Ward code (as served by the backend) -> Finnish display name (wards.csv ward_fi).
export const WARD_NAMES: Record<string, string> = {
	ED: 'Päivystys',
	'MED-A': 'Sisätaudit A',
	'MED-B': 'Sisätaudit B',
	SURG: 'Kirurgia',
	URO: 'Urologia',
	ICU: 'Teho-osasto',
	GER: 'Geriatria',
	'PHC-N': 'Terveysasema Pohjoinen',
	'PHC-S': 'Terveysasema Etelä'
};

// Falls back to the code itself for wards missing from the map.
export function wardName(code: string): string {
	return WARD_NAMES[code] ?? code;
}
