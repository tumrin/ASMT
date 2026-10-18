// Mock patient documents for the patient view. The shapes mirror what the backend
// serves from GET /patients, GET /patients/{id}/wards/{ward} and
// GET /patients/{id}/history (server/README.md), so the view can be wired to the
// API later without changing its types.

export interface PatientSummary {
	patient_id: string;
	sex: string;
	birth_year: number;
	home_area: string;
	wards: string[];
}

export interface WardIsolate {
	isolate_id: string;
	isolate_no: number;
	organism: string;
	quantity: string | null;
	flags: {
		esbl: number;
		mrsa: number;
		vre: number;
		cpe: number;
	};
	susceptibility: Record<string, string>;
}

export interface WardCulture {
	culture_id: string;
	sample_date: string;
	iso_year: number;
	iso_week: number;
	age_years: number;
	specimen: string;
	result: string;
	n_isolates: number;
	days_since_admission: number | null;
	isolates: WardIsolate[];
}

export interface WardDetail {
	ward_code: string;
	ward_fi: string | null;
	ward_en: string | null;
	ward_type: string | null;
	institution: string | null;
	cultures: WardCulture[];
}

export interface HistoryEntry {
	isolate_id: string;
	culture_id: string;
	organism: string;
	specimen: string;
	ward_code: string | null;
	sample_date: string | null;
	days_ago: number | null;
	flags: {
		esbl: number;
		mrsa: number;
		vre: number;
		cpe: number;
	};
	susceptibility: Record<string, string>;
}

interface MockPatient {
	summary: PatientSummary;
	ward: WardDetail;
}

function mockCulture(
	cultureId: string,
	sampleDate: string,
	specimen: string,
	organism: string,
	susceptibility: Record<string, string>,
	flags = { esbl: 0, mrsa: 0, vre: 0, cpe: 0 }
): WardCulture {
	const date = new Date(`${sampleDate}T00:00:00`);
	return {
		culture_id: cultureId,
		sample_date: sampleDate,
		iso_year: date.getFullYear(),
		iso_week: 1,
		age_years: 45,
		specimen,
		result: 'Positive',
		n_isolates: 1,
		days_since_admission: 2,
		isolates: [
			{
				isolate_id: `MOCK-${cultureId}`,
				isolate_no: 1,
				organism,
				quantity: 'moderate',
				flags,
				susceptibility
			}
		]
	};
}

function mockPatient(
	patient_id: string,
	sex: string,
	birth_year: number,
	home_area: string,
	ward_code: string,
	ward_en: string,
	cultures: WardCulture[]
): MockPatient {
	return {
		summary: { patient_id, sex, birth_year, home_area, wards: [ward_code] },
		ward: {
			ward_code,
			ward_fi: ward_en,
			ward_en,
			ward_type: 'in',
			institution: 'Demo Hospital',
			cultures
		}
	};
}

export const MOCK_PATIENTS: MockPatient[] = [
	mockPatient('MOCK-001', 'F', 1984, 'North', 'MED-A', 'Internal medicine A', [
		mockCulture('CULTURE-001', '2026-09-24', 'urine', 'escherichia_coli', {
			AMP: 'R',
			CIP: 'S',
			MEC: 'S',
			NIT: 'S',
			TMP: 'R'
		}),
		mockCulture('CULTURE-002', '2026-08-19', 'urine', 'escherichia_coli', {
			AMP: 'R',
			CIP: 'S',
			MEC: 'S',
			NIT: 'S',
			TMP: 'S'
		})
	]),
	mockPatient('MOCK-002', 'M', 1971, 'West', 'SURG', 'Surgery', [
		mockCulture(
			'CULTURE-003',
			'2026-09-21',
			'wound',
			'staphylococcus_aureus',
			{
				CIP: 'S',
				CLI: 'R',
				FOX: 'S',
				VAN: 'S'
			},
			{ esbl: 0, mrsa: 0, vre: 0, cpe: 0 }
		)
	]),
	mockPatient('MOCK-003', 'F', 1996, 'Centre', 'URO', 'Urology', [
		mockCulture('CULTURE-004', '2026-09-18', 'urine', 'enterococcus_faecalis', {
			AMP: 'S',
			CIP: 'R',
			NIT: 'S',
			VAN: 'S'
		})
	]),
	mockPatient('MOCK-004', 'M', 1955, 'East', 'ICU', 'Intensive care unit', [
		mockCulture(
			'CULTURE-005',
			'2026-09-25',
			'blood',
			'klebsiella_pneumoniae',
			{
				CRO: 'R',
				MEM: 'S',
				TZP: 'R'
			},
			{ esbl: 1, mrsa: 0, vre: 0, cpe: 0 }
		)
	]),
	mockPatient('MOCK-005', 'F', 1947, 'South', 'GER', 'Geriatrics', [
		mockCulture('CULTURE-006', '2026-09-12', 'urine', 'proteus_mirabilis', {
			AMP: 'S',
			CIP: 'S',
			MEC: 'S',
			NIT: 'R',
			TMP: 'S'
		})
	])
];

export function findMockPatient(patientId: string): MockPatient | undefined {
	return MOCK_PATIENTS.find(({ summary }) => summary.patient_id === patientId);
}

// The history the backend would serve from GET /patients/{id}/history, flattened
// from the ward's cultures.
export function mockHistory(ward: WardDetail): HistoryEntry[] {
	return ward.cultures.flatMap((culture) =>
		culture.isolates.map((isolate) => ({
			isolate_id: isolate.isolate_id,
			culture_id: culture.culture_id,
			organism: isolate.organism,
			specimen: culture.specimen,
			ward_code: ward.ward_code,
			sample_date: culture.sample_date,
			days_ago: null,
			flags: isolate.flags,
			susceptibility: isolate.susceptibility
		}))
	);
}
