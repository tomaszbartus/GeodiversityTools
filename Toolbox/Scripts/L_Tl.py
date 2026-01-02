# Geodiversity Tool L_Tl
# Calculates the total length of line features of a selected landscape feature
# within each polygon of an analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2026-01-02

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

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX, FIELDS AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()

    stat_zone_field_ID = "StatZoneID"
    intersect_fc = f"{workspace_gdb}\\{prefix}_Int"
    dissolved_fc = f"{workspace_gdb}\\{prefix}_Dis"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_LTl"
    output_index_alias = f"{prefix}_L_Tl"
    std_output_index_name = f"{prefix}_LTl_MM"
    std_output_index_alias = f"Std_{prefix}_L_Tl"

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
        dissolved_fc
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
    # 2. INTERSECT LANDSCAPE LINES WITH GRID FL (creates intersect_fc containing FID_<grid> for grouping)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Intersecting landscape lines with the analytical grid...")
    arcpy.analysis.Intersect([landscape_fl, grid_fl], intersect_fc,"ALL")

    # ----------------------------------------------------------------------
    # 3. DISSOLVE LINES
    # ----------------------------------------------------------------------
    grid_fid_field = f"FID_{arcpy.Describe(grid_fl).baseName}"
    arcpy.management.Dissolve(intersect_fc, dissolved_fc, stat_zone_field_ID)

    # ----------------------------------------------------------------------
    # 4. CREATE Lines_Length FIELD AND COPY Shape_Length VALUES INTO IT
    #    (Shape_Length is a system attribute and cannot be removed in step 5)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Creating Lines_Length field...")
    arcpy.management.AddField(dissolved_fc, "Lines_Length", "DOUBLE")
    arcpy.management.CalculateField(dissolved_fc, "Lines_Length", "!Shape_Length!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 5. STANDARDIZE L_Tl (MIN-MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing L_Tl (Min-Max)...")
    arcpy.management.StandardizeField(dissolved_fc, "Lines_Length", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 6. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
    # ----------------------------------------------------------------------
    fields_to_check = ["LINES_LENGTH", "LINES_LENGTH_MIN_MAX"]
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
    arcpy.management.JoinField(grid_fl, stat_zone_field_ID, dissolved_fc, stat_zone_field_ID,["Lines_Length", "Lines_Length_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 8. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "Lines_Length", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "Lines_Length_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 9. CLEANUP
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
