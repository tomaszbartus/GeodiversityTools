# Geodiversity Tool R_SD
# Calculates the Standard Deviation (SD) for a selected landscape feature (raster)
# in each polygon of an analytical grid
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# Date: 2025-11-29

import arcpy

# Allow overwriting outputs
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    # 0 - Input landscape raster (continuous variable)
    # 1 - Analytical grid feature layer (polygon layer)
    # 2 - Analytical grid identification field (e.g. OBJECTID)
    landscape_ras = arcpy.GetParameterAsText(0)
    grid_fl = arcpy.GetParameterAsText(1)
    grid_id_field = arcpy.GetParameterAsText(2)

    # ----------------------------------------------------------------------
    # INTERMEDIATE DATA
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(grid_fl).path
    raster_base = arcpy.Describe(landscape_ras).baseName
    prefix = raster_base[:3].upper()
    zonal_stat_table = f"{workspace_gdb}\\{prefix}_ZONAL_STAT"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_SD"
    output_index_alias = f"{prefix}_SD"
    std_output_index_name = f"{prefix}_SD_MM"
    std_output_index_alias = f"Std_{prefix}_SD"

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS ALREADY EXIST IN GRID TABLE
    # ----------------------------------------------------------------------
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    field_raw = output_index_name.upper()
    field_std = std_output_index_name.upper()

    if field_raw in existing_fields or field_std in existing_fields:
        arcpy.AddError(
            f"Fields '{output_index_name.upper()}' and/or '{std_output_index_name.upper()}' already exist "
            f"in the analytical grid attribute table.\n"
            f"Remove these fields before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

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

    # ----------------------------------------------------------------------
    # 4. Rename joined fields (raw index + standardized index)
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "STD", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "STD_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 5. CLEANUP
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