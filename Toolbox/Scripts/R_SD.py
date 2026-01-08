# Geodiversity Tool R_SD (in_memory)
# Calculates the Standard Deviation (SD) for a selected landscape feature (raster)
# in each polygon of an analytical grid
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# Date: 2026-01-08

import arcpy

# Allow overwriting outputs
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    # 0 - Input RASTER, LINEAR landscape feature (continuous variable)
    # 1 - Analytical grid feature layer (polygon layer)
    # 2 - Analytical grid identification field (e.g. OBJECTID)
    landscape_ras = arcpy.GetParameterAsText(0)
    grid_fl = arcpy.GetParameterAsText(1)
    grid_id_field = arcpy.GetParameterAsText(2)

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX, FIELDS AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(grid_fl).path
    raster_base = arcpy.Describe(landscape_ras).baseName
    prefix = raster_base[:3].upper()

    stat_zone_field_ID = "StatZoneID"
    zonal_stat_table = fr"memory\{prefix}_ZONAL_STAT"
    stats_table = fr"memory\{prefix}_STD_STATS"

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
    output_index_name = f"{prefix}_RSD"
    output_index_alias = f"{prefix}_R_SD"
    std_output_index_name = f"{prefix}_RSD_MM"
    std_output_index_alias = f"Std_{prefix}_R_SD"

    # ----------------------------------------------------------------------
    # FORCE REMOVAL OF LOCKS FROM INPUT DATASETS
    # ----------------------------------------------------------------------
    try:
        arcpy.AddMessage("Removing existing locks...")
        arcpy.management.RemoveLocks(landscape_ras)
        arcpy.management.RemoveLocks(grid_fl)
    except:
        pass

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
    # 2. ZONAL STATISTICS AS TABLE
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating pixel SD within the analytical grid zones...")
    arcpy.sa.ZonalStatisticsAsTable(grid_fl, stat_zone_field_ID, landscape_ras, zonal_stat_table, "DATA", "STD")

    # ----------------------------------------------------------------------
    # 3. STANDARDIZE SD (MIN-MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing SD using manual Min-Max normalization...")
    #arcpy.management.StandardizeField(zonal_stat_table, "STD", "MIN-MAX", 0, 1) #Problems with standardize in in_memory mode

    # ----------------------------------------------------------------------
    # 3.1. CALCULATE MIN & MAX OF STD
    # ----------------------------------------------------------------------
    arcpy.analysis.Statistics(zonal_stat_table, stats_table, [["STD", "MIN"], ["STD", "MAX"]])

    with arcpy.da.SearchCursor(stats_table, ["MIN_STD", "MAX_STD"]) as cursor:
        min_std, max_std = next(cursor)

    arcpy.management.Delete(stats_table)

    # ----------------------------------------------------------------------
    # 3.2. CREATE MIN-MAX STANDARDIZED FIELD
    # ----------------------------------------------------------------------
    std_field_name = "STD_MM"
    arcpy.management.AddField(zonal_stat_table, std_field_name, "DOUBLE")

    if max_std == min_std:
        arcpy.AddWarning(
            "STD has constant value across all zones. "
            "Standardized values will be set to 0."
        )
        arcpy.management.CalculateField( zonal_stat_table, std_field_name,"0","PYTHON3")
    else:
        code_block = f"""
def minmax(val):
    return (val - {min_std}) / ({max_std} - {min_std})
"""

        arcpy.management.CalculateField(
            zonal_stat_table,
            std_field_name,
            "minmax(!STD!)",
            "PYTHON3",
            code_block
        )

    # ----------------------------------------------------------------------
    # 4. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
    # ----------------------------------------------------------------------
    fields_to_check = ["STD", std_field_name]
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
    arcpy.management.JoinField(grid_fl, stat_zone_field_ID, zonal_stat_table, stat_zone_field_ID,["STD", std_field_name])

    # ----------------------------------------------------------------------
    # 6. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "STD", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, std_field_name, std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 7. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Removing temporary zone field...")
    arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.AddMessage("Cleaning intermediate datasets...")
    for item in [zonal_stat_table]:
        if arcpy.Exists(item):
            try:
               arcpy.management.Delete(item)
            except Exception:
                arcpy.AddWarning(f"Could not delete intermediate dataset: {item}")

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
        arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("R_SD calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()