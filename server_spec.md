# 

# Cumulative antibiogram application

*Summary of the idea here*  
  
Simple web application that calculates resistance rate of certain antibiotics and produces constantly updating antibiogram.

## Raw data sources

Only data source we are allowed to use are following:

- antibiotics.csv
- cultures.csv
- isolates.csv
- patients.csv
- susceptibility.csv
- wards.csv

Data shouldn’t be enriched in any possible way. Data can be aggregated, filtered and combined with each other but any additional raw data outside of these .csv files isn’t allowed to be used.

## Technology stack to be used

### Backend

- Python
  - Fastapi, uvicorn for API
  - Polars, Scipy for data-analysis
- Tooling
  - Ruff for linting
  - Ty for type checking
  - Uv for project management

### Frontend

React, Vite, Typescript

## End user groups

Application consists two end user groups:

- Doctor
- Nurse

## Functional requirements

- Application has an antibiogram view for the hospital
- Application has an antibiogram view for specific ward inside the hospital
- Antibiogram view shows both annual and monthly results
- A doctor wants to see up-to-date information on the susceptibility profile of bacteria in their own ward
- Application should calculate resistance rate of antibiotic per microbe
  - **Computing resistance rates:** count the **first isolate per patient per species per specimen type per period** and report a percentage only with **at least 30 isolates**.
- Application should produce matrix of antibiotic and microbe based on the susceptibility rate. Susceptibility meaning how effective the antibiotic is against the microbe.
- Application should have a patient view that lists all in-type patients. From this list view, user should be able to select individual patient.
  - Individual patient view shows basic information about the patient and recommend antibiotics basic on what microbe infection patient has and the susceptibility rates for that microbe.
- User should be able to produce PDF reports from patient level and general hospital/ward level views.

## Non-functional requirements

1. Antibiogram view for hospitals and wards can be implemented with a filterable table that displays resistance percentages for the hospital, all or a chose ward in it, for a specific organism and either for a monthly timescale or annually. Resistance percentage calculations should be done in the backend based on the data provided and is then sent to the frontend where the table is assembled based on selected filters. The table should display good, okay and bad antibiotic options for a given organism with a traffic light system, green for an antibiotic that works well, red for badly and yellow for medium.
2. The backend should calculate resistance percentages for each organism present in the data. The resistance percentage data should include the number of isolates used in the calculation. 

   \- **Computing resistance rates:** count the **first isolate per patient per species per specimen type per period** and report a percentage only with **at least 30 isolates**.
3. The patient specific view should be separate from the antibiogram view and display recommended antibiotics for that patient specifically based on the data available from both the patient and resistance percentage calculations. Basically a very focused view of the Antibiogram table for only that one patient.
4. Should be able to print tables as PDFs.