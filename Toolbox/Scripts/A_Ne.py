# Geodiversity Tool A_Ne
# Calculates the number of landscape polygon feature elements within each polygon of an analytical grid
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2025-11-29

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
    # Intermediate datasets
    # ----------------------------------------------------------------------
    intersect_fc = f"{workspace_gdb}\\{prefix}_Ne_Int"
    mts_fc       = f"{workspace_gdb}\\{prefix}_Ne_MtS"
    ne_table     = f"{workspace_gdb}\\{prefix}_Ne_Tab"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_Ne"
    output_index_alias = f"{prefix}_Ne"
    std_output_index_name = f"{prefix}_Ne_MM"
    std_output_index_alias = f"Std_{prefix}_Ne"

    # ----------------------------------------------------------------------
    # CHECK FOR EXISTING OUTPUT FIELDS (re-running protection)
    # ----------------------------------------------------------------------
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
    # 1. Intersect landscape FL with grid FL (creates intersect_fc containing FID_<grid> for grouping)
    # ----------------------------------------------------------------------
    #arcpy.analysis.Intersect([landscape_fl, grid_fl], intersect_fc,"ALL", "", "INPUT")
    arcpy.analysis.Intersect([landscape_fl, grid_fl], intersect_fc,"ONLY_FID")

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
    case_field = f"FID_{arcpy.Describe(grid_fl).name}"
    #case_field = "FID_" + grid_fl
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
    arcpy.management.AlterField(grid_fl, "SUM_Count", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "SUM_Count_MIN_MAX", std_output_index_name, std_output_index_alias)

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
