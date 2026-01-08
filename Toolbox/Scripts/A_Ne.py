# Geodiversity Tool A_Ne
# Calculates the number of landscape polygon feature elements within each polygon of an analytical grid
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2026-01-08

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)             # polygon FL
    grid_fl = arcpy.GetParameterAsText(1)                  # analytical grid FL
    grid_id_field = arcpy.GetParameterAsText(2)            # grid OBJECTID-like field

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX, FIELDS AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = landscape_fl[:3].upper()

    stat_zone_field_ID = "StatZoneID"
    intersect_fc = f"{workspace_gdb}\\{prefix}_Ne_Int"
    mts_fc       = f"{workspace_gdb}\\{prefix}_Ne_MtS"
    ne_table     = f"{workspace_gdb}\\{prefix}_Ne_Tab"
    stats_table = f"memory\\{prefix}_stats_temp"

    # ---------------------------------------------------------------------------
    # CHECK SPATIAL INTERSECTION OF EXTENTS
    # ---------------------------------------------------------------------------
    # Recalculate extents
    arcpy.AddMessage("Recalculating feature class extents...")
    arcpy.management.RecalculateFeatureClassExtent(landscape_fl)
    arcpy.management.RecalculateFeatureClassExtent(grid_fl)

    # Check if input layers contain features
    if int(arcpy.management.GetCount(landscape_fl)[0]) == 0:
        arcpy.AddError("Landscape features layer contains no features.")
        raise arcpy.ExecuteError

    if int(arcpy.management.GetCount(grid_fl)[0]) == 0:
        arcpy.AddError("Analytical grid layer contains no features.")
        raise arcpy.ExecuteError

    # Get updated extents
    ext_land = arcpy.Describe(landscape_fl).extent
    ext_grid = arcpy.Describe(grid_fl).extent

    # Check spatial intersection of extents
    # Two extents intersect if they are NOT disjoint
    if ext_land.disjoint(ext_grid):
        arcpy.AddError(
            "The landscape features layer does not spatially overlap "
            "with the analytical grid. Analysis cannot be performed."
        )
        raise arcpy.ExecuteError

    # Inform user
    arcpy.AddMessage("Input validation passed.")

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_ANe"
    output_index_alias = f"{prefix}_A_Ne"
    std_output_index_name = f"{prefix}_ANe_MM"
    std_output_index_alias = f"Std_{prefix}_A_Ne"

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
        intersect_fc,
        mts_fc,
        ne_table
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
            f"Please remove these fields before re-running the tool."
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
    # 2. INTERSECT LANDSCAPE POLYGONS WITH GRID FL (creates intersect_fc containing FID_<grid> for grouping)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Intersecting landscape polygons with the analytical grid...")
    arcpy.analysis.Intersect([landscape_fl, grid_fl], intersect_fc,"ALL")

    # ----------------------------------------------------------------------
    # 3. MULTIPART → SINGLEPART (create mts_fc - ..._Ne_MtS FC)
    # ----------------------------------------------------------------------
    arcpy.management.MultipartToSinglepart(intersect_fc, mts_fc)

    # ----------------------------------------------------------------------
    # 4. ADD Count FIELD and set = 1
    # ----------------------------------------------------------------------
    arcpy.management.AddField(mts_fc, "Count", "SHORT")

    with arcpy.da.UpdateCursor(mts_fc, ["Count"]) as cursor:
        for row in cursor:
            row[0] = 1
            cursor.updateRow(row)

    # ----------------------------------------------------------------------
    # 5. STATISTICS: count elements per grid cell
    # ----------------------------------------------------------------------
    #case_field = f"FID_{arcpy.Describe(grid_fl).name}"
    #case_field = "FID_" + grid_fl
    arcpy.analysis.Statistics(mts_fc, ne_table, [["Count", "SUM"]], stat_zone_field_ID)

    # ----------------------------------------------------------------------
    # 6. SAFE MIN–MAX STANDARDIZATION FOR Ne (in_memory version)
    # If MIN(Ne) == MAX(Ne), assign 0 to all rows
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing A_Ne (Min-Max)...")

    # 6.1. Calculate statistics (min and max of Ne) using in_memory table
    arcpy.analysis.Statistics(ne_table, stats_table, [["SUM_Count", "MIN"], ["SUM_Count", "MAX"]])

    # 6.2. Read min/max values
    with arcpy.da.SearchCursor(stats_table, ["MIN_SUM_Count", "MAX_SUM_Count"]) as cursor:
        for row in cursor:
            min_SUM_Count = float(row[0])
            max_SUM_Count = float(row[1])

    # 6.3. Delete temporary in_memory table
    arcpy.management.Delete(stats_table)

    # 6.4. Case 1 — all values identical → assign 0 to all records
    if min_SUM_Count == max_SUM_Count:
        arcpy.AddMessage(
            "All Ne values are identical (MIN = MAX). "
            "Skipping Min–Max standardization. Assigning 0 to SUM_Count_MIN_MAX."
        )

        # Add new field for standardized values
        if "SUM_Count_MIN_MAX" not in [f.name for f in arcpy.ListFields(ne_table)]:
            arcpy.management.AddField(ne_table, "SUM_Count_MIN_MAX", "DOUBLE")

        # Set all SUM_Count_MIN_MAX values to 0
        arcpy.management.CalculateField(ne_table, "SUM_Count_MIN_MAX", 0, "PYTHON3")

    # 6.5. Case 2 — normal standardization
    else:
        arcpy.AddMessage("Performing Min–Max standardization of Ne...")
        arcpy.management.StandardizeField(ne_table, "SUM_Count", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 7. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
    # ----------------------------------------------------------------------
    fields_to_check = ["SUM_COUNT", "SUM_COUNT_MIN_MAX"]
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    # Checking whether any fields need to be removed at all
    fields_to_remove = [f for f in fields_to_check if f in existing_fields]

    if fields_to_remove:
        arcpy.AddMessage("Removing old join fields from the grid...")
        for old_field in fields_to_remove:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 8. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, stat_zone_field_ID, ne_table, stat_zone_field_ID,["SUM_Count", "SUM_Count_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 9. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "SUM_Count", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "SUM_Count_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 10. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Removing temporary zone field...")
    arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.AddMessage("Cleaning intermediate datasets...")
    for fc in (intersect_fc, mts_fc, ne_table):
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
        arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("A_Ne calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
