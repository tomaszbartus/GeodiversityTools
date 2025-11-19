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
    # (all must be Feature Layers in the tool definition)
    landscape_fl = arcpy.GetParameterAsText(0)            # polygon feature layer
    landscape_attr = arcpy.GetParameterAsText(1)          # category field
    grid_fl = arcpy.GetParameterAsText(2)                # grid layer
    grid_id_field = arcpy.GetParameterAsText(3)          # OBJECTID of the grid

    # Workspace GDB (safe - points to geodatabase containing the landscape FL)
    workspace_gdb = arcpy.Describe(landscape_fl).path

    # ----------------------------------------------------------------------
    # Intermediate FC paths
    # ----------------------------------------------------------------------
    prefix = landscape_attr[:3].upper()
    dissolved_fl = f"{workspace_gdb}\\{prefix}_Dis"
    nc_fl = f"{workspace_gdb}\\{prefix}_Nc"

    # ----------------------------------------------------------------------
    # 1. Dissolve polygons by category
    # ----------------------------------------------------------------------
    arcpy.management.Dissolve(landscape_fl, dissolved_fl, landscape_attr)

    # ----------------------------------------------------------------------
    # 2. Spatial Join: count dissolved polygons inside grid cells
    # ----------------------------------------------------------------------
    arcpy.analysis.SpatialJoin(grid_fl, dissolved_fl, nc_fl,"JOIN_ONE_TO_ONE","KEEP_ALL","INTERSECT")

    # ----------------------------------------------------------------------
    # 3. Standardization (Min-Max)
    # ----------------------------------------------------------------------
    arcpy.management.StandardizeField(nc_fl,"Join_Count","MIN-MAX",0,1)

    # ----------------------------------------------------------------------
    # 4. Join results back to the grid layer
    # ----------------------------------------------------------------------
    field_raw = prefix + "_Nc"
    field_std = prefix + "_Nc_MM"

    arcpy.management.JoinField(grid_fl, grid_id_field, nc_fl,"TARGET_FID",["Join_Count", "Join_Count_MIN_MAX"])

    arcpy.management.AlterField(grid_fl, "Join_Count", field_raw, landscape_attr + "_Nc")
    arcpy.management.AlterField(grid_fl, "Join_Count_MIN_MAX", field_std, "Std_" + landscape_attr + "_Nc")

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
    # Catch geoprocessing-specific errors
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    # Catch other Python errors
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    # Ensure workspace cache is cleared even on error
    arcpy.ClearWorkspaceCache_management()