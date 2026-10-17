// Antibiotic code (as served by the backend) -> Finnish display name (antibiotics.csv antibiotic_fi).
export const ANTIBIOTIC_NAMES: Record<string, string> = {
	AMP: 'ampisilliini',
	MEC: 'mesillinaami',
	TZP: 'piperasilliini-tatsobaktaami',
	FOX: 'kefoksitiini (seulonta)',
	CXM: 'kefuroksiimi',
	CRO: 'keftriaksoni',
	CAZ: 'keftatsidiimi',
	MEM: 'meropeneemi',
	CIP: 'siprofloksasiini',
	TMP: 'trimetopriimi',
	NIT: 'nitrofurantoiini',
	VAN: 'vankomysiini',
	CLI: 'klindamysiini'
};

// Falls back to the code itself for antibiotics missing from the map.
export function antibioticName(code: string): string {
	return ANTIBIOTIC_NAMES[code] ?? code;
}
