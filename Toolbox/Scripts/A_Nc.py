# Geodiversity Tool A_Nc
# Calculates the number of polygon feature categories of a selected landscape feature
# within each polygon of an analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2026-01-08

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)      # Polygon feature layer
    landscape_attr = arcpy.GetParameterAsText(1)    # Category field
    grid_fl = arcpy.GetParameterAsText(2)           # Analytical grid layer
    grid_id_field = arcpy.GetParameterAsText(3)     # Grid ID (usually OBJECTID)

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX, FIELDS AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = landscape_attr[:3].upper()

    stat_zone_field_ID = "StatZoneID"
    dissolved_fl = f"memory\\{prefix}_Dis"
    nc_fl = f"{workspace_gdb}\\{prefix}_Nc"
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
    output_index_name = f"{prefix}_ANc"
    output_index_alias = f"{prefix}_A_Nc"
    std_output_index_name = f"{prefix}_ANc_MM"
    std_output_index_alias = f"Std_{prefix}_A_Nc"

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
        nc_fl
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
    # 2. DISSOLVE LANDSCAPE POLYGONS BY CATEGORY
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Dissolving the landscape polygons by category...")
    arcpy.management.Dissolve(landscape_fl, dissolved_fl, landscape_attr)

    # ----------------------------------------------------------------------
    # 3. SPATIAL JOIN: count dissolved polygons intersecting each grid cell
    # NOTE: field_mapping not required here (default behavior is correct)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Spatially joining landscape polygons with the analytical grid...")
    arcpy.analysis.SpatialJoin(
        grid_fl, dissolved_fl, nc_fl,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", "", "INTERSECT"
    )

    # -----------------------------------------------------------
    # 4. SAFE MIN–MAX STANDARDIZATION FOR Nc (in_memory version)
    # If MIN(Nc) == MAX(Nc), assign 0 to all rows
    # -----------------------------------------------------------
    arcpy.AddMessage("Standardizing A_Nc (Min-Max)...")

    # 4.1. Calculate statistics (min and max of Nc) using in_memory table
    arcpy.analysis.Statistics(nc_fl, stats_table, [["Join_Count", "MIN"], ["Join_Count", "MAX"]])

    # 4.2. Read min/max values
    with arcpy.da.SearchCursor(stats_table, ["MIN_Join_Count", "MAX_Join_Count"]) as cursor:
        for row in cursor:
            min_Join_Count = float(row[0])
            max_Join_Count = float(row[1])

    # 4.3. Delete temporary in_memory table
    arcpy.management.Delete(stats_table)

    # 4.4. Case 1 — all values identical → assign 0 to all records
    if min_Join_Count == max_Join_Count:
        arcpy.AddMessage(
            "All Nc values are identical (MIN = MAX). "
            "Skipping Min–Max standardization. Assigning 0 to Join_Count_MIN_MAX."
        )

        # Add new field for standardized values
        if "Join_Count_MIN_MAX" not in [f.name for f in arcpy.ListFields(nc_fl)]:
            arcpy.management.AddField(nc_fl, "Join_Count_MIN_MAX", "DOUBLE")

        # Set all Join_Count_MIN_MAX values to 0
        arcpy.management.CalculateField(nc_fl, "Join_Count_MIN_MAX", 0, "PYTHON3")

    # 4.5. Case 2 — normal standardization
    else:
        arcpy.AddMessage("Performing Min–Max standardization of Join_Count...")
        arcpy.management.StandardizeField(nc_fl, "Join_Count", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 5. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
    # ----------------------------------------------------------------------
    fields_to_check = ["JOIN_COUNT", "JOIN_COUNT_MIN_MAX"]
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
    arcpy.management.JoinField(
        grid_fl, stat_zone_field_ID, nc_fl, stat_zone_field_ID,
        ["Join_Count", "Join_Count_MIN_MAX"]
    )

    # ----------------------------------------------------------------------
    # 7. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "Join_Count", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "Join_Count_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 8. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Removing temporary zone field...")
    arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.AddMessage("Cleaning intermediate datasets...")
    for fl in (dissolved_fl, nc_fl, stats_table):
        try:
            if arcpy.Exists(fl):
                arcpy.management.Delete(fl)
        except:
            arcpy.AddWarning(f"Could not delete intermediate dataset: {fl}")

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
        arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("A_Nc calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("A geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("A Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()