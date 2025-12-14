# Geodiversity Tool R_SDc
# Calculates the Circular Standard Deviation (SDc) for a selected landscape feature (raster)
# in each polygon of an analytical grid. In_memory version
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# Date: 2025-12-12

import arcpy
import math
from arcpy.sa import *
import textwrap  # removing unwanted indentations

# Allow to overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_ras = arcpy.GetParameterAsText(0)   # raster (circular values in degrees)
    grid_fl = arcpy.GetParameterAsText(1)        # polygon grid
    grid_id_field = arcpy.GetParameterAsText(2)  # key field in grid (e.g. OBJECTID)

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX AND INTERMEDIATE DATASETS (in_memory)
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(grid_fl).path
    raster_base = arcpy.Describe(landscape_ras).baseName
    prefix = raster_base[:3].upper()

    landscape_rad = fr"in_memory\{prefix}_RAD"
    landscape_sin = fr"in_memory\{prefix}_SIN"
    landscape_cos = fr"in_memory\{prefix}_COS"

    zonal_sin_tbl = fr"in_memory\{prefix}_SIN_SUM"
    zonal_cos_tbl = fr"in_memory\{prefix}_COS_SUM"
    zonal_stat_table = fr"in_memory\{prefix}_ZONAL_STAT"
    stats_table = fr"in_memory\{prefix}_STATS"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_RSDc"
    output_index_alias = f"{prefix}_R_SDc"
    std_output_index_name = f"{prefix}_RSDcMM"
    std_output_index_alias = f"Std_{prefix}_R_SDc"

    # ----------------------------------------------------------------------
    # FORCE REMOVAL OF LOCKS FROM INPUT DATASETS
    # ----------------------------------------------------------------------
    try:
        arcpy.AddMessage("Removing existing locks...")
        arcpy.management.RemoveLocks(landscape_ras)
        arcpy.management.RemoveLocks(grid_fl)
    except:
        pass

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS ALREADY EXIST IN GRID TABLE
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Checking if the output fields already exist...")
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]
    if output_index_name.upper() in existing_fields or std_output_index_name.upper() in existing_fields:
        arcpy.AddError(
            f"Fields '{output_index_name}' and/or '{std_output_index_name}' already exist in the grid. "
            "Remove them before re-running."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # 1. CONVERT Degrees -> Radians (raster)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Converting degrees to radians...")
    raster_rad = Raster(landscape_ras) / (180.0 / math.pi)
    raster_rad.save(landscape_rad)

    # ----------------------------------------------------------------------
    # 2. CALCULATE sin(θ) and cos(θ)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating sin and cos rasters...")
    raster_sin = Sin(raster_rad)
    raster_sin.save(landscape_sin)

    raster_cos = Cos(raster_rad)
    raster_cos.save(landscape_cos)

    # ----------------------------------------------------------------------
    # 3. ZONAL SUM of sin and cos (per grid cell) -> in_memory tables
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Computing zonal sums (sin/cos)...")
    arcpy.sa.ZonalStatisticsAsTable(grid_fl, grid_id_field, landscape_sin, zonal_sin_tbl, "DATA", "SUM")
    arcpy.sa.ZonalStatisticsAsTable(grid_fl, grid_id_field, landscape_cos, zonal_cos_tbl, "DATA", "SUM")

    # ----------------------------------------------------------------------
    # 3a. PRINT FIELD NAMES FOR DEBUGGING
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Fields in zonal_sin_tbl:")
    for f in arcpy.ListFields(zonal_sin_tbl):
        arcpy.AddMessage(f" - {f.name} ({f.type})")
    arcpy.AddMessage("Fields in zonal_cos_tbl:")
    for f in arcpy.ListFields(zonal_cos_tbl):
        arcpy.AddMessage(f" - {f.name} ({f.type})")

    # Rename SUM fields in zonal tables for clarity (they are in memory)
    arcpy.management.AlterField(zonal_sin_tbl, "SUM", "SumSin", "SumSin")
    arcpy.management.AlterField(zonal_cos_tbl, "SUM", "SumCos", "SumCos")

    # ----------------------------------------------------------------------
    # 4. USE zonal_sin_tbl as base zonal_stat_table
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Creating zonal_stat_table from zonal_sin_tbl...")
    arcpy.management.CopyRows(zonal_sin_tbl, zonal_stat_table)

    arcpy.AddMessage("Fields in zonal_stat_table after CopyRows:")
    for f in arcpy.ListFields(zonal_stat_table):
        arcpy.AddMessage(f" - {f.name} ({f.type})")

    # Detect zone field – use OBJECTID_1
    zone_field = "OBJECTID_1"
    arcpy.AddMessage(f"Using zone field: {zone_field}")

    # ----------------------------------------------------------------------
    # 5. JOIN cos sums (corrected!)
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(zonal_stat_table, zone_field, zonal_cos_tbl, zone_field, ["SumCos"])
    # No need to alter field, already SumCos

    # ----------------------------------------------------------------------
    # 6. ADD EMPTY FIELDS FOR: R, R_Mn, SDc
    # ----------------------------------------------------------------------
    arcpy.management.AddField(zonal_stat_table, "R", "DOUBLE")
    arcpy.management.AddField(zonal_stat_table, "R_Mn", "DOUBLE")
    arcpy.management.AddField(zonal_stat_table, "SDc", "DOUBLE")

    # ----------------------------------------------------------------------
    # 7. CALCULATE R, R_Mn and SDc (use Python expressions)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating R, R_Mn and SDc...")

    # Calculate R safely
    code_block = textwrap.dedent("""
        import math
        def calc_r(sin_val, cos_val):
            try:
                sin_val = float(sin_val)
                cos_val = float(cos_val)
                return math.sqrt(sin_val**2 + cos_val**2)
            except:
                return None
    """)
    arcpy.management.CalculateField(zonal_stat_table, "R", "calc_r(!SumSin!, !SumCos!)", "PYTHON3", code_block)

    # R_Mn = R / COUNT
    arcpy.management.CalculateField(zonal_stat_table, "R_Mn", "(!R! / !COUNT!) if !COUNT! not in (None, 0) else 0", "PYTHON3")

    # SDc formula
    arcpy.management.CalculateField(zonal_stat_table, "SDc", "(180/math.pi)*math.sqrt(2*(1-!R_Mn!))", "PYTHON3")

    # ----------------------------------------------------------------------
    # 8. MANUAL MIN-MAX STANDARDIZATION
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing SDc using manual Min-Max normalization...")

    # 8.1 Calculate min & max
    arcpy.analysis.Statistics(zonal_stat_table, stats_table, [["SDc", "MIN"], ["SDc", "MAX"]])
    with arcpy.da.SearchCursor(stats_table, ["MIN_SDc", "MAX_SDc"]) as cursor:
        min_sdc, max_sdc = next(cursor)
    arcpy.management.Delete(stats_table)

    # 8.2 Add standardized field
    std_field_name = "SDc_MM"
    arcpy.management.AddField(zonal_stat_table, std_field_name, "DOUBLE")

    if max_sdc == min_sdc:
        arcpy.AddWarning(
            "SDc has constant value across all zones. Standardized values will be set to 0."
        )
        arcpy.management.CalculateField(zonal_stat_table, std_field_name, "0", "PYTHON3")
    else:
        code_block = f"""
def minmax(val):
    return (val - {min_sdc}) / ({max_sdc} - {min_sdc})
"""
        arcpy.management.CalculateField(
            zonal_stat_table,
            std_field_name,
            "minmax(!SDc!)",
            "PYTHON3",
            code_block
        )

    # ----------------------------------------------------------------------
    # 9. REMOVE OLD JOIN FIELDS FROM GRID (if any)
    # ----------------------------------------------------------------------
    fields_to_check = ["SDC", "SDC_MM"]
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]
    fields_to_remove = [f for f in fields_to_check if f in existing_fields]
    if fields_to_remove:
        arcpy.AddMessage("Removing old join fields from the grid...")
        for old_field in fields_to_remove:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 10. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, grid_id_field, zonal_stat_table, zone_field, ["SDc", "SDc_MM"])

    # ----------------------------------------------------------------------
    # 11. RENAME JOINED FIELDS on GRID
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "SDc", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "SDc_MM", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 12. CLEANUP (delete in_memory intermediates)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    for item in [landscape_rad, landscape_sin, landscape_cos, zonal_sin_tbl, zonal_cos_tbl, zonal_stat_table]:
        try:
            if arcpy.Exists(item):
                arcpy.management.Delete(item)
        except Exception:
            arcpy.AddWarning(f"Could not delete intermediate dataset: {item}")

    arcpy.ClearWorkspaceCache_management()
    # compact unnecessary for in_memory-only run but OK for gdb
    try:
        arcpy.management.Compact(workspace_gdb)
    except:
        pass

    arcpy.AddMessage("R_SDc calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
