# Geodiversity Tool A_Nc
# Calculates the number of polygon feature categories of a selected landscape feature
# within each polygon of an analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2025-11-29

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)      # Polygon feature layer
    landscape_attr = arcpy.GetParameterAsText(1)    # Category field
    grid_fl = arcpy.GetParameterAsText(2)           # Analytical grid layer
    grid_id_field = arcpy.GetParameterAsText(3)     # Grid ID (usually OBJECTID)

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path

    prefix = landscape_attr[:3].upper()
    dissolved_fl = f"{workspace_gdb}\\{prefix}_Dis"
    nc_fl = f"{workspace_gdb}\\{prefix}_Nc"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_ANc"
    output_index_alias = f"{prefix}_A_Nc"
    std_output_index_name = f"{prefix}_ANc_MM"
    std_output_index_alias = f"Std_{prefix}_A_Nc"

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
    # 1. DISSOLVE LANDSCAPE POLYGONS BY CATEGORY
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Dissolving the landscape polygons by category...")
    arcpy.management.Dissolve(landscape_fl, dissolved_fl, landscape_attr)

    # ----------------------------------------------------------------------
    # 2. SPATIAL JOIN: count dissolved polygons intersecting each grid cell
    # NOTE: field_mapping not required here (default behavior is correct)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Spatially joining landscape polygons with the analytical grid...")
    arcpy.analysis.SpatialJoin(
        grid_fl, dissolved_fl, nc_fl,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", "", "INTERSECT"
    )

    # ----------------------------------------------------------------------
    # 3. STANDARDIZE A_Nc (MIN-MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing A_Nc (Min-Max)...")
    arcpy.management.StandardizeField(nc_fl, "Join_Count", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 4. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
    # ----------------------------------------------------------------------
    fields_to_check = ["JOIN_COUNT", "JOIN_COUNT_MIN_MAX"]
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    # Checking whether any fields need to be removed at all
    fields_to_remove = [f for f in fields_to_check if f in existing_fields]

    if fields_to_remove:
        arcpy.AddMessage("Removing old join fields from the grid...")
        for old_field in fields_to_remove:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 5. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(
        grid_fl, grid_id_field, nc_fl, "TARGET_FID",
        ["Join_Count", "Join_Count_MIN_MAX"]
    )

    # ----------------------------------------------------------------------
    # 6. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "Join_Count", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "Join_Count_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 7. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    for fl in (dissolved_fl, nc_fl):
        if arcpy.Exists(fl):
            arcpy.management.Delete(fl)

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("A_Nc calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("A geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("A Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
