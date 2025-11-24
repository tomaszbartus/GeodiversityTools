# Geodiversity Tool A_SHDI
# Calculates the Shannon–Weaver diversity index (SHDI) for a selected landscape feature (polygon feature class)
# in each polygon of an analytical grid.
# Author: Tomasz Bartuś (bartus@agh.edu.pl)
# Date: 2025-11-21

import arcpy
import math

arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)            # polygon feature layer
    landscape_attr = arcpy.GetParameterAsText(1)          # category field
    grid_fl = arcpy.GetParameterAsText(2)                 # grid layer
    grid_id_field = arcpy.GetParameterAsText(3)           # OBJECTID of the grid

    workspace_gdb = arcpy.Describe(landscape_fl).path

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS ALREADY EXIST
    # ----------------------------------------------------------------------
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    field_raw = f"{landscape_attr}_SHDI".upper()
    field_std = f"STD_{landscape_attr}_SHDI".upper()

    if field_raw in existing_fields or field_std in existing_fields:
        arcpy.AddError(
            f"Fields '{landscape_attr}_SHDI' and/or 'Std_{landscape_attr}_SHDI' already exist "
            f"in the analytical grid attribute table.\n"
            f"Please remove these fields before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # INTERMEDIATE PATHS
    # ----------------------------------------------------------------------
    prefix = landscape_attr[:3].upper()
    out_intersect_fc = f"{workspace_gdb}\\{prefix}_grid"
    out_mts_fc       = f"{workspace_gdb}\\{prefix}_MtS"
    freq_table       = f"{workspace_gdb}\\{prefix}_Freq"
    shdi_table       = f"{workspace_gdb}\\{prefix}_SHDI"

    # ----------------------------------------------------------------------
    # 1. INTERSECT
    # ----------------------------------------------------------------------
    arcpy.analysis.Intersect([landscape_fl, grid_fl], out_intersect_fc, "ALL", "", "INPUT")

    # ----------------------------------------------------------------------
    # 2. SINGLEPART
    # ----------------------------------------------------------------------
    arcpy.management.MultipartToSinglepart(out_intersect_fc, out_mts_fc)

    # ----------------------------------------------------------------------
    # 3. STATISTICS OF AREA
    # ----------------------------------------------------------------------
    grid_base = arcpy.Describe(grid_fl).baseName
    case_field = "FID_" + grid_base

    arcpy.analysis.Statistics(
        out_mts_fc,
        freq_table,
        [["Shape_Area", "SUM"]],
        [case_field, landscape_attr]
    )

    # ----------------------------------------------------------------------
    # 4. SHDI fields
    # ----------------------------------------------------------------------
    arcpy.management.AddField(freq_table, "p_i", "FLOAT")
    arcpy.management.AddField(freq_table, "ln_p_i", "FLOAT")
    arcpy.management.AddField(freq_table, "SumElement", "FLOAT")

    # ----------------------------------------------------------------------
    # 5. AREA DICTIONARY
    # ----------------------------------------------------------------------
    total_area = {}
    with arcpy.da.SearchCursor(freq_table, [case_field, "Sum_Shape_Area"]) as s:
        for fid, area in s:
            area = area if area else 0
            total_area[fid] = total_area.get(fid, 0) + area

    # ----------------------------------------------------------------------
    # 6. CALCULATE p_i, ln(p_i), SumElement
    # ----------------------------------------------------------------------
    with arcpy.da.UpdateCursor(freq_table,
                               [case_field, "Sum_Shape_Area", "p_i", "ln_p_i", "SumElement"]) as u:
        for fid, area, p, ln_p, se in u:
            area = area if area else 0
            denom = total_area.get(fid, 0)
            p_val = area / denom if denom > 0 else 0
            if p_val > 0:
                ln_p_val = math.log(p_val)
                sum_el = -p_val * ln_p_val
            else:
                ln_p_val = 0
                sum_el = 0
            u.updateRow([fid, area, p_val, ln_p_val, sum_el])

    # ----------------------------------------------------------------------
    # 7. SUM SHDI
    # ----------------------------------------------------------------------
    arcpy.analysis.Statistics(freq_table, shdi_table,[["SumElement", "SUM"]], case_field)

    # ----------------------------------------------------------------------
    # 8. STANDARDIZE (MIN–MAX) – BEZ ZMIAN!
    # ----------------------------------------------------------------------
    arcpy.management.StandardizeField(shdi_table, "SUM_SumElement", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 9. JOIN TO GRID (UŻYCIE PARAMETRU grid_id_field)
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(grid_fl, grid_id_field, shdi_table, case_field,["SUM_SumElement", "SUM_SumElement_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 10. RENAME FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "SUM_SumElement",f"{prefix}_SHDI",f"{landscape_attr}_SHDI")
    arcpy.management.AlterField(grid_fl, "SUM_SumElement_MIN_MAX",f"{prefix}_SHDIMM",f"Std_{landscape_attr}_SHDI")

    # ----------------------------------------------------------------------
    # 11. CLEANUP
    # ----------------------------------------------------------------------
    for fc in [out_intersect_fc, out_mts_fc, freq_table, shdi_table]:
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("SHDI calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()