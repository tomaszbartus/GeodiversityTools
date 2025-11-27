# Geodiversity Tool R_SD
# Calculates the Standard Deviation (SD) for a selected landscape feature (raster)
# in each polygon of an analytical grid.
# Author: Tomasz Bartuś (bartus@agh.edu.pl)
# Date: 2025-11-27 (finalized)

import arcpy

# Allow to overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    # 0 - Input raster landscape feature
    # 1 - Analytical grid feature layer (polygon layer)
    # 2 - Analytical grid identification field (e.g. OBJECTID)
    landscape_ras = arcpy.GetParameterAsText(0)
    grid_fl = arcpy.GetParameterAsText(1)
    grid_id_field = arcpy.GetParameterAsText(2)

    # Workspace (use geodatabase where the grid lives)
    workspace_gdb = arcpy.Describe(grid_fl).path

    # ----------------------------------------------------------------------
    # Prepare names and intermediate outputs
    # ----------------------------------------------------------------------
    raster_base = arcpy.Describe(landscape_ras).baseName
    prefix = raster_base[:3].upper()

    zonal_stat_table = f"{workspace_gdb}\\{prefix}_ZONAL_STAT"

    # ----------------------------------------------------------------------
    # 1. Zonal statistics as table
    # ----------------------------------------------------------------------
    arcpy.sa.ZonalStatisticsAsTable(grid_fl, grid_id_field, landscape_ras, zonal_stat_table, "DATA", "STD")

    # ----------------------------------------------------------------------
    # 2. STANDARDIZE SD (MIN-MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing SD (Min-Max)...")
    arcpy.management.StandardizeField(zonal_stat_table, "STD", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 3. JOIN zonal_stat_table to the analytical grid
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, grid_id_field, zonal_stat_table, grid_id_field, ["STD", "STD_MIN_MAX"])

    # RENAME joined fields on the grid for clarity (prefix and alias with full raster name)
    field_name = f"{prefix}_SD"
    field_alias = f"{prefix}_SD"
    std_field_name = f"{prefix}_SD_MM"
    std_field_alias = f"Std_{prefix}_SD"

    arcpy.management.AlterField(grid_fl, "STD", field_name, field_alias)
    arcpy.management.AlterField(grid_fl, "STD_MIN_MAX", std_field_name, std_field_alias)

    # ----------------------------------------------------------------------
    # 4. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    for item in [zonal_stat_table]:
        if arcpy.Exists(item):
            try:
               arcpy.management.Delete(item)
            except Exception:
                arcpy.AddWarning(f"Could not delete intermediate dataset: {item}")

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("SD calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()