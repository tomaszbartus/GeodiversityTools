# Geodiversity Tool P_Ne
# Calculates the number of geosites (point features)
# within each polygon of the analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2025-11-29

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)     # point feature layer
    landscape_attr = arcpy.GetParameterAsText(1)   # category field (not used for calculation)
    grid_fl = arcpy.GetParameterAsText(2)          # analytical grid
    grid_id_field = arcpy.GetParameterAsText(3)    # grid ID field

    # ----------------------------------------------------------------------
    # INTERMEDIATE DATA
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()

    intersect_fc = f"{workspace_gdb}\\{prefix}_Ne_Int"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_Ne"
    output_index_alias = f"{prefix}_Ne"
    std_output_index_name = f"{prefix}_Ne_MM"
    std_output_index_alias = f"Std_{prefix}_Ne"

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS ALREADY EXIST
    # ----------------------------------------------------------------------
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    if output_index_name.upper() in existing_fields or std_output_index_name.upper() in existing_fields:
        arcpy.AddError(
            f"Fields '{output_index_name.upper()}' and/or '{std_output_index_name.upper()}' "
            f"already exist in the analytical grid.\n"
            f"Remove these fields before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # 1. SPATIAL JOIN – count points inside each grid cell
    # ----------------------------------------------------------------------
    arcpy.analysis.SpatialJoin(
        grid_fl, landscape_fl, intersect_fc,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", "", "INTERSECT"
    )

    # Rename Join_Count to Ne
    arcpy.management.AlterField(intersect_fc, "Join_Count", "Ne")

    # ----------------------------------------------------------------------
    # 2. STANDARDIZATION (MIN–MAX)
    # ----------------------------------------------------------------------
    arcpy.management.StandardizeField(intersect_fc, "Ne", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 3. JOIN BACK TO GRID
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(
        grid_fl, grid_id_field,
        intersect_fc, grid_id_field,
        ["Ne", "Ne_MIN_MAX"]
    )

    # ----------------------------------------------------------------------
    # 4. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "Ne", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "Ne_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 5. CLEANUP
    # ----------------------------------------------------------------------
    if arcpy.Exists(intersect_fc):
        arcpy.management.Delete(intersect_fc)

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("Geosites Ne calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
