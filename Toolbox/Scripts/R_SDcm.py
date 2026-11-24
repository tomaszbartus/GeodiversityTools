# coding=utf-8
"""
Toolbox: GeodiversityTools (for ArcGIS Pro)
Tool: R_SDcm (Modified Circular Standard Deviation for Raster)
Version: v.1.0.0.
Short description: Calculates the Circular Standard Deviation (SDc) for a circular landscape feature (raster, e.g. aspect) excluding flat pixels (where slope <= threshold) within each polygon of an analytical grid.
Performs Min-Max standardization.
Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
2026-11-11
"""

import arcpy
import math
from arcpy.sa import *
import textwrap
import geodiversity_core as core

# Allow to overwrite
arcpy.env.overwriteOutput = True
# Prevent Z-coordinate and M-coordinate inheritance in feature classes
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_ras = arcpy.GetParameterAsText(0)  # Raster cyrkularny (stopnie, np. aspect)
    slope_ras = arcpy.GetParameterAsText(1)  # Raster nachylenia (stopnie)
    slope_thresh_param = arcpy.GetParameterAsText(2)  # Próg nachylenia (np. 5.0)
    grid_fl = arcpy.GetParameterAsText(3)  # Bazowa siatka analityczna
    grid_id_field = arcpy.GetParameterAsText(4)  # Pole identyfikatora strefy

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(5)  # Ścieżka wyjściowej klasy obiektów
    output_raw_field = arcpy.GetParameterAsText(6)  # Nazwa pola surowego R_SDcm
    output_std_field = arcpy.GetParameterAsText(7)  # Nazwa pola zestandaryzowanego (Min-Max)

    slope_threshold = float(slope_thresh_param) if slope_thresh_param else 0.0

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(grid_fl).path
    desc_land = arcpy.Describe(landscape_ras)
    base_name = desc_land.name
    prefix = arcpy.ValidateTableName(
        base_name[:3].upper(),
        workspace_gdb
    )

    stat_zone_field_ID = "StatZoneID"
    filtered_ras = fr"memory\{prefix}_FLT_RAS"
    landscape_rad = fr"memory\{prefix}_RAD"
    landscape_sin = fr"memory\{prefix}_SIN"
    landscape_cos = fr"memory\{prefix}_COS"

    zonal_sin_tbl = fr"memory\{prefix}_SIN_SUM"
    zonal_cos_tbl = fr"memory\{prefix}_COS_SUM"
    zonal_stat_table = fr"memory\{prefix}_ZONAL_STAT"
    stats_table = fr"memory\{prefix}_STATS"

    # 1. Walidacja przez core
    core.check_gdb_feature(grid_fl)

    # ---------------------------------------------------------------------------
    # CHECK SPATIAL INTERSECTION OF EXTENTS
    # ---------------------------------------------------------------------------
    arcpy.AddMessage("Recalculating feature class extent for the grid...")
    arcpy.management.RecalculateFeatureClassExtent(grid_fl)

    ext_ras = arcpy.Describe(landscape_ras).extent
    ext_grid = arcpy.Describe(grid_fl).extent

    if ext_ras.disjoint(ext_grid):
        arcpy.AddError("The raster layer does not spatially overlap with the analytical grid.")
        raise arcpy.ExecuteError

    arcpy.AddMessage("Input validation passed.")

    # ----------------------------------------------------------------------
    # FORCE REMOVAL OF LOCKS
    # ----------------------------------------------------------------------
    try:
        arcpy.AddMessage("Removing existing locks...")
        arcpy.management.RemoveLocks(landscape_ras)
        arcpy.management.RemoveLocks(slope_ras)
        arcpy.management.RemoveLocks(grid_fl)
    except:
        pass

    # Przygotowanie bezpiecznej kopii roboczej siatki w pamięci RAM z polem StatZoneID
    temp_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # Czyszczenie tymczasowych zbiorów danych
    intermediate_items = [filtered_ras, landscape_rad, landscape_sin, landscape_cos, zonal_sin_tbl, zonal_cos_tbl,
                          zonal_stat_table, stats_table]
    for item in intermediate_items:
        if arcpy.Exists(item):
            try:
                arcpy.management.Delete(item)
            except:
                pass

    # ----------------------------------------------------------------------
    # 2. FILTER RASTER BY SLOPE THRESHOLD (Slope > threshold -> Aspect, else NoData)
    # ----------------------------------------------------------------------
    arcpy.AddMessage(f"Filtering aspect raster where slope > {slope_threshold} degrees...")
    masked_aspect = Con(Raster(slope_ras) > slope_threshold, Raster(landscape_ras))
    masked_aspect.save(filtered_ras)

    # ----------------------------------------------------------------------
    # 3. CONVERT Degrees -> Radians (filtered raster)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Converting degrees to radians...")
    raster_rad = Raster(filtered_ras) / (180.0 / math.pi)
    raster_rad.save(landscape_rad)

    # ----------------------------------------------------------------------
    # 4. CALCULATE sin(θ) and cos(θ)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating sin and cos rasters...")
    raster_sin = Sin(raster_rad)
    raster_sin.save(landscape_sin)

    raster_cos = Cos(raster_rad)
    raster_cos.save(landscape_cos)

    # ----------------------------------------------------------------------
    # 5. ZONAL SUM of sin and cos (per grid cell) -> memory tables
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Computing zonal sums (sin/cos)...")
    arcpy.sa.ZonalStatisticsAsTable(temp_grid_memory, stat_zone_field_ID, landscape_sin, zonal_sin_tbl, "DATA", "SUM")
    arcpy.sa.ZonalStatisticsAsTable(temp_grid_memory, stat_zone_field_ID, landscape_cos, zonal_cos_tbl, "DATA", "SUM")

    # ----------------------------------------------------------------------
    # 6. PREPARE SIN & COS TABLES
    # ----------------------------------------------------------------------
    arcpy.management.AddField(zonal_sin_tbl, "SumSin", "DOUBLE")
    arcpy.management.CalculateField(zonal_sin_tbl, "SumSin", "!SUM!", "PYTHON3")

    arcpy.management.AddField(zonal_cos_tbl, "SumCos", "DOUBLE")
    arcpy.management.CalculateField(zonal_cos_tbl, "SumCos", "!SUM!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 7. CREATE FINAL ZONAL STAT TABLE & JOIN
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining Sin and Cos tables...")
    arcpy.management.CopyRows(zonal_sin_tbl, zonal_stat_table)
    arcpy.management.JoinField(zonal_stat_table, stat_zone_field_ID, zonal_cos_tbl, stat_zone_field_ID, ["SumCos"])

    # ----------------------------------------------------------------------
    # 8. ADD EMPTY FIELDS FOR: R, R_Mn, SDcm
    # ----------------------------------------------------------------------
    arcpy.management.AddField(zonal_stat_table, "R", "DOUBLE")
    arcpy.management.AddField(zonal_stat_table, "R_Mn", "DOUBLE")
    arcpy.management.AddField(zonal_stat_table, "SDcm", "DOUBLE")

    # ----------------------------------------------------------------------
    # 9. CALCULATE R, R_Mn and SDcm
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating R, R_Mn and modified SDcm...")

    code_block = textwrap.dedent("""
        import math
        def calc_r(sin_val, cos_val):
            try:
                sin_val = float(sin_val)
                cos_val = float(cos_val)
                return math.sqrt(sin_val**2 + cos_val**2)
            except:
                return None
    """)
    arcpy.management.CalculateField(zonal_stat_table, "R", "calc_r(!SumSin!, !SumCos!)", "PYTHON3", code_block)
    arcpy.management.CalculateField(zonal_stat_table, "R_Mn", "(!R! / !COUNT!) if !COUNT! not in (None, 0) else 0",
                                    "PYTHON3")
    arcpy.management.CalculateField(zonal_stat_table, "SDcm",
                                    "(180/math.pi)*math.sqrt(max(0, 2*(1-!R_Mn!))) if !COUNT! not in (None, 0) else 0.0",
                                    "PYTHON3")

    # ----------------------------------------------------------------------
    # 10. MANUAL MIN-MAX STANDARDIZATION
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing SDcm using manual Min-Max normalization...")

    arcpy.analysis.Statistics(zonal_stat_table, stats_table, [["SDcm", "MIN"], ["SDcm", "MAX"]])
    with arcpy.da.SearchCursor(stats_table, ["MIN_SDcm", "MAX_SDcm"]) as cursor:
        min_sdcm, max_sdcm = next(cursor)
    arcpy.management.Delete(stats_table)

    std_field_name = "SDcm_MM"
    arcpy.management.AddField(zonal_stat_table, std_field_name, "DOUBLE")

    if max_sdcm == min_sdcm:
        arcpy.AddWarning("SDcm has constant value across all zones. Standardized values set to 0.")
        arcpy.management.CalculateField(zonal_stat_table, std_field_name, "0", "PYTHON3")
    else:
        code_block_mm = f"""
def minmax(val):
    return (val - {min_sdcm}) / ({max_sdcm} - {min_sdcm}) if val is not None else 0.0
"""
        arcpy.management.CalculateField(
            zonal_stat_table,
            std_field_name,
            "minmax(!SDcm!)",
            "PYTHON3",
            code_block_mm
        )

    # ----------------------------------------------------------------------
    # 11. BEZPIECZNY ZAPIS DO NOWEJ KLASY OBIEKTÓW (Non-destructive)
    # ----------------------------------------------------------------------
    core.safe_write_to_new_feature_class(
        grid_fl=grid_fl,
        grid_id_field=grid_id_field,
        result_table=zonal_stat_table,
        raw_value_field="SDcm",
        std_value_field=std_field_name,
        output_fc_path=output_fc_path,
        output_raw_field=output_raw_field,
        output_std_field=output_std_field
    )

    # ----------------------------------------------------------------------
    # 12. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    for item in intermediate_items + [temp_grid_memory]:
        try:
            if arcpy.Exists(item):
                arcpy.management.Delete(item)
        except Exception:
            pass

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
        arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("R_SDcm calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("A Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()