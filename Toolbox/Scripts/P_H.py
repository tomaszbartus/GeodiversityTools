# Geodiversity Tool P_Hjed
# Calculates the number of geosites (point features) within each polygon of the analytical grid
# Author: bartus@agh.edu.pl
# 2025-11-26

import arcpy
import math

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)           # point feature layer
    landscape_attr = arcpy.GetParameterAsText(1)         # geosites category field
    grid_fl = arcpy.GetParameterAsText(2)                # grid layer
    grid_id_field = arcpy.GetParameterAsText(3)          # OBJECTID of the grid

    # Workspace GDB
    workspace_gdb = arcpy.Describe(landscape_fl).path

    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()

    # ----------------------------------------------------------------------
    # CHECK FOR EXISTING OUTPUT FIELDS (re-running protection)
    # ----------------------------------------------------------------------
    field_raw = f"{prefix}_H"
    field_std = f"{prefix}_Ne_MM"

    existing_fields = [f.name for f in arcpy.ListFields(grid_fl)]

    if field_raw in existing_fields:
        arcpy.AddError(
            f"Fields '{field_raw}' already exist in the analytical grid.\n"
            f"Remove these fields before re-running the P_H tool."
        )
        raise Exception("Existing output field detected. Aborting tool execution.")

    # ----------------------------------------------------------------------
    # 1. CREATE TEMPORARY LAYER WITH COUNT FIELD
    # ----------------------------------------------------------------------
    intersect_fc = f"{workspace_gdb}\\{prefix}_Ne_Int"
    tabulate_intersection_table = f"{workspace_gdb}\\{prefix}_Nc_Tbl"
    H_table = f"{workspace_gdb}\\{prefix}_H_Tbl"

    # ----------------------------------------------------------------------
    # 2. SPATIAL JOIN
    # ----------------------------------------------------------------------
    # arcpy.analysis.SpatialJoin(target_features, join_features, out_feature_class, {join_operation}, {join_type}, {field_mapping}, {match_option}, {search_radius}, {distance_field_name}, {match_fields})
    arcpy.analysis.SpatialJoin(grid_fl, landscape_fl, intersect_fc, "JOIN_ONE_TO_ONE","KEEP_ALL", "", "INTERSECT")

    arcpy.management.AlterField(intersect_fc, "Join_Count", "Ne")

    # ----------------------------------------------------------------------
    # 3. TABULATE INTERSECTION
    # ----------------------------------------------------------------------
    arcpy.analysis.TabulateIntersection(grid_fl, grid_id_field, landscape_fl, tabulate_intersection_table, landscape_attr)

    # ----------------------------------------------------------------------
    # 4. qi = Nc / Ne
    # ----------------------------------------------------------------------
    # Add Ne attribute to the tabulate_intersection_table
    arcpy.management.JoinField(tabulate_intersection_table, grid_id_field, intersect_fc, grid_id_field,["Ne"])

    # Add new attribute qi to the  tabulate_intersection_table
    arcpy.management.AddField(tabulate_intersection_table, "qi", "DOUBLE")

    # Calculate qi
    arcpy.management.CalculateField(tabulate_intersection_table,"qi","(!POINTS! / !Ne!) if !Ne! > 0 else 0","PYTHON3")

    # ----------------------------------------------------------------------
    # 5. Calculate Unit Entropy (q_i * ln(q_i))
    # ----------------------------------------------------------------------
    arcpy.management.AddField(tabulate_intersection_table, "H_i", "DOUBLE")
    arcpy.management.CalculateField(tabulate_intersection_table,"H_i","-(!qi! * math.log(!qi!)) if !qi! > 0 else 0","PYTHON3")

    # ----------------------------------------------------------------------
    # 6. SUMMARIZE ALL qi
    # ----------------------------------------------------------------------
    arcpy.analysis.Statistics(tabulate_intersection_table, H_table,[["H_i", "SUM"]], grid_id_field)

    # ----------------------------------------------------------------------
    # 7. Join back to grid layer
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(grid_fl, grid_id_field, H_table, grid_id_field,["SUM_H_i"])

    # ----------------------------------------------------------------------
    # 8. Rename joined fields
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "SUM_H_i", f"{prefix}_H", landscape_attr + "_H")
    arcpy.AddMessage(f"Unit entropy ({prefix}_H) calculated successfully.")

    # ----------------------------------------------------------------------
    # 9. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.management.Delete(intersect_fc)
    arcpy.management.Delete(tabulate_intersection_table)
    arcpy.management.Delete(H_table)
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("Ne calculation completed successfully.")


except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))