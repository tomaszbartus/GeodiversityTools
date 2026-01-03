# Geodiversity Tool P_Nc
# The script calculates the number of point features (e.g. geosites) categories of a selected
# landscape feature within each polygon of the analytical grid
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2026-01-03

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
    grid_id_field = arcpy.GetParameterAsText(3)          # OBJECTID of the statistical zones
    null_handling_mode = arcpy.GetParameterAsText(4)     # handling of empty grid cells

    # ----------------------------------------------------------------------
    # NULL HANDLING MODE
    # ----------------------------------------------------------------------
    arcpy.AddMessage(f"Null handling mode: {null_handling_mode}")

    use_zero_for_null = False

    if null_handling_mode == "Replace NULL with 0 (MIN=0, MAX from Nc)":
        use_zero_for_null = True
    elif null_handling_mode == "Keep NULL (MIN/MAX from observed Nc only)":
        use_zero_for_null = False
    else:
        arcpy.AddError("Unknown NULL handling mode selected.")
        raise Exception("Invalid NULL handling mode.")

    if use_zero_for_null:
        arcpy.AddMessage(
            "NULL handling mode: NULL values replaced with 0. "
            "Standardization uses fixed MIN = 0 and MAX from observed Nc values."
        )
    else:
        arcpy.AddMessage(
            "NULL handling mode: NULL values preserved. "
            "Standardization uses true MIN–MAX range of observed Nc values."
        )

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX, FIELDS AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()

    stat_zone_field_ID = "StatZoneID"
    dissolved_fc = f"{workspace_gdb}\\{prefix}_Dis"
    nc_table = f"{workspace_gdb}\\{prefix}_Nc"
    stats_table = f"memory\\{prefix}_stats_temp"

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
    # 1. CREATE TEMPORARY STATISTICAL ZONE FIELD ID TO AVOID OBJECTID_1 CONFLICTS
    # ----------------------------------------------------------------------
    arcpy.AddMessage(f"Creating temporary zone field: {stat_zone_field_ID}...")

    # Remove if exist in grid_fl
    if stat_zone_field_ID in [f.name for f in arcpy.ListFields(grid_fl)]:
        arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.management.AddField(grid_fl, stat_zone_field_ID, "LONG")
    arcpy.management.CalculateField(grid_fl, stat_zone_field_ID, f"!{grid_id_field}!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 2. Assigning each point feature (geosite) the identifier (OBJECTID)
    #    of the grid cell (statistical zone) in which it is located.
    #    The OBJECTID is assigned to the NEAR_FID attribute of the point feature class
    # ----------------------------------------------------------------------
    arcpy.analysis.Near(landscape_fl, grid_fl)

    # ----------------------------------------------------------------------
    # 3. DISSOLVE points by category within each cell of the analytical grid
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Dissolving the landscape points by category...")
    arcpy.management.Dissolve(landscape_fl, dissolved_fc, [landscape_attr, "NEAR_FID"])

    # ----------------------------------------------------------------------
    # 4. CALCULATE the frequency of point category groups within each cell of the analytical grid
    # ----------------------------------------------------------------------
    arcpy.analysis.Frequency(dissolved_fc, nc_table, ["NEAR_FID"])

    # ----------------------------------------------------------------------
    # 4.1. Completing the nc_table with missing grid cells assigned FREQUENCY = 0
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Missing cells added to nc_table FREQUENCY=0...")

    # Retrieval of all analytical grid cell identifiers (StatZoneID)
    all_near_fid = []
    with arcpy.da.SearchCursor(grid_fl, [stat_zone_field_ID]) as cursor:
        for row in cursor:
            all_near_fid.append(row[0])

    # Retrieval of all NEAR_FID grid cell identifiers present in nc_table (only cells containing geosites)
    existing_near_fid = []
    with arcpy.da.SearchCursor(nc_table, ["NEAR_FID"]) as cursor:
        for row in cursor:
            existing_near_fid.append(row[0])

    # Rows present in the analytical grid table but not present in nc_table
    missing_near_fid = set(all_near_fid) - set(existing_near_fid)

    # Adding missing rows to nc_table according to NULL handling mode
    if missing_near_fid:
        with arcpy.da.InsertCursor(nc_table, ["NEAR_FID", "FREQUENCY"]) as cursor:
            for fid in missing_near_fid:
                if use_zero_for_null:
                    cursor.insertRow([fid, 0])  # replace missing with 0
                else:
                    cursor.insertRow([fid, None])  # keep as NULL

    arcpy.AddMessage(f"Added {len(missing_near_fid)} missing records with FREQUENCY = 0")

    # ----------------------------------------------------------------------
    # 5. SAFE MIN–MAX STANDARDIZATION FOR Nc
    # Statistical zones without geosites → Std_P_Nc = 0
    # MIN for standardization is fixed at 0 (no geosites in the cell)
    # MAX for standardization is taken from the actual observed values
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing P_Nc (Min-Max) with proper handling of empty cells...")

    # 5.1. Handle NULL FREQUENCY values according to user choice
    with arcpy.da.UpdateCursor(nc_table, ["FREQUENCY"]) as cursor:
        for row in cursor:
            if row[0] is None:
                if use_zero_for_null:
                    row[0] = 0  # user-selected: NULL → 0
                    cursor.updateRow(row)
                else:
                    pass  # user-selected: keep NULL

    # 5.2. Calculate MIN and MAX for standardization according to user choice
    frequencies = []

    with arcpy.da.SearchCursor(nc_table, ["FREQUENCY"]) as cursor:
        for row in cursor:
            if row[0] is not None:
                frequencies.append(row[0])

    if not frequencies:
        min_FREQUENCY = 0
        max_FREQUENCY = 0
    else:
        if use_zero_for_null:
            min_FREQUENCY = 0
            max_FREQUENCY = max(frequencies)
        else:
            min_FREQUENCY = min(frequencies)
            max_FREQUENCY = max(frequencies)

    # 5.3. Add field for standardized values (if it does not exist yet)
    if "FREQUENCY_MIN_MAX" not in [f.name for f in arcpy.ListFields(nc_table)]:
        arcpy.management.AddField(nc_table, "FREQUENCY_MIN_MAX", "DOUBLE")

    # 5.4. Apply Min–Max standardization according to selected mode
    with arcpy.da.UpdateCursor(nc_table, ["FREQUENCY", "FREQUENCY_MIN_MAX"]) as cursor:

        if max_FREQUENCY == min_FREQUENCY:
            # Degenerate case – no variability
            for row in cursor:
                row[1] = 0
                cursor.updateRow(row)

        else:
            for row in cursor:
                value = row[0]

                if value is None:
                    # Preserve NULLs if user chose so
                    if use_zero_for_null:
                        value = 0
                    else:
                        row[1] = None
                        cursor.updateRow(row)
                        continue

                if use_zero_for_null:
                    # MIN fixed at 0
                    row[1] = value / max_FREQUENCY
                else:
                    # Classical Min–Max
                    row[1] = (value - min_FREQUENCY) / (max_FREQUENCY - min_FREQUENCY)

                cursor.updateRow(row)

    arcpy.AddMessage("Standardization completed.")

    # ----------------------------------------------------------------------
    # 6. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
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
    # 7. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, stat_zone_field_ID, nc_table, "NEAR_FID",["FREQUENCY", "FREQUENCY_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 8. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "FREQUENCY", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "FREQUENCY_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 9. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Removing temporary zone field...")
    arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.AddMessage("Cleaning intermediate datasets...")
    arcpy.management.DeleteField(landscape_fl, ["NEAR_FID", "NEAR_DIST"])

    for fl in (dissolved_fc, nc_table):
        if arcpy.Exists(fl):
            arcpy.management.Delete(fl)

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
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