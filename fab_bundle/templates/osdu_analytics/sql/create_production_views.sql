-- Production Analytics Views

CREATE OR ALTER VIEW vw_production_summary AS
SELECT
    p.well_id,
    w.facility_name,
    w.field_name,
    w.basin,
    w.current_operator AS operator,
    p.production_date,
    p.oil_bbl,
    p.gas_mcf,
    p.water_bbl,
    p.boe,
    p.gor,
    p.water_cut,
    p.hours_on,
    p.tubing_pressure_psi,
    p.casing_pressure_psi
FROM production_lakehouse.dbo.production_daily p
INNER JOIN osdu_curated_lakehouse.dbo.wells w ON p.well_id = w.well_id;

CREATE OR ALTER VIEW vw_production_monthly_summary AS
SELECT
    pm.well_id,
    w.facility_name,
    w.field_name,
    w.basin,
    pm.production_month,
    pm.oil_bbl,
    pm.gas_mcf,
    pm.water_bbl,
    pm.boe,
    pm.avg_gor,
    pm.avg_water_cut,
    pm.producing_days,
    pm.avg_tubing_pressure,
    -- Running cumulative production
    SUM(pm.oil_bbl) OVER (PARTITION BY pm.well_id ORDER BY pm.production_month) AS cum_oil_bbl,
    SUM(pm.gas_mcf) OVER (PARTITION BY pm.well_id ORDER BY pm.production_month) AS cum_gas_mcf,
    SUM(pm.boe) OVER (PARTITION BY pm.well_id ORDER BY pm.production_month) AS cum_boe
FROM production_lakehouse.dbo.production_monthly pm
INNER JOIN osdu_curated_lakehouse.dbo.wells w ON pm.well_id = w.well_id;

CREATE OR ALTER VIEW vw_field_production AS
SELECT
    w.field_name,
    w.basin,
    p.production_date,
    COUNT(DISTINCT p.well_id) AS producing_wells,
    SUM(p.oil_bbl) AS total_oil_bbl,
    SUM(p.gas_mcf) AS total_gas_mcf,
    SUM(p.water_bbl) AS total_water_bbl,
    SUM(p.boe) AS total_boe,
    AVG(p.gor) AS avg_gor,
    AVG(p.water_cut) AS avg_water_cut
FROM production_lakehouse.dbo.production_daily p
INNER JOIN osdu_curated_lakehouse.dbo.wells w ON p.well_id = w.well_id
GROUP BY w.field_name, w.basin, p.production_date;
