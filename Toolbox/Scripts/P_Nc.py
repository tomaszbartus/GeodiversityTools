# Geodiversity Tool P_Nc
# The script calculates the number of geosite (point) categories of a selected
# landscape feature within each polygon of the analytical grid.
# Author: bartus@agh.edu.pl
# 2025-11-23

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)           # point feature layer
    landscape_attr = arcpy.GetParameterAsText(1)         # geosites category field
    grid_fl = arcpy.GetParameterAsText(2)                # grid layer
    grid_id_field = arcpy.GetParameterAsText(3)          # OBJECTID of the grid

    # Workspace GDB
    workspace_gdb = arcpy.Describe(landscape_fl).path

    # ----------------------------------------------------------------------
    # Intermediate feature class and table paths
    # ----------------------------------------------------------------------
    prefix = landscape_fl[:3].upper()
    dissolved_fl = f"{workspace_gdb}\\{prefix}_Dis"
    nc_table = f"{workspace_gdb}\\{prefix}_Nc"

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS IN ANALYTICAL GRID ALREADY EXIST IN GRID TABLE
    # ----------------------------------------------------------------------
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    field_raw = (prefix + "_P_Nc").upper()
    field_std = ("Std_" + landscape_attr + "_P_Nc").upper()

    if field_raw in existing_fields or field_std in existing_fields:
        arcpy.AddError(
            f"Fields '{prefix}_P_Nc' and/or 'Std_{landscape_attr}_P_Nc' already exist "
            f"in the analytical grid attribute table.\n"
            f"Please remove these fields before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # 1. Assigning each point feature (geosite) the identifier (OBJECTID)
    #    of the grid cell (statistical zone) in which it is located.
    #    The OBJECTID is assigned to the NEAR_FID attribute of the point feature class
    # ----------------------------------------------------------------------
    arcpy.analysis.Near(landscape_fl, grid_fl)

    # ----------------------------------------------------------------------
    # 2. Dissolve points by category within each cell of the analytical grid
    # ----------------------------------------------------------------------
    arcpy.management.Dissolve(landscape_fl, dissolved_fl, [landscape_attr, "NEAR_FID"])

    # ----------------------------------------------------------------------
    # 3. Calculate the frequency of point category groups within each cell of the analytical grid
    # ----------------------------------------------------------------------
    arcpy.analysis.Frequency(dissolved_fl, nc_table, "NEAR_FID")

    # ----------------------------------------------------------------------
    # 4. Standardization (Min-Max)
    # ----------------------------------------------------------------------
    arcpy.management.StandardizeField(nc_table, "FREQUENCY", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 5. Join results back to the grid layer
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(grid_fl, grid_id_field, nc_table, "NEAR_FID",["FREQUENCY", "FREQUENCY_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 6. Rename table attributes
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "FREQUENCY", prefix + "_P_Nc", landscape_fl + "_P_Nc")
    arcpy.management.AlterField(grid_fl, "FREQUENCY_MIN_MAX", prefix + "_P_Nc_MM", "Std_" + landscape_fl + "_A_Nc")

    # ----------------------------------------------------------------------
    # 7. Cleanup
    # ----------------------------------------------------------------------

    arcpy.management.DeleteField(landscape_fl, ["NEAR_FID", "NEAR_DIST"])

    for fl in (dissolved_fl, nc_table):
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