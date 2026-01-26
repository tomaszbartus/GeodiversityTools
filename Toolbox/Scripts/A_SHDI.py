# Geodiversity Tool A_SHDI
# Calculates the Shannon–Weaver diversity index (SHDI) for a selected landscape feature (polygon feature class)
# in each polygon of an analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# Date: 2026-01-26

import arcpy
import math

arcpy.env.overwriteOutput = True
# Prevent Z-coordinate and M-coordinate inheritance in feature classes
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)            # polygon feature layer
    landscape_attr = arcpy.GetParameterAsText(1)          # category field
    grid_fl = arcpy.GetParameterAsText(2)                 # grid layer
    grid_id_field = arcpy.GetParameterAsText(3)           # OBJECTID of the grid

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX, FIELDS AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(landscape_fl).path
    prefix = landscape_attr[:3].upper()

    stat_zone_field_ID = "StatZoneID"
    out_intersect_fc = f"{workspace_gdb}\\{prefix}_grid"
    out_mts_fc       = f"{workspace_gdb}\\{prefix}_MtS"
    freq_table       = f"{workspace_gdb}\\{prefix}_Freq"
    shdi_table       = f"{workspace_gdb}\\{prefix}_SHDI"

    # ----------------------------------------------------------------------
    # VALIDATE DATA FORMATS (BLOCK SHAPEFILES)
    # ----------------------------------------------------------------------
    def check_gdb_feature(fc):
        desc = arcpy.Describe(fc)
        if desc.dataType == "ShapeFile" or desc.catalogPath.lower().endswith(".shp"):
            arcpy.AddError(f"Error: Layer '{desc.name}' is a Shapefile.")
            arcpy.AddError("Geodiversity Tools require GDB feature classes.")
            raise arcpy.ExecuteError

    check_gdb_feature(landscape_fl)
    check_gdb_feature(grid_fl)

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
    output_index_name = f"{prefix}_ASHDI"
    output_index_alias = f"{prefix}_A_SHDI"
    std_output_index_name = f"{prefix}_SHDIMM"
    std_output_index_alias = f"Std_{prefix}_A_SHDI"

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
        out_intersect_fc,
        out_mts_fc,
        freq_table,
        shdi_table
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
    # 1. CREATE TEMPORARY STATISTICAL ZONE FIELD ID TO AVOID OBJECTID_1 CONFLICTS
    # ----------------------------------------------------------------------
    arcpy.AddMessage(f"Creating temporary zone field: {stat_zone_field_ID}...")

    # Remove if exist in grid_fl
    if stat_zone_field_ID in [f.name for f in arcpy.ListFields(grid_fl)]:
        arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.management.AddField(grid_fl, stat_zone_field_ID, "LONG")
    arcpy.management.CalculateField(grid_fl, stat_zone_field_ID, f"!{grid_id_field}!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 2. INTERSECT LANDSCAPE POLYGONS WITH GRID FL (creates intersect_fc containing FID_<grid> for grouping)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Intersecting landscape polygons with the analytical grid...")
    arcpy.analysis.Intersect([landscape_fl, grid_fl], out_intersect_fc, "ALL", "", "INPUT")

    arcpy.AddMessage(">>> INTERSECT FINISHED")

    if not arcpy.Exists(out_intersect_fc):
        raise Exception("Intersect output was not created.")

    count = int(arcpy.management.GetCount(out_intersect_fc)[0])
    arcpy.AddMessage(f">>> Intersect feature count: {count}")

    if count == 0:
        raise Exception("Intersect output is empty.")

    # ----------------------------------------------------------------------
    # 3. MULTIPART → SINGLEPART
    # ----------------------------------------------------------------------
    arcpy.management.MultipartToSinglepart(out_intersect_fc, out_mts_fc)
    arcpy.AddMessage(">>> MULTIPART TO SINGLEPART FINISHED")

    # ----------------------------------------------------------------------
    # 4. STATISTICS OF AREA
    # ----------------------------------------------------------------------
    arcpy.AddMessage(">>> STARTING STATISTICS")
    arcpy.analysis.Statistics(
        out_mts_fc,
        freq_table,
        [["Shape_Area", "SUM"]],
        [stat_zone_field_ID, landscape_attr]
    )

    # ----------------------------------------------------------------------
    # 5. SHDI INTERMEDIATE FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AddField(freq_table, "p_i", "FLOAT")
    arcpy.management.AddField(freq_table, "ln_p_i", "FLOAT")
    arcpy.management.AddField(freq_table, "SumElement", "FLOAT")

    # ----------------------------------------------------------------------
    # 6. AREA DICTIONARY
    # ----------------------------------------------------------------------
    total_area = {}
    with arcpy.da.SearchCursor(freq_table, [stat_zone_field_ID, "Sum_Shape_Area"]) as s:
        for fid, area in s:
            area = area if area else 0
            total_area[fid] = total_area.get(fid, 0) + area

    # ----------------------------------------------------------------------
    # 7. CALCULATE p_i, ln(p_i), SumElement
    # ----------------------------------------------------------------------
    with arcpy.da.UpdateCursor(freq_table,
                               [stat_zone_field_ID, "Sum_Shape_Area", "p_i", "ln_p_i", "SumElement"]) as u:
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
    # 8. SUM SHDI
    # ----------------------------------------------------------------------
    arcpy.analysis.Statistics(freq_table, shdi_table,[["SumElement", "SUM"]], stat_zone_field_ID)

    # ----------------------------------------------------------------------
    # 9. STANDARDIZE A_SHDI (MIN–MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing A_SHDI (Min-Max)...")
    arcpy.management.StandardizeField(shdi_table, "SUM_SumElement", "MIN-MAX", 0, 1)

    # ----------------------------------------------------------------------
    # 10. ENSURE OLD JOIN FIELDS ARE REMOVED FROM THE GRID
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
    # 11. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, stat_zone_field_ID, shdi_table, stat_zone_field_ID,["SUM_SumElement", "SUM_SumElement_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 12. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "SUM_SumElement", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "SUM_SumElement_MIN_MAX",std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 13. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Removing temporary zone field...")
    arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.AddMessage("Cleaning intermediate datasets...")
    for fc in [out_intersect_fc, out_mts_fc, freq_table, shdi_table]:
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
        arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("A_SHDI calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()