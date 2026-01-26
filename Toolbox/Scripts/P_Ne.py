# Geodiversity Tool P_Ne
# Calculates the number of geosites (point features)
# within each polygon of the analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2026-01-26

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True
# Prevent Z-coordinate and M-coordinate inheritance in feature classes
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)          # point feature layer
    grid_fl = arcpy.GetParameterAsText(1)               # analytical grid
    grid_id_field = arcpy.GetParameterAsText(2)         # grid ID field
    null_handling_mode = arcpy.GetParameterAsText(3)    # handling of empty grid cells

    # ----------------------------------------------------------------------
    # NULL HANDLING MODE
    # ----------------------------------------------------------------------
    arcpy.AddMessage(f"Null handling mode: {null_handling_mode}")
    use_zero_for_null = False

    if null_handling_mode == "Replace NULL with 0 (MIN=0, MAX from Ne)":
        use_zero_for_null = True
    elif null_handling_mode == "Keep NULL (MIN/MAX from observed Ne only)":
        use_zero_for_null = False
    else:
        arcpy.AddError("Unknown NULL handling mode selected.")
        raise Exception("Invalid NULL handling mode.")

    if use_zero_for_null:
        arcpy.AddMessage(
            "NULL handling mode: NULL values replaced with 0. "
            "Standardization uses fixed MIN = 0 and MAX from observed Ne values."
        )
    else:
        arcpy.AddMessage(
            "NULL handling mode: NULL values preserved. "
            "Standardization uses true MIN–MAX range of observed Ne values."
        )

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX, FIELDS AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    #prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()
    desc_land = arcpy.Describe(landscape_fl)        # get the layer's metadata
    base_name = desc_land.name                      # FC name without the path
    prefix = arcpy.ValidateTableName(
        base_name[:3].upper(),                      # first 3 letters in uppercase
        workspace_gdb                               # validate for the target geodatabase
    )

    stat_zone_field_ID = "StatZoneID"
    intersect_fc = f"{workspace_gdb}\\{prefix}_Ne_Int"

    # ----------------------------------------------------------------------
    # VALIDATE DATA FORMATS (BLOCK SHAPEFILES)
    # ----------------------------------------------------------------------
    def check_gdb_feature(fc):
        desc = arcpy.Describe(fc)
        if desc.dataType == "ShapeFile" or desc.catalogPath.lower().endswith(".shp"):
            arcpy.AddError(f"Error: Layer '{desc.name}' is a Shapefile.")
            arcpy.AddError("Geodiversity Tools require GDB feature classes.")
            raise arcpy.ExecuteError

    check_gdb_feature(landscape_fl)
    check_gdb_feature(grid_fl)

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
    output_index_name = f"{prefix}_PNe"
    output_index_alias = f"{prefix}_P_Ne"
    std_output_index_name = f"{prefix}_PNe_MM"
    std_output_index_alias = f"Std_{prefix}_P_Ne"

    # ----------------------------------------------------------------------
    # FORCE REMOVAL OF LOCKS AND CLEAN INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    try:
        arcpy.AddMessage("Removing existing locks...")
        arcpy.management.RemoveLocks(landscape_fl)
        arcpy.management.RemoveLocks(grid_fl)
    except:
        pass

    if arcpy.Exists(intersect_fc):
        arcpy.management.Delete(intersect_fc)
        arcpy.AddMessage(f"Removed leftover dataset: {intersect_fc}")

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS ALREADY EXIST IN GRID TABLE
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Checking if the output fields already exist...")
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]
    if output_index_name.upper() in existing_fields or std_output_index_name.upper() in existing_fields:
        arcpy.AddError(
            f"Fields '{output_index_name.upper()}' and/or '{std_output_index_name.upper()}' "
            "already exist in the analytical grid. Remove these fields before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # 1. CREATE TEMPORARY STATISTICAL ZONE FIELD ID
    # ----------------------------------------------------------------------
    arcpy.AddMessage(f"Creating temporary zone field: {stat_zone_field_ID}...")
    if stat_zone_field_ID in [f.name for f in arcpy.ListFields(grid_fl)]:
        arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)
    arcpy.management.AddField(grid_fl, stat_zone_field_ID, "LONG")
    arcpy.management.CalculateField(grid_fl, stat_zone_field_ID, f"!{grid_id_field}!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 2. SPATIAL JOIN – count points inside each grid cell
    # ----------------------------------------------------------------------
    arcpy.AddMessage("SPATIALLY JOINING landscape points with the analytical grid...")
    arcpy.analysis.SpatialJoin(
        grid_fl, landscape_fl, intersect_fc,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", "", "INTERSECT"
    )
    arcpy.management.AlterField(intersect_fc, "Join_Count", "Ne")

    # ----------------------------------------------------------------------
    # 3. OPTIONAL: convert zeros to NULL if user wants to preserve empty cells
    # ----------------------------------------------------------------------
    if not use_zero_for_null:
        arcpy.AddMessage("Replacing 0 values with NULL to preserve empty cells...")
        with arcpy.da.UpdateCursor(intersect_fc, ["Ne"]) as cursor:
            for row in cursor:
                if row[0] == 0:
                    row[0] = None
                    cursor.updateRow(row)

    # ----------------------------------------------------------------------
    # 4. SAFE MIN–MAX STANDARDIZATION FOR Ne
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing Ne (Min–Max) with proper handling of empty cells...")

    if "Ne_MIN_MAX" not in [f.name for f in arcpy.ListFields(intersect_fc)]:
        arcpy.management.AddField(intersect_fc, "Ne_MIN_MAX", "DOUBLE")
        arcpy.AddMessage("Added field 'Ne_MIN_MAX' for standardized values.")

    ne_values = [row[0] for row in arcpy.da.SearchCursor(intersect_fc, ["Ne"]) if row[0] is not None]

    if not ne_values:
        min_ne = 0
        max_ne = 0
        arcpy.AddWarning("No valid Ne values found. Setting MIN and MAX to 0.")
    else:
        if use_zero_for_null:
            min_ne = 0
            max_ne = max(ne_values)
            arcpy.AddMessage(f"Using fixed MIN=0 and MAX={max_ne} for standardization (NULLs replaced with 0).")
        else:
            min_ne = min(ne_values)
            max_ne = max(ne_values)
            arcpy.AddMessage(f"Using observed MIN={min_ne} and MAX={max_ne} for standardization (NULLs preserved).")

    with arcpy.da.UpdateCursor(intersect_fc, ["Ne", "Ne_MIN_MAX"]) as cursor:
        if max_ne == min_ne:
            arcpy.AddMessage(
                "All Ne values are identical (MIN = MAX). "
                "Skipping Min–Max standardization. Assigning 0 to all Ne_MIN_MAX."
            )
            for row in cursor:
                row[1] = 0
                cursor.updateRow(row)
        else:
            arcpy.AddMessage("Performing Min–Max standardization of Ne...")
            for row in cursor:
                value = row[0]
                if value is None:
                    row[1] = None  # Preserve NULL
                else:
                    row[1] = (value - min_ne) / (max_ne - min_ne) if not use_zero_for_null else value / max_ne
                cursor.updateRow(row)

    arcpy.AddMessage("Min–Max standardization completed successfully.")

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
