# Geodiversity Tool P_Hu
# Calculates the unit entropy (Hu) point feature layer within each polygon of the analytical grid
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2026-01-08

import arcpy
import math

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
    intersect_fc = f"{workspace_gdb}\\{prefix}_Hu_Int"
    tabulate_intersection_table = f"{workspace_gdb}\\{prefix}_Hu_Ti_Tbl"
    Hu_table = f"{workspace_gdb}\\{prefix}_Hu_Tbl"
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
    output_index_name = f"{prefix}_PHu"
    output_index_alias = f"{prefix}_P_Hu"
    std_output_index_name = f"{prefix}_PHu_MM"
    std_output_index_alias = f"Std_{prefix}_P_Hu"

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
        tabulate_intersection_table,
        Hu_table
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
            f"Fields '{output_index_name.upper()}' already exist "
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
    # 2. SPATIAL JOIN
    # ----------------------------------------------------------------------
    arcpy.AddMessage("SPATIALLY JOINING landscape points with the analytical grid...")
    arcpy.analysis.SpatialJoin(grid_fl, landscape_fl, intersect_fc, "JOIN_ONE_TO_ONE","KEEP_ALL", "", "INTERSECT")

    arcpy.management.AlterField(intersect_fc, "Join_Count", "Ne")

    # ----------------------------------------------------------------------
    # 3. TABULATE INTERSECTION
    # Funkcja tworzy tabelę złożoną z kolumn: 1) ID komórki grida, 2) wartość kategorii, 3) liczby punktów tej kategorii (PNT_COUNT)
    # ----------------------------------------------------------------------
    #arcpy.analysis.TabulateIntersection(grid_fl, grid_id_field, landscape_fl, tabulate_intersection_table, landscape_attr)
    arcpy.analysis.TabulateIntersection(grid_fl, stat_zone_field_ID, landscape_fl, tabulate_intersection_table, landscape_attr)

    # ----------------------------------------------------------------------
    # 4. q_i = PNT_COUNT / Ne
    # ----------------------------------------------------------------------
    # Add new attribute Ne to the tabulate_intersection_table
    #arcpy.management.JoinField(tabulate_intersection_table, f"{grid_id_field}_1", intersect_fc, grid_id_field,["Ne"])
    arcpy.management.JoinField(tabulate_intersection_table, stat_zone_field_ID, intersect_fc, stat_zone_field_ID, ["Ne"])

    # Add new attribute q_i to the tabulate_intersection_table
    arcpy.management.AddField(tabulate_intersection_table, "q_i", "DOUBLE")

    # CALCULATE q_i
    arcpy.management.CalculateField(tabulate_intersection_table,"q_i","(!PNT_COUNT! / !Ne!) if !Ne! > 0 else 0","PYTHON3")

    # ----------------------------------------------------------------------
    # 5. CALCULATE UNIT ENTROPY H_i = -(q_i * ln(q_i))
    # ----------------------------------------------------------------------
    arcpy.management.AddField(tabulate_intersection_table, "H_i", "DOUBLE")
    arcpy.management.CalculateField(tabulate_intersection_table,"H_i","-(!q_i! * math.log(!q_i!)) if !q_i! > 0 else 0","PYTHON3")

    # ----------------------------------------------------------------------
    # 6. SUMMARIZE ALL H_i -- use the grid ID field name present in the tabulate table (usually grid_id + "_1")
    # ----------------------------------------------------------------------
    #arcpy.analysis.Statistics(tabulate_intersection_table, Hu_table,[["H_i", "SUM"]], f"{grid_id_field}_1")
    arcpy.analysis.Statistics(tabulate_intersection_table, Hu_table, [["H_i", "SUM"]], stat_zone_field_ID)

    # ----------------------------------------------------------------------
    # 7. SAFE MIN–MAX STANDARDIZATION FOR Hu (memory version)
    # If MIN(Hu) == MAX(Hu), assign 0 to all rows
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing P_Hu (Min-Max)...")

    # 7.1. Calculate statistics (min and max of SUM_H_i) using memory table
    arcpy.analysis.Statistics(Hu_table, stats_table, [["SUM_H_i", "MIN"], ["SUM_H_i", "MAX"]])

    # 7.2. Read min/max values
    with arcpy.da.SearchCursor(stats_table, ["MIN_SUM_H_i", "MAX_SUM_H_i"]) as cursor:
        for row in cursor:
            min_SUM_H_i = float(row[0])
            max_SUM_H_i = float(row[1])

    # 7.3. Delete temporary in_memory table
    arcpy.management.Delete(stats_table)

    # 7.4. Case 1 — all values identical → assign 0 to all records
    if min_SUM_H_i == max_SUM_H_i:
        arcpy.AddMessage(
            "All Hu values are identical (MIN = MAX). "
            "Skipping Min–Max standardization. Assigning 0 to SUM_H_i_MIN_MAX."
        )

        # Add new field for standardized values
        if "SUM_H_i_MIN_MAX" not in [f.name for f in arcpy.ListFields(Hu_table)]:
            arcpy.management.AddField(Hu_table, "SUM_H_i_MIN_MAX", "DOUBLE")

        # Set all SUM_H_i_MIN_MAX values to 0
        arcpy.management.CalculateField(Hu_table, "SUM_H_i_MIN_MAX", 0, "PYTHON3")

    # 7.5. Case 2 — normal standardization
    else:
        arcpy.AddMessage("Performing Min–Max standardization of Hu...")
        arcpy.management.StandardizeField(Hu_table, "SUM_H_i", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 8. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
    # ----------------------------------------------------------------------
    fields_to_check = ["SUM_H_i", "SUM_H_i_MIN_MAX"]
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    # Checking whether any fields need to be removed at all
    fields_to_remove = [f for f in fields_to_check if f in existing_fields]

    if fields_to_remove:
        arcpy.AddMessage("Removing old join field from the grid...")
        for old_field in fields_to_remove:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 9. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    #arcpy.management.JoinField(grid_fl, grid_id_field, Hu_table, f"{grid_id_field}_1",["SUM_H_i", "SUM_H_i_MIN_MAX"])
    arcpy.management.JoinField(grid_fl, stat_zone_field_ID, Hu_table, stat_zone_field_ID, ["SUM_H_i", "SUM_H_i_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 10. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl,"SUM_H_i", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "SUM_H_i_MIN_MAX",std_output_index_name, std_output_index_alias)
    arcpy.AddMessage(f"Unit entropy ({output_index_name}) calculated successfully.")

    # ----------------------------------------------------------------------
    # 11. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Removing temporary zone field...")
    arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.AddMessage("Cleaning intermediate datasets...")
    for fc in (intersect_fc, tabulate_intersection_table, Hu_table):
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
        arcpy.management.Compact(workspace_gdb)
    arcpy.AddMessage("P_Hu calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))