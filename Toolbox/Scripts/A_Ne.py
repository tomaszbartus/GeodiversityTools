# Geodiversity Tool A_Ne
# Calculates the number of landscape polygon feature elements within each polygon of an analytical grid
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2025-12-12

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)             # polygon FL
    landscape_attr = arcpy.GetParameterAsText(1)           # category field
    grid_fl = arcpy.GetParameterAsText(2)                  # analytical grid FL
    grid_id_field = arcpy.GetParameterAsText(3)            # grid OBJECTID-like field

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = landscape_attr[:3].upper()

    intersect_fc = f"{workspace_gdb}\\{prefix}_Ne_Int"
    mts_fc       = f"{workspace_gdb}\\{prefix}_Ne_MtS"
    ne_table     = f"{workspace_gdb}\\{prefix}_Ne_Tab"

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
    # 1. INTERSECT LANDSCAPE POLYGONS WITH GRID FL (creates intersect_fc containing FID_<grid> for grouping)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Intersecting landscape polygons with the analytical grid...")
    arcpy.analysis.Intersect([landscape_fl, grid_fl], intersect_fc,"ONLY_FID")

    # ----------------------------------------------------------------------
    # 2. MULTIPART → SINGLEPART (create mts_fc - ..._Ne_MtS FC)
    # ----------------------------------------------------------------------
    arcpy.management.MultipartToSinglepart(intersect_fc, mts_fc)

    # ----------------------------------------------------------------------
    # 3. ADD Count FIELD and set = 1
    # ----------------------------------------------------------------------
    arcpy.management.AddField(mts_fc, "Count", "SHORT")

    with arcpy.da.UpdateCursor(mts_fc, ["Count"]) as cursor:
        for row in cursor:
            row[0] = 1
            cursor.updateRow(row)

    # ----------------------------------------------------------------------
    # 4. STATISTICS: count elements per grid cell
    # ----------------------------------------------------------------------
    case_field = f"FID_{arcpy.Describe(grid_fl).name}"
    #case_field = "FID_" + grid_fl
    arcpy.analysis.Statistics(mts_fc, ne_table, [["Count", "SUM"]], case_field)

    # ----------------------------------------------------------------------
    # 5. STANDARDIZE A_Ne (MIN-MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing A_Ne (Min-Max)...")
    arcpy.management.StandardizeField(ne_table, "SUM_Count", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 6. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
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
    # 7. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, grid_id_field, ne_table, case_field,["SUM_Count", "SUM_Count_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 8. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "SUM_Count", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "SUM_Count_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 9. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    for fc in (intersect_fc, mts_fc, ne_table):
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    arcpy.ClearWorkspaceCache_management()
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
