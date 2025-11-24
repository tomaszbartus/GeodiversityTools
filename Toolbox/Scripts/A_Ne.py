# Geodiversity Tool A_Ne
# Calculates the number of landscape feature elements (polygons) within each polygon of an analytical grid
# Author: Tomasz Bartuś (bartus@agh.edu.pl)
# 2025-11-20

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL (Feature Layers only)
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)             # polygon FL
    landscape_attr = arcpy.GetParameterAsText(1)           # category field
    grid_fl = arcpy.GetParameterAsText(2)                  # analytical grid FL
    grid_id_field = arcpy.GetParameterAsText(3)            # grid OBJECTID-like field

    # Workspace where intermediate data will be written
    workspace_gdb = arcpy.Describe(landscape_fl).path

    # Prefix based on category attribute
    prefix = landscape_attr[:3].upper()

    # ----------------------------------------------------------------------
    # CHECK FOR EXISTING OUTPUT FIELDS (re-running protection)
    # ----------------------------------------------------------------------
    field_raw = f"{prefix}_Ne"
    field_std = f"{prefix}_Ne_MM"

    existing_fields = [f.name for f in arcpy.ListFields(grid_fl)]

    if field_raw in existing_fields or field_std in existing_fields:
        arcpy.AddError(
            f"Fields '{field_raw}' and/or '{field_std}' already exist in the analytical grid.\n"
            f"Remove these fields before re-running the A_Ne tool."
        )
        raise Exception("Existing output fields detected. Aborting tool execution.")

    # ----------------------------------------------------------------------
    # Intermediate datasets
    # ----------------------------------------------------------------------
    intersect_fc = f"{workspace_gdb}\\{prefix}_Ne_Int"
    mts_fc       = f"{workspace_gdb}\\{prefix}_Ne_MtS"
    ne_table     = f"{workspace_gdb}\\{prefix}_Ne_Tab"

    # ----------------------------------------------------------------------
    # 1. Intersect landscape FL with grid FL (create intersect_fc - ..._Ne_Tab FC)
    # ----------------------------------------------------------------------
    arcpy.analysis.Intersect([landscape_fl, grid_fl], intersect_fc,"ALL", "", "INPUT")

    # ----------------------------------------------------------------------
    # 2. Multipart → singlepart (create mts_fc - ..._Ne_MtS FC)
    # ----------------------------------------------------------------------
    arcpy.management.MultipartToSinglepart(intersect_fc, mts_fc)

    # ----------------------------------------------------------------------
    # 3. Add Count field and set = 1
    # ----------------------------------------------------------------------
    arcpy.management.AddField(mts_fc, "Count", "SHORT")

    with arcpy.da.UpdateCursor(mts_fc, ["Count"]) as cursor:
        for row in cursor:
            row[0] = 1
            cursor.updateRow(row)

    # ----------------------------------------------------------------------
    # 4. Statistics: count elements per grid cell
    # ----------------------------------------------------------------------
    #case_field = grid_id_field
    case_field = "FID_" + grid_fl
    # arcpy.analysis.Statistics(in_table, out_table, statistics_fields, {case_field}, {concatenation_separator})
    arcpy.analysis.Statistics(mts_fc, ne_table, [["Count", "SUM"]], case_field)

    # ----------------------------------------------------------------------
    # 5. Min-Max standardization
    # ----------------------------------------------------------------------
    arcpy.management.StandardizeField(ne_table, "SUM_Count", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 6. Join back to grid layer
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(grid_fl, grid_id_field, ne_table, case_field,["SUM_Count", "SUM_Count_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 7. Rename joined fields
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "SUM_Count", field_raw, landscape_attr + "_Ne")
    arcpy.management.AlterField(grid_fl, "SUM_Count_MIN_MAX", field_std, "Std_" + landscape_attr + "_Ne")

    # ----------------------------------------------------------------------
    # 8. Cleanup
    # ----------------------------------------------------------------------
    for fc in (intersect_fc, mts_fc, ne_table):
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("Ne calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
