# Geodiversity Tool L_Tl
# Calculates the total length of line features of a selected landscape feature
# within each polygon of an analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2026-01-05

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)      # Line feature layer
    grid_fl = arcpy.GetParameterAsText(1)           # Analytical grid layer
    grid_id_field = arcpy.GetParameterAsText(2)     # Grid ID (usually OBJECTID)
    null_handling_mode = arcpy.GetParameterAsText(3)  # handling of empty grid cells

    # ----------------------------------------------------------------------
    # NULL HANDLING MODE
    # ----------------------------------------------------------------------
    use_zero_for_null = False

    arcpy.AddMessage(f"Null handling mode: {null_handling_mode}")

    if null_handling_mode == "Replace NULL with 0 (MIN=0, MAX from L_Tl)":
        use_zero_for_null = True
    elif null_handling_mode == "Keep NULL (MIN/MAX from observed L_Tl only)":
        use_zero_for_null = False
    else:
        arcpy.AddError("Unknown NULL handling mode selected.")
        raise Exception("Invalid NULL handling mode.")

    if use_zero_for_null:
        arcpy.AddMessage(
            "NULL handling mode: NULL values will be replaced with 0. "
            "Standardization uses fixed MIN = 0 and MAX from observed Lines_Length values."
        )
    else:
        arcpy.AddMessage(
            "NULL handling mode: NULL values preserved. "
            "Standardization uses true MIN–MAX range of observed Lines_Length values."
        )

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX, INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()

    stat_zone_field_ID = "StatZoneID"
    intersect_fc = f"memory\\{prefix}_Int"
    dissolved_fc = f"{workspace_gdb}\\{prefix}_Dis"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_LTl"
    output_index_alias = f"{prefix}_L_Tl"
    std_output_index_name = f"{prefix}_LTl_MM"
    std_output_index_alias = f"Std_{prefix}_L_Tl"

    # ----------------------------------------------------------------------
    # REMOVE LOCKS
    # ----------------------------------------------------------------------
    try:
        arcpy.AddMessage("Removing existing locks...")
        arcpy.management.RemoveLocks(landscape_fl)
        arcpy.management.RemoveLocks(grid_fl)
    except:
        pass

    # ----------------------------------------------------------------------
    # DELETE INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    for item in [intersect_fc, dissolved_fc]:
        if arcpy.Exists(item):
            try:
                arcpy.management.Delete(item)
                arcpy.AddMessage(f"Removed leftover dataset: {item}")
            except:
                arcpy.AddWarning(f"Could not remove leftover dataset: {item}")

    # ----------------------------------------------------------------------
    # CHECK FOR EXISTING OUTPUT FIELDS
    # ----------------------------------------------------------------------
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]
    if output_index_name.upper() in existing_fields or std_output_index_name.upper() in existing_fields:
        arcpy.AddError(
            f"Fields '{output_index_name.upper()}' and/or '{std_output_index_name.upper()}' already exist "
            "in the analytical grid. Remove them before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # 1. CREATE TEMPORARY STATISTICAL ZONE FIELD
    # ----------------------------------------------------------------------
    if stat_zone_field_ID in [f.name for f in arcpy.ListFields(grid_fl)]:
        arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)
    arcpy.management.AddField(grid_fl, stat_zone_field_ID, "LONG")
    arcpy.management.CalculateField(grid_fl, stat_zone_field_ID, f"!{grid_id_field}!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 2. INTERSECT LINES WITH GRID
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Intersecting landscape lines with the analytical grid...")
    arcpy.analysis.Intersect([landscape_fl, grid_fl], intersect_fc, "ALL")

    # ----------------------------------------------------------------------
    # 3. DISSOLVE LINES BY ZONE
    # ----------------------------------------------------------------------
    arcpy.management.Dissolve(intersect_fc, dissolved_fc, stat_zone_field_ID)

    # ----------------------------------------------------------------------
    # 4. CREATE ATTRIBUTE FIELDS (RAW + STANDARDIZED)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Creating Lines_Length and Lines_Length_MIN_MAX fields...")

    arcpy.management.AddField(dissolved_fc, "Lines_Length", "DOUBLE")
    arcpy.management.CalculateField(dissolved_fc, "Lines_Length", "!Shape_Length!", "PYTHON3")

    arcpy.management.AddField(dissolved_fc, "Lines_Length_MIN_MAX", "DOUBLE")

    # ----------------------------------------------------------------------
    # 5. MIN–MAX STANDARDIZATION
    # ----------------------------------------------------------------------
    lines_values = [row[0] for row in arcpy.da.SearchCursor(dissolved_fc, ["Lines_Length"]) if row[0] is not None]

    if not lines_values:
        min_lines = 0
        max_lines = 0
        arcpy.AddWarning("No valid Lines_Length values found. MIN/MAX set to 0.")
    else:
        min_lines = 0 if use_zero_for_null else min(lines_values)
        max_lines = max(lines_values)
        arcpy.AddMessage(f"Using MIN={min_lines} and MAX={max_lines} for standardization.")

    with arcpy.da.UpdateCursor(dissolved_fc, ["Lines_Length", "Lines_Length_MIN_MAX"]) as cursor:
        for row in cursor:
            val = row[0]
            if val is None:
                row[0] = 0 if use_zero_for_null else None
                row[1] = 0 if use_zero_for_null else None
            else:
                if max_lines == min_lines:
                    row[1] = 0
                else:
                    row[1] = val / max_lines if use_zero_for_null else (val - min_lines) / (max_lines - min_lines)
            cursor.updateRow(row)

    arcpy.AddMessage("Min–Max standardization completed successfully.")

    # ----------------------------------------------------------------------
    # 6. REMOVE OLD JOIN FIELDS FROM GRID
    # ----------------------------------------------------------------------
    for old_field in ["LINES_LENGTH", "LINES_LENGTH_MIN_MAX"]:
        if old_field in [f.name.upper() for f in arcpy.ListFields(grid_fl)]:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 7. JOIN RESULTS BACK TO GRID
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(
        grid_fl,
        stat_zone_field_ID,
        dissolved_fc,
        stat_zone_field_ID,
        ["Lines_Length", "Lines_Length_MIN_MAX"]
    )

    # ----------------------------------------------------------------------
    # 8. REPLACE NULLS WITH 0 IN GRID (OPTIONAL)
    # ----------------------------------------------------------------------
    if use_zero_for_null:
        arcpy.AddMessage("Replacing NULL values with 0 in the analytical grid fields...")
        with arcpy.da.UpdateCursor(grid_fl, ["Lines_Length", "Lines_Length_MIN_MAX"]) as cursor:
            for row in cursor:
                if row[0] is None:
                    row[0] = 0
                if row[1] is None:
                    row[1] = 0
                cursor.updateRow(row)

    # ----------------------------------------------------------------------
    # 9. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "Lines_Length", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "Lines_Length_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 10. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Removing temporary zone field...")
    arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.AddMessage("Cleaning intermediate datasets...")
    for fc in (intersect_fc, dissolved_fc):
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
        arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("L_Tl calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("A geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("A Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
