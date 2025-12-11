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
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    # 0 - Input RASTER, LINEAR landscape feature (continuous variable)
    # 1 - Analytical grid feature layer (polygon layer)
    # 2 - Analytical grid identification field (e.g. OBJECTID)
    landscape_ras = arcpy.GetParameterAsText(0)
    grid_fl = arcpy.GetParameterAsText(1)
    grid_id_field = arcpy.GetParameterAsText(2)

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(grid_fl).path
    raster_base = arcpy.Describe(landscape_ras).baseName
    prefix = raster_base[:3].upper()

    zonal_stat_table = f"{workspace_gdb}\\{prefix}_ZONAL_STAT"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_RSD"
    output_index_alias = f"{prefix}_R_SD"
    std_output_index_name = f"{prefix}_RSD_MM"
    std_output_index_alias = f"Std_{prefix}_R_SD"

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS ALREADY EXIST IN GRID TABLE
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Checking if the output fields already exist...")
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
    # 1. ZONAL STATISTICS AS TABLE
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating pixel SD within the analytical grid zones...")
    arcpy.sa.ZonalStatisticsAsTable(grid_fl, grid_id_field, landscape_ras, zonal_stat_table, "DATA", "STD")

    # ----------------------------------------------------------------------
    # 2. STANDARDIZE SD (MIN-MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing SD (Min-Max)...")
    arcpy.management.StandardizeField(zonal_stat_table, "STD", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 3. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
    # ----------------------------------------------------------------------
    fields_to_check = ["STD", "STD_MIN_MAX"]
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    # Checking whether any fields need to be removed at all
    fields_to_remove = [f for f in fields_to_check if f in existing_fields]

    if fields_to_remove:
        arcpy.AddMessage("Removing old join fields from the grid...")
        for old_field in fields_to_remove:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 4. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, grid_id_field, zonal_stat_table, grid_id_field, ["STD", "STD_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 5. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "STD", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "STD_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 6. CLEANUP
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

    arcpy.AddMessage("R_SD calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()