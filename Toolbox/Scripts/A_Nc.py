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

    # Workspace GDB
    workspace_gdb = arcpy.Describe(landscape_fl).path

    # ----------------------------------------------------------------------
    # INTERMEDIATE FEATURE CLASSES
    # ----------------------------------------------------------------------
    prefix = landscape_attr[:3].upper()
    dissolved_fl = f"{workspace_gdb}\\{prefix}_Dis"
    nc_fl = f"{workspace_gdb}\\{prefix}_Nc"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_Nc"
    output_index_alias = f"{prefix}_Nc"
    std_output_index_name = f"{prefix}_Nc_MM"
    std_output_index_alias = f"Std_{prefix}_Nc"

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
    # 1. Dissolve polygons by category
    # ----------------------------------------------------------------------
    arcpy.management.Dissolve(landscape_fl, dissolved_fl, landscape_attr)

    # ----------------------------------------------------------------------
    # 2. Spatial Join: count dissolved polygons intersecting each grid cell
    # NOTE: field_mapping not required here (default behavior is correct)
    # ----------------------------------------------------------------------
    arcpy.analysis.SpatialJoin(
        grid_fl, dissolved_fl, nc_fl,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", "", "INTERSECT"
    )

    # ----------------------------------------------------------------------
    # 3. Standardization (Min–Max)
    # ----------------------------------------------------------------------
    arcpy.management.StandardizeField(nc_fl, "Join_Count", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 4. Join results back to the grid layer
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(
        grid_fl, grid_id_field, nc_fl, "TARGET_FID",
        ["Join_Count", "Join_Count_MIN_MAX"]
    )

    # ----------------------------------------------------------------------
    # 5. Rename joined fields (raw index + standardized index)
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "Join_Count", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "Join_Count_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 6. Cleanup
    # ----------------------------------------------------------------------
    for fl in (dissolved_fl, nc_fl):
        if arcpy.Exists(fl):
            arcpy.management.Delete(fl)

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("Nc calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("A geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("A Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
