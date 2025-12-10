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
    grid_fl = arcpy.GetParameterAsText(1)          # analytical grid
    grid_id_field = arcpy.GetParameterAsText(2)    # grid ID field

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
    arcpy.analysis.SpatialJoin(grid_fl, landscape_fl, intersect_fc, "JOIN_ONE_TO_ONE", "KEEP_ALL", "", "INTERSECT")

    # Rename Join_Count to Ne
    arcpy.management.AlterField(intersect_fc, "Join_Count", "Ne")

    # -----------------------------------------------------------
    # 2. SAFE MIN–MAX STANDARDIZATION FOR Ne
    # If MIN(Ne) == MAX(Ne), assign 0 to all rows
    # -----------------------------------------------------------

    # 2.1. Calculate statistics (min and max of Ne)
    stats_table = "stats_temp"
    arcpy.analysis.Statistics(intersect_fc, stats_table,[["Ne", "MIN"], ["Ne", "MAX"]])

    # Read min/max values
    with arcpy.da.SearchCursor(stats_table, ["MIN_Ne", "MAX_Ne"]) as cursor:
        for row in cursor:
            min_ne = float(row[0])
            max_ne = float(row[1])

    # Remove temporary stats table
    arcpy.management.Delete(stats_table)

    # 2.2. Case 1 — all values identical → assign 0 to all records
    if min_ne == max_ne:
        arcpy.AddMessage(
            "All Ne values are identical (MIN = MAX). "
            "Skipping Min–Max standardization. Assigning 0 to Ne_MIN_MAX."
        )

        # Add new field for standardized values
        if "Ne_MIN_MAX" not in [f.name for f in arcpy.ListFields(intersect_fc)]:
            arcpy.management.AddField(intersect_fc, "Ne_MIN_MAX", "DOUBLE")

        # Set all Ne_MIN_MAX values to 0
        arcpy.management.CalculateField(intersect_fc,"Ne_MIN_MAX",0,"PYTHON3")

    # 2.3. Case 2 — normal standardization
    else:
        arcpy.AddMessage("Performing Min–Max standardization of Ne.")

        arcpy.management.StandardizeField(intersect_fc,"Ne", "MIN-MAX",0, 1)

    # ----------------------------------------------------------------------
    # 3. Ensure old join fields are removed from grid
    # ----------------------------------------------------------------------
    for old_field in ["Ne", "Ne_MIN_MAX"]:
        if old_field in [f.name for f in arcpy.ListFields(grid_fl)]:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 4. JOIN BACK TO GRID
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(grid_fl, grid_id_field, intersect_fc, grid_id_field, ["Ne", "Ne_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 5. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "Ne", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "Ne_MIN_MAX", std_output_index_name, std_output_index_alias)

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
