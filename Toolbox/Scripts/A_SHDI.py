# Geodiversity Tool A_SHDI
# Calculates the Shannon–Weaver diversity index (SHDI) for a selected landscape feature (polygon feature class)
# in each polygon of an analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# Date: 2025-11-29

import arcpy
import math

arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)            # polygon feature layer
    landscape_attr = arcpy.GetParameterAsText(1)          # category field
    grid_fl = arcpy.GetParameterAsText(2)                 # grid layer
    grid_id_field = arcpy.GetParameterAsText(3)           # OBJECTID of the grid

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = landscape_attr[:3].upper()

    out_intersect_fc = f"{workspace_gdb}\\{prefix}_grid"
    out_mts_fc       = f"{workspace_gdb}\\{prefix}_MtS"
    freq_table       = f"{workspace_gdb}\\{prefix}_Freq"
    shdi_table       = f"{workspace_gdb}\\{prefix}_SHDI"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_ASHDI"
    output_index_alias = f"{prefix}_A_SHDI"
    std_output_index_name = f"{prefix}_SHDIMM"
    std_output_index_alias = f"Std_{prefix}_A_SHDI"

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
    arcpy.analysis.Intersect([landscape_fl, grid_fl], out_intersect_fc, "ALL", "", "INPUT")

    # ----------------------------------------------------------------------
    # 2. MULTIPART → SINGLEPART
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
    # 4. SHDI INTERMEDIATE FIELDS
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
    # 8. STANDARDIZE A_SHDI (MIN–MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing A_SHDI (Min-Max)...")
    arcpy.management.StandardizeField(shdi_table, "SUM_SumElement", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 9. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
    # ----------------------------------------------------------------------
    fields_to_check = ["SUM_SUMELEMENT", "SUM_SUMELEMENT_MIN_MAX"]
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    # Checking whether any fields need to be removed at all
    fields_to_remove = [f for f in fields_to_check if f in existing_fields]

    if fields_to_remove:
        arcpy.AddMessage("Removing old join fields from the grid...")
        for old_field in fields_to_remove:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 10. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, grid_id_field, shdi_table, case_field,["SUM_SumElement", "SUM_SumElement_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 11. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "SUM_SumElement", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "SUM_SumElement_MIN_MAX",std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 12. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    for fc in [out_intersect_fc, out_mts_fc, freq_table, shdi_table]:
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("A_SHDI calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()