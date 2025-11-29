# Geodiversity Tool P_Hu
# Calculates the unit entropy (Hu) point feature layer within each polygon of the analytical grid
# Author: bartus@agh.edu.pl
# 2025-11-27

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

    # ----------------------------------------------------------------------
    # INTERMEDIATE DATA
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()

    intersect_fc = f"{workspace_gdb}\\{prefix}_Ne_Int"
    tabulate_intersection_table = f"{workspace_gdb}\\{prefix}_Nc_Tbl"
    Hu_table = f"{workspace_gdb}\\{prefix}_Hu_Tbl"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_Hu"
    output_index_alias = f"{prefix}_Hu"

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS ALREADY EXIST IN GRID TABLE
    # ----------------------------------------------------------------------
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    field_raw = output_index_name.upper()

    if field_raw in existing_fields:
        arcpy.AddError(
            f"Fields '{output_index_name.upper()}' already exist "
            f"in the analytical grid attribute table.\n"
            f"Remove these field before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # 1. SPATIAL JOIN
    # ----------------------------------------------------------------------
    arcpy.analysis.SpatialJoin(grid_fl, landscape_fl, intersect_fc, "JOIN_ONE_TO_ONE","KEEP_ALL", "", "INTERSECT")

    arcpy.management.AlterField(intersect_fc, "Join_Count", "Ne")

    # ----------------------------------------------------------------------
    # 2. TABULATE INTERSECTION
    # Funkcja tworzy tabelę złożoną z kolumn: 1) ID komórki grida, 2) wartość kategorii, 3) liczby punktów tej kategorii (Nc)
    # ----------------------------------------------------------------------
    arcpy.analysis.TabulateIntersection(grid_fl, grid_id_field, landscape_fl, tabulate_intersection_table, landscape_attr)

    # ----------------------------------------------------------------------
    # 3. q_i = Nc / Ne
    # ----------------------------------------------------------------------
    # Add new attribute Ne to the tabulate_intersection_table
    arcpy.management.JoinField(tabulate_intersection_table, f"{grid_id_field}_1", intersect_fc, grid_id_field,["Ne"])

    # Add new attribute q_i to the tabulate_intersection_table
    arcpy.management.AddField(tabulate_intersection_table, "q_i", "DOUBLE")

    # Calculate q_i
    arcpy.management.CalculateField(tabulate_intersection_table,"q_i","(!PNT_COUNT! / !Ne!) if !Ne! > 0 else 0","PYTHON3")

    # ----------------------------------------------------------------------
    # 4. Calculate Unit Entropy H_i = -(q_i * ln(q_i))
    # ----------------------------------------------------------------------
    arcpy.management.AddField(tabulate_intersection_table, "H_i", "DOUBLE")
    arcpy.management.CalculateField(tabulate_intersection_table,"H_i","-(!q_i! * math.log(!q_i!)) if !q_i! > 0 else 0","PYTHON3")

    # ----------------------------------------------------------------------
    # 5. SUMMARIZE ALL H_i -- use the grid ID field name present in the tabulate table (usually grid_id + "_1")
    # ----------------------------------------------------------------------
    arcpy.analysis.Statistics(tabulate_intersection_table, Hu_table,[["H_i", "SUM"]], f"{grid_id_field}_1")

    # ----------------------------------------------------------------------
    # 6. Join back to grid layer
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(grid_fl, grid_id_field, Hu_table, f"{grid_id_field}_1",["SUM_H_i"])

    # ----------------------------------------------------------------------
    # 7. Rename joined fields
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl,"SUM_H_i", output_index_name, output_index_alias)
    arcpy.AddMessage(f"Unit entropy ({output_index_name}) calculated successfully.")

    # ----------------------------------------------------------------------
    # 8. CLEANUP
    # ----------------------------------------------------------------------
    for fc in (intersect_fc, tabulate_intersection_table, Hu_table):
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)
    arcpy.AddMessage("Hu calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))