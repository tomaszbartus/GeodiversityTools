# Geodiversity Tool P_Ne
# Calculates the number of geosites (point features)
# within each polygon of the analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2025-12-14

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)     # point feature layer
    grid_fl = arcpy.GetParameterAsText(1)          # analytical grid
    grid_id_field = arcpy.GetParameterAsText(2)    # grid ID field

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX, FIELDS AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()

    stat_zone_field_ID = "StatZoneID"
    intersect_fc = f"{workspace_gdb}\\{prefix}_Ne_Int"
    stats_table = f"memory\\{prefix}_stats_temp"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_PNe"
    output_index_alias = f"{prefix}_P_Ne"
    std_output_index_name = f"{prefix}_PNe_MM"
    std_output_index_alias = f"Std_{prefix}_P_Ne"

    # ----------------------------------------------------------------------
    # FORCE REMOVAL OF LOCKS FROM INPUT DATASETS
    # ----------------------------------------------------------------------
    try:
        arcpy.AddMessage("Removing existing locks...")
        arcpy.management.RemoveLocks(landscape_fl)
        arcpy.management.RemoveLocks(grid_fl)
    except:
        pass

    # ----------------------------------------------------------------------
    # CHECK IF INTERMEDIATE DATASETS ALREADY EXIST IN GDB
    # ----------------------------------------------------------------------
    intermediate_items = [
        intersect_fc
    ]

    arcpy.AddMessage("Checking for leftover intermediate datasets...")

    for item in intermediate_items:
        if arcpy.Exists(item):
            try:
                arcpy.management.Delete(item)
                arcpy.AddMessage(f"Removed leftover dataset: {item}")
            except:
                arcpy.AddWarning(f"Could not remove leftover dataset: {item}")

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS ALREADY EXIST IN GRID TABLE
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Checking if the output fields already exist...")
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    if output_index_name.upper() in existing_fields or std_output_index_name.upper() in existing_fields:
        arcpy.AddError(
            f"Fields '{output_index_name.upper()}' and/or '{std_output_index_name.upper()}' "
            f"already exist in the analytical grid.\n"
            f"Remove these fields before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # 1. CREATE TEMPORARY STATISTICAL ZONE FIELD ID TO AVOID OBJECTID_1 CONFLICTS
    # ----------------------------------------------------------------------
    arcpy.AddMessage(f"Creating temporary zone field: {stat_zone_field_ID}...")

    # Remove if exist in grid_fl
    if stat_zone_field_ID in [f.name for f in arcpy.ListFields(grid_fl)]:
        arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.management.AddField(grid_fl, stat_zone_field_ID, "LONG")
    arcpy.management.CalculateField(grid_fl, stat_zone_field_ID, f"!{grid_id_field}!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 2. SPATIAL JOIN – count points inside each grid cell
    # ----------------------------------------------------------------------
    arcpy.AddMessage("SPATIALLY JOINING landscape points with the analytical grid...")
    arcpy.analysis.SpatialJoin(grid_fl, landscape_fl, intersect_fc, "JOIN_ONE_TO_ONE", "KEEP_ALL", "", "INTERSECT")

    # Rename Join_Count to Ne
    arcpy.management.AlterField(intersect_fc, "Join_Count", "Ne")

    # -----------------------------------------------------------
    # 3. SAFE MIN–MAX STANDARDIZATION FOR Ne (in_memory version)
    # If MIN(Ne) == MAX(Ne), assign 0 to all rows
    # -----------------------------------------------------------

    # 3.1. Calculate statistics (min and max of Ne) using in_memory table
    arcpy.analysis.Statistics(intersect_fc, stats_table, [["Ne", "MIN"], ["Ne", "MAX"]])

    # 3.2. Read min/max values
    with arcpy.da.SearchCursor(stats_table, ["MIN_Ne", "MAX_Ne"]) as cursor:
        for row in cursor:
            min_ne = float(row[0])
            max_ne = float(row[1])

    # 3.3. Delete temporary in_memory table
    arcpy.management.Delete(stats_table)

    # 3.4. Case 1 — all values identical → assign 0 to all records
    if min_ne == max_ne:
        arcpy.AddMessage(
            "All Ne values are identical (MIN = MAX). "
            "Skipping Min–Max standardization. Assigning 0 to Ne_MIN_MAX."
        )

        # Add new field for standardized values
        if "Ne_MIN_MAX" not in [f.name for f in arcpy.ListFields(intersect_fc)]:
            arcpy.management.AddField(intersect_fc, "Ne_MIN_MAX", "DOUBLE")

        # Set all Ne_MIN_MAX values to 0
        arcpy.management.CalculateField(intersect_fc, "Ne_MIN_MAX", 0, "PYTHON3")

    # 3.5. Case 2 — normal standardization
    else:
        arcpy.AddMessage("Performing Min–Max standardization of Ne...")
        arcpy.management.StandardizeField(intersect_fc, "Ne", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 4. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
    # ----------------------------------------------------------------------
    fields_to_check = ["NE", "NE_MIN_MAX"]
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
    arcpy.management.JoinField(grid_fl, stat_zone_field_ID, intersect_fc, stat_zone_field_ID, ["Ne", "Ne_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 6. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "Ne", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "Ne_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 7. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Removing temporary zone field...")
    arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.AddMessage("Cleaning intermediate datasets...")
    if arcpy.Exists(intersect_fc):
        arcpy.management.Delete(intersect_fc)

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
        arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("P_Ne calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
