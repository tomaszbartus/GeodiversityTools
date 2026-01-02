# Geodiversity Tool R_SDc
# Calculates the Circular Standard Deviation (SDc)
# for a selected circular landscape feature (raster)
# in each polygon of an analytical grid.
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# Date: 2025-12-31

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
    landscape_ras = arcpy.GetParameterAsText(0)  # raster (circular values in degrees)
    grid_fl = arcpy.GetParameterAsText(1)        # polygon grid
    grid_id_field = arcpy.GetParameterAsText(2)  # key field in grid (e.g. OBJECTID)

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX, FIELDS AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(grid_fl).path
    raster_base = arcpy.Describe(landscape_ras).baseName
    prefix = raster_base[:3].upper()

    stat_zone_field_ID = "StatZoneID"
    landscape_rad = fr"memory\{prefix}_RAD"
    landscape_sin = fr"memory\{prefix}_SIN"
    landscape_cos = fr"memory\{prefix}_COS"

    zonal_sin_tbl = fr"memory\{prefix}_SIN_SUM"
    zonal_cos_tbl = fr"memory\{prefix}_COS_SUM"
    zonal_stat_table = fr"memory\{prefix}_ZONAL_STAT"
    stats_table = fr"memory\{prefix}_STATS"

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
    # 1. CREATE TEMPORARY STATISTICAL ZONE FIELD ID TO AVOID OBJECTID_1 CONFLICTS
    # ----------------------------------------------------------------------
    arcpy.AddMessage(f"Creating temporary zone field: {stat_zone_field_ID}...")

    # Remove if exist in grid_fl
    if stat_zone_field_ID in [f.name for f in arcpy.ListFields(grid_fl)]:
        arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.management.AddField(grid_fl, stat_zone_field_ID, "LONG")
    arcpy.management.CalculateField(grid_fl, stat_zone_field_ID, f"!{grid_id_field}!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 2. CONVERT Degrees -> Radians (raster)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Converting degrees to radians...")
    raster_rad = Raster(landscape_ras) / (180.0 / math.pi)
    raster_rad.save(landscape_rad)

    # ----------------------------------------------------------------------
    # 3. CALCULATE sin(θ) and cos(θ)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating sin and cos rasters...")
    raster_sin = Sin(raster_rad)
    raster_sin.save(landscape_sin)

    raster_cos = Cos(raster_rad)
    raster_cos.save(landscape_cos)

    # ----------------------------------------------------------------------
    # 4. ZONAL SUM of sin and cos (per grid cell) -> memory tables
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Computing zonal sums (sin/cos)...")
    arcpy.sa.ZonalStatisticsAsTable(grid_fl, stat_zone_field_ID, landscape_sin, zonal_sin_tbl, "DATA", "SUM")
    arcpy.sa.ZonalStatisticsAsTable(grid_fl, stat_zone_field_ID, landscape_cos, zonal_cos_tbl, "DATA", "SUM")

    # ----------------------------------------------------------------------
    # 4a. PRINT FIELD NAMES FOR DEBUGGING
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Fields in zonal_sin_tbl:")
    for f in arcpy.ListFields(zonal_sin_tbl):
        arcpy.AddMessage(f" - {f.name} ({f.type})")
    arcpy.AddMessage("Fields in zonal_cos_tbl:")
    for f in arcpy.ListFields(zonal_cos_tbl):
        arcpy.AddMessage(f" - {f.name} ({f.type})")

    # ----------------------------------------------------------------------
    # 5. PREPARE SIN TABLE (zonal_sin_tbl)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Preparing Sin values...")
    # Add a new field 'SumSin' and copy the 'SUM' value into it
    arcpy.management.AddField(zonal_sin_tbl, "SumSin", "DOUBLE")
    arcpy.management.CalculateField(zonal_sin_tbl, "SumSin", "!SUM!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 6. PREPARE COS TABLE (zonal_cos_tbl)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Preparing Cos values...")
    # Add a new field 'SumCos' and copy the 'SUM' value into it
    arcpy.management.AddField(zonal_cos_tbl, "SumCos", "DOUBLE")
    arcpy.management.CalculateField(zonal_cos_tbl, "SumCos", "!SUM!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 7. CREATE FINAL ZONAL STAT TABLE & JOIN
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining Sin and Cos tables...")
    # Copy zonal_sin_tbl as the base for zonal_stat_table
    arcpy.management.CopyRows(zonal_sin_tbl, zonal_stat_table)

    # Join only SumCos field (StatZoneID will be used as the join key)
    arcpy.management.JoinField(zonal_stat_table, stat_zone_field_ID, zonal_cos_tbl, stat_zone_field_ID, ["SumCos"])

    # ----------------------------------------------------------------------
    # 8. ADD EMPTY FIELDS FOR: R, R_Mn, SDc
    # ----------------------------------------------------------------------
    arcpy.management.AddField(zonal_stat_table, "R", "DOUBLE")
    arcpy.management.AddField(zonal_stat_table, "R_Mn", "DOUBLE")
    arcpy.management.AddField(zonal_stat_table, "SDc", "DOUBLE")

    # ----------------------------------------------------------------------
    # 9. CALCULATE R, R_Mn and SDc (use Python expressions)
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
    arcpy.management.CalculateField(zonal_stat_table, "SDc", "(180/math.pi)*math.sqrt(max(0, 2*(1-!R_Mn!)))", "PYTHON3")

    # ----------------------------------------------------------------------
    # 10. MANUAL MIN-MAX STANDARDIZATION
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing SDc using manual Min-Max normalization...")

    # 10.1 Calculate min & max
    arcpy.analysis.Statistics(zonal_stat_table, stats_table, [["SDc", "MIN"], ["SDc", "MAX"]])
    with arcpy.da.SearchCursor(stats_table, ["MIN_SDc", "MAX_SDc"]) as cursor:
        min_sdc, max_sdc = next(cursor)
    arcpy.management.Delete(stats_table)

    # 10.2 Add standardized field
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
    # 11. REMOVE OLD JOIN FIELDS FROM GRID (if any)
    # ----------------------------------------------------------------------
    fields_to_check = ["SDC", "SDC_MM"]
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]
    fields_to_remove = [f for f in fields_to_check if f in existing_fields]
    if fields_to_remove:
        arcpy.AddMessage("Removing old join fields from the grid...")
        for old_field in fields_to_remove:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 12. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, stat_zone_field_ID, zonal_stat_table, stat_zone_field_ID, ["SDc", "SDc_MM"])

    # ----------------------------------------------------------------------
    # 13. RENAME JOINED FIELDS on GRID
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "SDc", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "SDc_MM", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 14. CLEANUP (delete memory intermediates)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Removing temporary zone field...")
    arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

    arcpy.AddMessage("Cleaning intermediate datasets...")
    for item in [landscape_rad, landscape_sin, landscape_cos, zonal_sin_tbl, zonal_cos_tbl, zonal_stat_table]:
        try:
            if arcpy.Exists(item):
                arcpy.management.Delete(item)
        except Exception:
            arcpy.AddWarning(f"Could not delete intermediate dataset: {item}")

    arcpy.ClearWorkspaceCache_management()
    # compact unnecessary for memory-only run but OK for gdb
    try:
        if workspace_gdb.endswith(".gdb"):
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
