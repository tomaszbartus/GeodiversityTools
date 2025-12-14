# Geodiversity Tool P_Nc
# The script calculates the number of point features (e.g. geosites) categories of a selected
# landscape feature within each polygon of the analytical grid
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2025-12-14

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)           # point feature layer
    landscape_attr = arcpy.GetParameterAsText(1)         # geosites category field
    grid_fl = arcpy.GetParameterAsText(2)                # grid layer
    grid_id_field = arcpy.GetParameterAsText(3)          # OBJECTID of the grid

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path

    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()
    dissolved_fc = f"{workspace_gdb}\\{prefix}_Dis"
    nc_table = f"{workspace_gdb}\\{prefix}_Nc"
    stats_table = f"in_memory\\{prefix}_stats_temp"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_PNc"
    output_index_alias = f"{prefix}_P_Nc"
    std_output_index_name = f"{prefix}_PNc_MM"
    std_output_index_alias = f"Std_{prefix}_P_Nc"

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
        dissolved_fc,
        nc_table
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
    # 1. Assigning each point feature (geosite) the identifier (OBJECTID)
    #    of the grid cell (statistical zone) in which it is located.
    #    The OBJECTID is assigned to the NEAR_FID attribute of the point feature class
    # ----------------------------------------------------------------------
    arcpy.analysis.Near(landscape_fl, grid_fl)

    # ----------------------------------------------------------------------
    # 2. DISSOLVE points by category within each cell of the analytical grid
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Dissolving the landscape points by category...")
    arcpy.management.Dissolve(landscape_fl, dissolved_fc, [landscape_attr, "NEAR_FID"])

    # ----------------------------------------------------------------------
    # 3. CALCULATE the frequency of point category groups within each cell of the analytical grid
    # ----------------------------------------------------------------------
    arcpy.analysis.Frequency(dissolved_fc, nc_table, ["NEAR_FID"])

    # ----------------------------------------------------------------------
    # 4. SAFE MIN–MAX STANDARDIZATION FOR Nc (in_memory version)
    # If MIN(Nc) == MAX(Nc), assign 0 to all rows
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing P_Nc (Min-Max)...")

    # 4.1. Calculate statistics (min and max of Nc) using in_memory table
    arcpy.analysis.Statistics(nc_table, stats_table, [["FREQUENCY", "MIN"], ["FREQUENCY", "MAX"]])

    # 4.2. Read min/max values
    with arcpy.da.SearchCursor(stats_table, ["MIN_FREQUENCY", "MAX_FREQUENCY"]) as cursor:
        for row in cursor:
            min_FREQUENCY = float(row[0])
            max_FREQUENCY = float(row[1])

    # 4.3. Delete temporary in_memory table
    arcpy.management.Delete(stats_table)

    # 4.4. Case 1 — all values identical → assign 0 to all records
    if min_FREQUENCY == max_FREQUENCY:
        arcpy.AddMessage(
            "All Nc values are identical (MIN = MAX). "
            "Skipping Min–Max standardization. Assigning 0 to FREQUENCY_MIN_MAX."
        )

        # Add new field for standardized values
        if "FREQUENCY_MIN_MAX" not in [f.name for f in arcpy.ListFields(nc_table)]:
            arcpy.management.AddField(nc_table, "FREQUENCY_MIN_MAX", "DOUBLE")

        # Set all FREQUENCY_MIN_MAX values to 0
        arcpy.management.CalculateField(nc_table, "FREQUENCY_MIN_MAX", 0, "PYTHON3")

    # 4.5. Case 2 — normal standardization
    else:
        arcpy.AddMessage("Performing Min–Max standardization of Nc...")
        arcpy.management.StandardizeField(nc_table, "FREQUENCY", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 5. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
    # ----------------------------------------------------------------------
    fields_to_check = ["FREQUENCY", "FREQUENCY_MIN_MAX"]
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    # Checking whether any fields need to be removed at all
    fields_to_remove = [f for f in fields_to_check if f in existing_fields]

    if fields_to_remove:
        arcpy.AddMessage("Removing old join fields from the grid...")
        for old_field in fields_to_remove:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 6. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, grid_id_field, nc_table, "NEAR_FID",["FREQUENCY", "FREQUENCY_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 7. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "FREQUENCY", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "FREQUENCY_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 8. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    arcpy.management.DeleteField(landscape_fl, ["NEAR_FID", "NEAR_DIST"])

    for fl in (dissolved_fc, nc_table):
        if arcpy.Exists(fl):
            arcpy.management.Delete(fl)

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("P_Nc calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()