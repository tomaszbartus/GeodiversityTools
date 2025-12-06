# Geodiversity Tool L_Tl
# Calculates the total length of line features of a selected landscape feature
# within each polygon of an analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# 2025-12-06

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
    # INTERMEDIATE FEATURE CLASSES
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()

    intersect_fc = f"{workspace_gdb}\\{prefix}_Int"
    dissolved_fc = f"{workspace_gdb}\\{prefix}_Dis"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_Tl"
    output_index_alias = f"{prefix}_Tl"
    std_output_index_name = f"{prefix}_Tl_MM"
    std_output_index_alias = f"Std_{prefix}_Tl"

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS ALREADY EXIST IN GRID TABLE
    # ----------------------------------------------------------------------
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
    # 1. Intersect landscape FL with grid FL (creates intersect_fc containing FID_<grid> for grouping)
    # ----------------------------------------------------------------------
    #arcpy.analysis.Intersect([landscape_fl, grid_fl], intersect_fc,"ALL", "", "INPUT")
    arcpy.analysis.Intersect([landscape_fl, grid_fl], intersect_fc,"ALL")

    # ----------------------------------------------------------------------
    # 2. Dissolve lines
    # ----------------------------------------------------------------------
    grid_fid_field = f"FID_{arcpy.Describe(grid_fl).baseName}"
    # arcpy.management.Dissolve(in_features, out_feature_class, {dissolve_field}, {statistics_fields}, {multi_part}, {unsplit_lines}, {concatenation_separator})
    arcpy.management.Dissolve(intersect_fc, dissolved_fc, grid_fid_field)

    # ----------------------------------------------------------------------
    # 3. Min-Max standardization
    # ----------------------------------------------------------------------
    arcpy.management.StandardizeField(dissolved_fc, "Shape_Length", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 4. Join back to grid layer
    # ----------------------------------------------------------------------

    arcpy.management.JoinField(grid_fl, grid_id_field, dissolved_fc, grid_fid_field,["Shape_Length", "Shape_Length_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 5. Rename joined fields
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "Shape_Length", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "Shape_Length_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 8. Cleanup
    # ----------------------------------------------------------------------
    for fc in (intersect_fc, dissolved_fc):
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("Ne calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("A geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("A Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
