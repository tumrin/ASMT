# Synteettinen mikrobiologia-aineisto / Synthetic microbiology dataset

> **Kaikki tiedot ovat keksittyjä.** Potilaat, näytteet ja tulokset on tuotettu
> tietokoneella sääntöjen ja todennäköisyyksien perusteella. Ne eivät kuvaa mitään
> todellista sairaalaa tai potilasta.
>
> **All data is synthetic.** Patients, samples and results were generated from rules
> and probabilities. They do not describe any real hospital or patient.

## Suomeksi

**Sisältö:** 10 000 potilasta, 46 792 viljelynäytettä, 24 571
isolaattia ja 172 381 herkkyysmääritystä aikavälillä 02.10.2023–27.09.2026
(156 viikkoa).

### Rakenne

Näyte (viljely) → 0–2 isolaattia (löydettyä mikrobia) → herkkyysmääritykset.

| Tiedosto | Sisältö |
|---|---|
| `cultures.csv` | viljelynäyte: päivä, ISO-viikko, ikä, osasto, avo/osasto, sisäänottopäivä, näytetyyppi, tulos (positive / negative / mixed_growth) |
| `isolates.csv` | löydetty mikrobi: määrä (virtsa CFU/ml, haava +…+++), ilmiasut ESBL / MRSA / VRE / CPE (0/1) |
| `susceptibility.csv` | herkkyys isolaateittain: antibiootti, WHONET-koodi, tulos S / R, tulkintaohje (EUCAST + vuosi) |
| `patients.csv` | potilas: sukupuoli, syntymävuosi, asuinalue |
| `antibiotics.csv`, `wards.csv` | koodistot |

Avaimet: `patient_id`, `culture_id`, `isolate_id`. CSV on standardimuotoinen
(pilkkuerotin, UTF-8, ISO-päivämäärät). Suomenkielinen Excel: Tiedot → Tekstistä/CSV:stä.

### Resistenssiprosenttien laskeminen

Resistenssiseurannassa (esim. THL:n Finres, WHO GLASS, CLSI M39) lasketaan yleensä
**vain potilaan ensimmäinen isolaatti** samaa lajia samasta näytetyypistä jakson aikana,
ja prosentti näytetään vasta kun isolaatteja on **vähintään 30**. Aineistossa sama potilas
voi esiintyä useasti. Virtsan E. colin resistenssi eroaa naisten ja miesten välillä.
Sairaalasyntyiseksi luetaan usein löydös, jonka näyte on otettu aikaisintaan 3.
hoitopäivänä (`admission_date`).

### Mihin aineisto perustuu

- Virtsan ja veren E. colin resistenssi, ESBL- ja MRSA-osuudet on kalibroitu karkeasti
  THL:n Finres 2023 -raportin tasoille. Muiden mikrobien tasot ja mikrobien osuudet
  ovat havainnollistavia arvioita.
- Luontaiset resistenssit noudattavat EUCASTin Expected Resistant Phenotypes v1.2 -listaa
  (esim. Proteus mirabilis – nitrofurantoiini, Klebsiella – ampisilliini).
- Rakenne seuraa resistenssiseurannan käytäntöjä (WHONET, ECDC EARS-Net): isolaattitaso,
  erilliset ilmiasut, avo/osasto, tulkintaohje.

### Yksinkertaistukset

- Herkkyys vain S / R. I-luokkaa (EUCAST 2019→: "herkkä, suurennettu annostus") sekä
  MIC- ja estovyöhykearvoja ei ole. Finres raportoi pääosin resistenttien osuuden.
- Virtsa-antibiootit (mesillinaami, trimetopriimi, nitrofurantoiini) raportoidaan vain
  virtsanäytteistä. Luontaisesti resistenttejä pareja, joita ei yleensä raportoida, ei ole mukana.
- Mikrobit ovat latinankielisinä niminä (todellisissa poiminnoissa usein WHONET-koodeina).
- Diagnoosit, lääkitys ja kliiniset tiedot puuttuvat.

## In English

**Contents:** 10,000 patients, 46,792 cultures, 24,571 isolates and
172,381 susceptibility results, 2023-10-02 to 2026-09-27 (156 weeks).

**Structure:** culture → 0–2 isolates → susceptibility results. Keys `patient_id`,
`culture_id`, `isolate_id`. Standard CSV (comma, UTF-8, ISO dates).

**Computing resistance rates:** surveillance programmes usually count only the **first
isolate per patient per species per specimen type per period** and report a percentage only
with **at least 30 isolates**. Urinary E. coli resistance differs between women and men.

**Basis:** urinary and blood E. coli resistance, ESBL and MRSA shares are roughly calibrated
to the Finnish Finres 2023 report (THL); intrinsic resistances follow EUCAST Expected Resistant
Phenotypes v1.2; other rates are illustrative. **Simplifications:** S/R only (no I, MIC or
zone diameters); urinary agents reported for urine only; organisms as Latin names; no
diagnoses or medication.

## Sarakkeet / Columns

`cultures.csv`: culture_id, patient_id, age_years, sample_date, iso_year, iso_week, ward_code,
ward_fi, ward_en, ward_type (in/out), institution (hospital/primary_care), admission_date
(inpatients), specimen (urine/blood/wound), specimen_fi, result (positive/negative/mixed_growth),
n_isolates

`isolates.csv`: isolate_id, culture_id, isolate_no, organism, quantity, esbl, mrsa, vre, cpe

`susceptibility.csv`: isolate_id, culture_id, organism, antibiotic, antibiotic_code,
antibiotic_fi, result (S/R), guideline

`patients.csv`: patient_id, sex (F/M), birth_year, home_area

### Osastot / Wards

| Koodi / Code | Suomeksi | English | Avo/osasto (in/out) | Laitos / Institution |
|---|---|---|---|---|
| ED | Päivystys | Emergency department | out | hospital |
| MED-A | Sisätaudit A | Internal medicine A | in | hospital |
| MED-B | Sisätaudit B | Internal medicine B | in | hospital |
| SURG | Kirurgia | Surgery | in | hospital |
| URO | Urologia | Urology | in | hospital |
| ICU | Teho-osasto | Intensive care unit | in | hospital |
| GER | Geriatria | Geriatrics | in | hospital |
| PHC-N | Terveysasema Pohjoinen | Health centre North | out | primary_care |
| PHC-S | Terveysasema Etelä | Health centre South | out | primary_care |

### Antibiootit / Antibiotics

| Antibiotic | WHONET | Suomeksi | Ryhmä / Class | Raportoidaan / Reported for |
|---|---|---|---|---|
| ampicillin | AMP | ampisilliini | penicillins | kaikki / all |
| mecillinam | MEC | mesillinaami | penicillins | virtsa / urine |
| piperacillin-tazobactam | TZP | piperasilliini-tatsobaktaami | penicillins + BLI | kaikki / all |
| cefoxitin (screen) | FOX | kefoksitiini (seulonta) | MRSA screen | kaikki / all |
| cefuroxime | CXM | kefuroksiimi | cephalosporins 2nd gen | kaikki / all |
| ceftriaxone | CRO | keftriaksoni | cephalosporins 3rd gen | kaikki / all |
| ceftazidime | CAZ | keftatsidiimi | cephalosporins 3rd gen | kaikki / all |
| meropenem | MEM | meropeneemi | carbapenems | kaikki / all |
| ciprofloxacin | CIP | siprofloksasiini | fluoroquinolones | kaikki / all |
| trimethoprim | TMP | trimetopriimi | trimethoprim | virtsa / urine |
| nitrofurantoin | NIT | nitrofurantoiini | nitrofurans | virtsa / urine |
| vancomycin | VAN | vankomysiini | glycopeptides | kaikki / all |
| clindamycin | CLI | klindamysiini | lincosamides | kaikki / all |

## Lähteet / Sources

- THL, Finres 2023 – Bakteerien mikrobilääkeresistenssi Suomessa
- EUCAST Expected Resistant Phenotypes v1.2 (2023)
- ECDC, EARS-Net reporting protocol; WHO GLASS manual

Aineisto tuotettu toistettavasti (siemenluku 2026). / Generated reproducibly (seed 2026).
