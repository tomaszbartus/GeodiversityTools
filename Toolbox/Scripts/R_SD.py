# coding=utf-8
"""
Toolbox: GeodiversityTools (for ArcGIS Pro)
Tool: R_SD (Standard Deviation for Raster)
Version: v.1.0.0.
Short description: Calculates the Standard Deviation (SD) for a selected landscape feature (raster) within each polygon of an analytical grid and performs Min-Max standardization.
Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
2026-11-11
"""

import arcpy
import geodiversity_core as core

# Allow overwriting outputs
arcpy.env.overwriteOutput = True
# Prevent Z-coordinate and M-coordinate inheritance in feature classes
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_ras = arcpy.GetParameterAsText(0)  # Raster wejściowy
    grid_fl = arcpy.GetParameterAsText(1)  # Siatka analityczna (Feature Class)
    grid_id_field = arcpy.GetParameterAsText(2)  # Pole identyfikatora strefy

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(3)  # Ścieżka wyjściowej klasy obiektów
    output_raw_field = arcpy.GetParameterAsText(4)  # Nazwa pola surowego odchylenia standardowego
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
    zonal_stat_table = fr"memory\{prefix}_ZONAL_STAT"
    stats_table = fr"memory\{prefix}_STD_STATS"

    # 1. Walidacja przez core
    core.check_gdb_feature(grid_fl)

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
        arcpy.management.RemoveLocks(grid_fl)
    except:
        pass

    # Przygotowanie bezpiecznej kopii roboczej siatki w pamięci RAM z polem StatZoneID
    temp_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # Czyszczenie śmieci w pamięci
    for item in [zonal_stat_table, stats_table]:
        if arcpy.Exists(item):
            try:
                arcpy.management.Delete(item)
            except:
                pass

    # ----------------------------------------------------------------------
    # 2. ZONAL STATISTICS AS TABLE
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating pixel SD within the analytical grid zones...")
    arcpy.sa.ZonalStatisticsAsTable(temp_grid_memory, stat_zone_field_ID, landscape_ras, zonal_stat_table, "DATA",
                                    "STD")

    # ----------------------------------------------------------------------
    # 3. STANDARDIZATE SD (MIN-MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing SD using manual Min-Max normalization...")

    arcpy.analysis.Statistics(zonal_stat_table, stats_table, [["STD", "MIN"], ["STD", "MAX"]])

    with arcpy.da.SearchCursor(stats_table, ["MIN_STD", "MAX_STD"]) as cursor:
        min_std, max_std = next(cursor)

    arcpy.management.Delete(stats_table)

    std_field_name = "STD_MM"
    if std_field_name not in [f.name for f in arcpy.ListFields(zonal_stat_table)]:
        arcpy.management.AddField(zonal_stat_table, std_field_name, "DOUBLE")

    if max_std == min_std:
        arcpy.AddWarning("STD has constant value across all zones. Standardized values set to 0.")
        arcpy.management.CalculateField(zonal_stat_table, std_field_name, "0", "PYTHON3")
    else:
        code_block = f"""
def minmax(val):
    return (val - {min_std}) / ({max_std} - {min_std}) if val is not None else 0.0
"""
        arcpy.management.CalculateField(
            zonal_stat_table,
            std_field_name,
            "minmax(!STD!)",
            "PYTHON3",
            code_block
        )

    # ----------------------------------------------------------------------
    # 4. BEZPIECZNY ZAPIS DO NOWEJ KLASY OBIEKTÓW (Non-destructive)
    # ----------------------------------------------------------------------
    core.safe_write_to_new_feature_class(
        grid_fl=grid_fl,
        grid_id_field=grid_id_field,
        result_table=zonal_stat_table,
        raw_value_field="STD",
        std_value_field=std_field_name,
        output_fc_path=output_fc_path,
        output_raw_field=output_raw_field,
        output_std_field=output_std_field
    )

    # ----------------------------------------------------------------------
    # 5. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    for item in [zonal_stat_table, stats_table, temp_grid_memory]:
        if arcpy.Exists(item):
            try:
                arcpy.management.Delete(item)
            except:
                pass

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
        arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("R_SD calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()