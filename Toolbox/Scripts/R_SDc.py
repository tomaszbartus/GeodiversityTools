# coding=utf-8
"""
Geodiversity Tool: R_SDc (Circular Standard Deviation for Raster)
Calculates the Circular Standard Deviation (SDc) for a selected circular landscape feature (raster)
within each polygon of an analytical grid and performs Min-Max standardization.
Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
Refactored for GeodiversityTools Core Architecture
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
    landscape_ras = arcpy.GetParameterAsText(0)  # Raster wejściowy (wartości cyrkularne w stopniach)
    grid_fl = arcpy.GetParameterAsText(1)  # Bazowa siatka analityczna
    grid_id_field = arcpy.GetParameterAsText(2)  # Pole identyfikatora strefy

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(3)  # Ścieżka wyjściowej klasy obiektów
    output_raw_field = arcpy.GetParameterAsText(4)  # Nazwa pola surowego cyrkularnego odchylenia standardowego
    output_std_field = arcpy.GetParameterAsText(5)  # Nazwa pola zestandaryzowanego (Min-Max)

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
    # FORCE REMOVAL OF LOCKS FROM INPUT DATASETS
    # ----------------------------------------------------------------------
    try:
        arcpy.AddMessage("Removing existing locks...")
        arcpy.management.RemoveLocks(landscape_ras)
        arcpy.management.RemoveLocks(grid_fl)
    except:
        pass

    # Przygotowanie bezpiecznej kopii roboczej siatki w pamięci RAM z polem StatZoneID
    temp_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # Czyszczenie śmieci pośrednich
    for item in [landscape_rad, landscape_sin, landscape_cos, zonal_sin_tbl, zonal_cos_tbl, zonal_stat_table,
                 stats_table]:
        if arcpy.Exists(item):
            try:
                arcpy.management.Delete(item)
            except:
                pass

    # ----------------------------------------------------------------------
    # 2. CONVERT Degrees -> Radians (raster)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Converting degrees to radians...")
    raster_rad = Raster(landscape_ras) / (180.0 / math.pi)
    raster_rad.save(landscape_rad)

    # ----------------------------------------------------------------------
    # 3. CALCULATE sin(θ) and cos(θ)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating sin and cos rasters...")
    raster_sin = Sin(raster_rad)
    raster_sin.save(landscape_sin)

    raster_cos = Cos(raster_rad)
    raster_cos.save(landscape_cos)

    # ----------------------------------------------------------------------
    # 4. ZONAL SUM of sin and cos (per grid cell) -> memory tables
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Computing zonal sums (sin/cos)...")
    arcpy.sa.ZonalStatisticsAsTable(temp_grid_memory, stat_zone_field_ID, landscape_sin, zonal_sin_tbl, "DATA", "SUM")
    arcpy.sa.ZonalStatisticsAsTable(temp_grid_memory, stat_zone_field_ID, landscape_cos, zonal_cos_tbl, "DATA", "SUM")

    # ----------------------------------------------------------------------
    # 5. PREPARE SIN TABLE (zonal_sin_tbl)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Preparing Sin values...")
    arcpy.management.AddField(zonal_sin_tbl, "SumSin", "DOUBLE")
    arcpy.management.CalculateField(zonal_sin_tbl, "SumSin", "!SUM!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 6. PREPARE COS TABLE (zonal_cos_tbl)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Preparing Cos values...")
    arcpy.management.AddField(zonal_cos_tbl, "SumCos", "DOUBLE")
    arcpy.management.CalculateField(zonal_cos_tbl, "SumCos", "!SUM!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 7. CREATE FINAL ZONAL STAT TABLE & JOIN
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining Sin and Cos tables...")
    arcpy.management.CopyRows(zonal_sin_tbl, zonal_stat_table)
    arcpy.management.JoinField(zonal_stat_table, stat_zone_field_ID, zonal_cos_tbl, stat_zone_field_ID, ["SumCos"])

    # ----------------------------------------------------------------------
    # 8. ADD EMPTY FIELDS FOR: R, R_Mn, SDc
    # ----------------------------------------------------------------------
    arcpy.management.AddField(zonal_stat_table, "R", "DOUBLE")
    arcpy.management.AddField(zonal_stat_table, "R_Mn", "DOUBLE")
    arcpy.management.AddField(zonal_stat_table, "SDc", "DOUBLE")

    # ----------------------------------------------------------------------
    # 9. CALCULATE R, R_Mn and SDc
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating R, R_Mn and SDc...")

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
    arcpy.management.CalculateField(zonal_stat_table, "SDc", "(180/math.pi)*math.sqrt(max(0, 2*(1-!R_Mn!)))", "PYTHON3")

    # ----------------------------------------------------------------------
    # 10. MANUAL MIN-MAX STANDARDIZATION
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing SDc using manual Min-Max normalization...")

    arcpy.analysis.Statistics(zonal_stat_table, stats_table, [["SDc", "MIN"], ["SDc", "MAX"]])
    with arcpy.da.SearchCursor(stats_table, ["MIN_SDc", "MAX_SDc"]) as cursor:
        min_sdc, max_sdc = next(cursor)
    arcpy.management.Delete(stats_table)

    std_field_name = "SDc_MM"
    arcpy.management.AddField(zonal_stat_table, std_field_name, "DOUBLE")

    if max_sdc == min_sdc:
        arcpy.AddWarning("SDc has constant value across all zones. Standardized values will be set to 0.")
        arcpy.management.CalculateField(zonal_stat_table, std_field_name, "0", "PYTHON3")
    else:
        code_block_mm = f"""
def minmax(val):
    return (val - {min_sdc}) / ({max_sdc} - {min_sdc}) if val is not None else 0.0
"""
        arcpy.management.CalculateField(
            zonal_stat_table,
            std_field_name,
            "minmax(!SDc!)",
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
        raw_value_field="SDc",
        std_value_field=std_field_name,
        output_fc_path=output_fc_path,
        output_raw_field=output_raw_field,
        output_std_field=output_std_field
    )

    # ----------------------------------------------------------------------
    # 12. CLEANUP (delete memory intermediates)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    for item in [landscape_rad, landscape_sin, landscape_cos, zonal_sin_tbl, zonal_cos_tbl, zonal_stat_table,
                 stats_table, temp_grid_memory]:
        try:
            if arcpy.Exists(item):
                arcpy.management.Delete(item)
        except Exception:
            arcpy.AddWarning(f"Could not delete intermediate dataset: {item}")

    arcpy.ClearWorkspaceCache_management()
    try:
        if workspace_gdb.endswith(".gdb"):
            arcpy.management.Compact(workspace_gdb)
    except:
        pass

    arcpy.AddMessage("R_SDc calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("A Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()