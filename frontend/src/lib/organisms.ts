// Normalized organism id (as served by the backend) -> display name.
export const ORGANISM_NAMES: Record<string, string> = {
	citrobacter_freundii: 'Citrobacter freundii',
	enterococcus_faecalis: 'Enterococcus faecalis',
	escherichia_coli: 'Escherichia coli',
	klebsiella_oxytoca: 'Klebsiella oxytoca',
	klebsiella_pneumoniae: 'Klebsiella pneumoniae',
	proteus_mirabilis: 'Proteus mirabilis',
	pseudomonas_aeruginosa: 'Pseudomonas aeruginosa',
	staphylococcus_aureus: 'Staphylococcus aureus',
	staphylococcus_saprophyticus: 'Staphylococcus saprophyticus'
};

// Falls back to the id itself for organisms missing from the map.
export function organismName(id: string): string {
	return ORGANISM_NAMES[id] ?? id;
}
