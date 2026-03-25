-- Well Master Views
-- Joins well headers with wellbore data for BI consumption.

CREATE OR ALTER VIEW vw_well_master AS
SELECT
    w.well_id,
    w.facility_name,
    w.uwi,
    w.api_number,
    w.current_operator AS operator,
    w.well_status,
    w.field_name,
    w.basin,
    w.state_province,
    w.county,
    w.surface_latitude,
    w.surface_longitude,
    w.spud_date,
    w.total_depth_ft,
    wb_count.wellbore_count
FROM osdu_curated_lakehouse.dbo.wells w
LEFT JOIN (
    SELECT well_id, COUNT(*) AS wellbore_count
    FROM osdu_curated_lakehouse.dbo.wellbores
    GROUP BY well_id
) wb_count ON w.well_id = wb_count.well_id;

CREATE OR ALTER VIEW vw_wellbore_detail AS
SELECT
    wb.wellbore_id,
    wb.wellbore_name,
    wb.wellbore_number,
    wb.trajectory_type,
    wb.total_depth_md_ft,
    wb.total_depth_tvd_ft,
    wb.target_formation,
    wb.wellbore_status,
    wb.spud_date AS wellbore_spud_date,
    wb.completion_date,
    w.facility_name AS well_name,
    w.field_name,
    w.basin,
    w.current_operator AS operator
FROM osdu_curated_lakehouse.dbo.wellbores wb
INNER JOIN osdu_curated_lakehouse.dbo.wells w ON wb.well_id = w.well_id;
