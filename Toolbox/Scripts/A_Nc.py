# Geodiversity Tool A_Nc
# Calculates the number of categories of a selected landscape feature
# within each polygon of an analytical grid.
# Author: bartus@agh.edu.pl
# 2025-11-19

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)            # polygon feature layer
    landscape_attr = arcpy.GetParameterAsText(1)          # category field
    grid_fl = arcpy.GetParameterAsText(2)                # grid layer
    grid_id_field = arcpy.GetParameterAsText(3)          # OBJECTID of the grid

    # Workspace GDB
    workspace_gdb = arcpy.Describe(landscape_fl).path

    # ----------------------------------------------------------------------
    # Intermediate FC paths
    # ----------------------------------------------------------------------
    prefix = landscape_attr[:3].upper()
    dissolved_fl = f"{workspace_gdb}\\{prefix}_Dis"
    nc_fl = f"{workspace_gdb}\\{prefix}_Nc"

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS IN ANALYTICAL GRID ALREADY EXIST IN GRID TABLE
    # ----------------------------------------------------------------------
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    field_raw = (prefix + "_Nc").upper()
    field_std = ("Std_" + landscape_attr + "_Nc").upper()

    if field_raw in existing_fields or field_std in existing_fields:
        arcpy.AddError(
            f"Fields '{prefix}_Nc' and/or 'Std_{landscape_attr}_Nc' already exist "
            f"in the analytical grid attribute table.\n"
            f"Please remove these fields before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # 1. Dissolve polygons by category
    # ----------------------------------------------------------------------
    arcpy.management.Dissolve(landscape_fl, dissolved_fl, landscape_attr)

    # ----------------------------------------------------------------------
    # 2. Spatial Join: count dissolved polygons inside grid cells
    # ----------------------------------------------------------------------
    arcpy.analysis.SpatialJoin(
        grid_fl, dissolved_fl, nc_fl,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", "INTERSECT"
    )

    # ----------------------------------------------------------------------
    # 3. Standardization (Min-Max)
    # ----------------------------------------------------------------------
    arcpy.management.StandardizeField(nc_fl, "Join_Count", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 4. Join results back to the grid layer
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(
        grid_fl, grid_id_field, nc_fl, "TARGET_FID",
        ["Join_Count", "Join_Count_MIN_MAX"]
    )

    arcpy.management.AlterField(grid_fl, "Join_Count", prefix + "_Nc", landscape_attr + "_Nc")
    arcpy.management.AlterField(grid_fl, "Join_Count_MIN_MAX", prefix + "_Nc_MM",
                                "Std_" + landscape_attr + "_Nc")

    # ----------------------------------------------------------------------
    # 5. Cleanup
    # ----------------------------------------------------------------------
    for fl in (dissolved_fl, nc_fl):
        if arcpy.Exists(fl):
            arcpy.management.Delete(fl)

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("Nc calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
