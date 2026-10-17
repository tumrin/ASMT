// Specimen (as served by the backend) -> Finnish display name (cultures.csv specimen_fi).
export const SPECIMEN_NAMES: Record<string, string> = {
	blood: 'Veri',
	urine: 'Virtsa',
	wound: 'Haava'
};

// Falls back to the specimen itself for specimens missing from the map.
export function specimenName(specimen: string): string {
	return SPECIMEN_NAMES[specimen] ?? specimen;
}
