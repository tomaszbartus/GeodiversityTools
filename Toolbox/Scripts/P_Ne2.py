# Geodiversity Tool P_Ne
# Calculates the number of geosites (point features) within each polygon of the analytical grid
# Author: bartus@agh.edu.pl
# 2025-11-26

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)   # point feature layer
    landscape_attr = arcpy.GetParameterAsText(1) # category field (string only, not used in prefix)
    grid_fl = arcpy.GetParameterAsText(2)        # analytical grid FL
    grid_id_field = arcpy.GetParameterAsText(3)  # grid ID field

    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS ALREADY EXIST
    # ----------------------------------------------------------------------
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    field_raw = f"{prefix}_Ne".upper()
    field_std = f"{prefix}_Ne_MM".upper()

    if field_raw in existing_fields or field_std in existing_fields:
        arcpy.AddError(
            f"Fields '{field_raw}' and/or '{field_std}' already exist "
            f"in the analytical grid attribute table.\n"
            f"Please remove these fields before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # INTERMEDIATE DATA
    # ----------------------------------------------------------------------
    intersect_fc = f"{workspace_gdb}\\{prefix}_Ne_Int"

    # ----------------------------------------------------------------------
    # 2. SPATIAL JOIN
    # ----------------------------------------------------------------------
    arcpy.analysis.SpatialJoin(
        grid_fl, landscape_fl, intersect_fc,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", "", "INTERSECT"
    )

    arcpy.management.AlterField(intersect_fc, "Join_Count", "Ne")

    # ----------------------------------------------------------------------
    # 3. MIN-MAX STANDARDIZATION
    # ----------------------------------------------------------------------
    arcpy.management.StandardizeField(intersect_fc, "Ne", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 4. JOIN BACK TO GRID
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(grid_fl, grid_id_field, intersect_fc, grid_id_field,["Ne", "Ne_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 5. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "Ne", f"{prefix}_Ne", landscape_attr + "_Ne")
    arcpy.management.AlterField(grid_fl, "Ne_MIN_MAX", f"{prefix}_Ne_MM", "Std_" + landscape_attr + "_Ne")

    # ----------------------------------------------------------------------
    # 6. CLEANUP
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
