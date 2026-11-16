# coding=utf-8
"""
Geodiversity Tool: R_SDm (Modified Standard Deviation for Raster)
Calculates the Standard Deviation (SD) for a continuous landscape feature (raster)
excluding flat pixels (where slope <= threshold) within each polygon of an analytical grid.
Performs Min-Max standardization.
Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
Refactored for GeodiversityTools Core Architecture
"""

import arcpy
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
    landscape_ras = arcpy.GetParameterAsText(0)  # Raster ciągły (np. krzywizna, NMT)
    slope_ras = arcpy.GetParameterAsText(1)  # Raster nachylenia (stopnie)
    slope_thresh_param = arcpy.GetParameterAsText(2)  # Próg nachylenia (np. 5.0)
    grid_fl = arcpy.GetParameterAsText(3)  # Bazowa siatka analityczna
    grid_id_field = arcpy.GetParameterAsText(4)  # Pole identyfikatora strefy

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(5)  # Ścieżka wyjściowej klasy obiektów
    output_raw_field = arcpy.GetParameterAsText(6)  # Nazwa pola surowego R_SDm
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
    filtered_ras = fr"memory\{prefix}_FLT_SD_RAS"
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
    intermediate_items = [filtered_ras, zonal_stat_table, stats_table]
    for item in intermediate_items:
        if arcpy.Exists(item):
            try:
                arcpy.management.Delete(item)
            except:
                pass

    # ----------------------------------------------------------------------
    # 2. FILTER RASTER BY SLOPE THRESHOLD (Slope > threshold -> Landscape Ras, else NoData)
    # ----------------------------------------------------------------------
    arcpy.AddMessage(f"Filtering landscape raster where slope > {slope_threshold} degrees...")
    masked_raster = Con(Raster(slope_ras) > slope_threshold, Raster(landscape_ras))
    masked_raster.save(filtered_ras)

    # ----------------------------------------------------------------------
    # 3. ZONAL STATISTICS AS TABLE (STD)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating pixel Standard Deviation within zones (excluding flat areas)...")
    arcpy.sa.ZonalStatisticsAsTable(temp_grid_memory, stat_zone_field_ID, filtered_ras, zonal_stat_table, "DATA", "STD")

    # ----------------------------------------------------------------------
    # 4. STANDARDIZATE SDm (MIN-MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing SDm using manual Min-Max normalization...")

    arcpy.analysis.Statistics(zonal_stat_table, stats_table, [["STD", "MIN"], ["STD", "MAX"]])

    # Sprawdzenie czy tabela statystyk zawiera dane
    min_std, max_std = 0.0, 0.0
    with arcpy.da.SearchCursor(stats_table, ["MIN_STD", "MAX_STD"]) as cursor:
        for row in cursor:
            min_std, max_std = row
            break
    arcpy.management.Delete(stats_table)

    std_field_name = "SDm_MM"
    if std_field_name not in [f.name for f in arcpy.ListFields(zonal_stat_table)]:
        arcpy.management.AddField(zonal_stat_table, std_field_name, "DOUBLE")

    if max_std is None or min_std is None or max_std == min_std:
        arcpy.AddWarning("STD has constant or null value across all zones. Standardized values set to 0.")
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
    # 5. BEZPIECZNY ZAPIS DO NOWEJ KLASY OBIEKTÓW (Non-destructive)
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
    # 6. CLEANUP
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

    arcpy.AddMessage("R_SDm calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()