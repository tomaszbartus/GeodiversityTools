# Calculates the Circular Standard Deviation (SDc) for a selected landscape feature (raster)
# in each polygon of an analytical grid.
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
    # 0 - Input RASTER, CIRCULAR landscape feature (continuous variable)
    # 1 - Analytical grid feature layer (polygon layer)
    # 2 - Analytical grid identification field (e.g. OBJECTID)
    landscape_ras = arcpy.GetParameterAsText(0)
    grid_fl = arcpy.GetParameterAsText(1)
    grid_id_field = arcpy.GetParameterAsText(2)

    # ----------------------------------------------------------------------
    # WORKSPACE, PREFIX AND INTERMEDIATE DATASETS
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(grid_fl).path
    raster_base = arcpy.Describe(landscape_ras).baseName
    prefix = raster_base[:3].upper()

    landscape_rad = f"{workspace_gdb}\\{prefix}_RAD"
    landscape_sin = f"{workspace_gdb}\\{prefix}_SIN"
    landscape_cos = f"{workspace_gdb}\\{prefix}_COS"

    zonal_sin_tbl = f"{workspace_gdb}\\{prefix}_SIN_SUM"
    zonal_cos_tbl = f"{workspace_gdb}\\{prefix}_COS_SUM"
    zonal_stat_table = f"{workspace_gdb}\\{prefix}_ZONAL_STAT"

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_RSDc"
    output_index_alias = f"{prefix}_R_SDc"
    std_output_index_name = f"{prefix}_RSDcMM"
    std_output_index_alias = f"Std_{prefix}_R_SDc"

    # ----------------------------------------------------------------------
    # CHECK IF INTERMEDIATE DATASETS ALREADY EXIST IN GDB
    # ----------------------------------------------------------------------
    intermediate_items = [
        landscape_rad,
        landscape_sin,
        landscape_cos,
        zonal_sin_tbl,
        zonal_cos_tbl,
        zonal_stat_table
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
            f"Remove these fields before re-running the tool."
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
    # 3. ZONAL SUM of sin and cos (per grid cell)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Computing zonal sums (sin/cos)...")

    arcpy.sa.ZonalStatisticsAsTable(grid_fl, grid_id_field, landscape_sin, zonal_sin_tbl, "DATA", "SUM")
    arcpy.sa.ZonalStatisticsAsTable(grid_fl, grid_id_field, landscape_cos, zonal_cos_tbl, "DATA", "SUM")

    arcpy.management.AlterField(zonal_sin_tbl, "SUM", "SumSin", "SumSin")
    arcpy.management.AlterField(zonal_cos_tbl, "SUM", "SumCos", "SumCos")

    # ----------------------------------------------------------------------
    # 4. CREATE empty zonal_stat table
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Creating zonal_stat table (object id skeleton)...")

    arcpy.conversion.TableToTable(grid_fl, workspace_gdb, f"{prefix}_ZONAL_STAT")

    fields_to_delete = [
        f.name for f in arcpy.ListFields(zonal_stat_table)
        if f.name.upper() != grid_id_field.upper()
    ]

    if fields_to_delete:
        arcpy.management.DeleteField(zonal_stat_table, fields_to_delete)

    # ----------------------------------------------------------------------
    # 5. JOIN zonal_sin and zonal_cos
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining zonal sum tables into zonal_stat table...")

    arcpy.management.JoinField(zonal_stat_table, grid_id_field, zonal_sin_tbl, grid_id_field, ["SumSin", "Count"])
    arcpy.management.JoinField(zonal_stat_table, grid_id_field, zonal_cos_tbl, grid_id_field, ["SumCos"])

    # ----------------------------------------------------------------------
    # 6. RENAME Count -> Px_No
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(zonal_stat_table, "Count", "Px_No", "NumberOfPixels")

    # ----------------------------------------------------------------------
    # 7. ADD EMPTY FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AddField(zonal_stat_table, "R", "DOUBLE")
    arcpy.management.AddField(zonal_stat_table, "R_Mn", "DOUBLE")
    arcpy.management.AddField(zonal_stat_table, "SDc", "DOUBLE")

    # ----------------------------------------------------------------------
    # 8. CALCULATE R using custom Python (float64)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating R, R_Mn and SDc...")

    code_block = textwrap.dedent("""
        import math
        def calc_r(sin_val, cos_val):
            sin_val = float(sin_val)
            cos_val = float(cos_val)
            return math.sqrt(sin_val**2 + cos_val**2)
    """)

    arcpy.management.CalculateField(zonal_stat_table,"R","calc_r(!SumSin!, !SumCos!)","PYTHON3", code_block)

    # ----------------------------------------------------------------------
    # 9. CALCULATE R_Mn
    # ----------------------------------------------------------------------
    arcpy.management.CalculateField(zonal_stat_table,"R_Mn","!R! / !Px_No!","PYTHON3")

    # ----------------------------------------------------------------------
    # 10. CALCULATE SDc
    # ----------------------------------------------------------------------
    arcpy.management.CalculateField(zonal_stat_table,"SDc","(180/math.pi)*math.sqrt(2*(1-!R_Mn!))","PYTHON3")

    # ----------------------------------------------------------------------
    # 11. STANDARDIZE SDc (MIN-MAX)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing R_SDc (Min-Max)...")
    arcpy.management.StandardizeField(zonal_stat_table,"SDc","MIN-MAX",0,1)

    # ----------------------------------------------------------------------
    # 12. REMOVE OLD JOIN FIELDS
    # ----------------------------------------------------------------------

    fields_to_check = ["SDC", "SDC_MIN_MAX"]
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    fields_to_remove = [f for f in fields_to_check if f in existing_fields]

    if fields_to_remove:
        arcpy.AddMessage("Removing old join fields from the grid...")
        for old_field in fields_to_remove:
            arcpy.management.DeleteField(grid_fl, old_field)

    # ----------------------------------------------------------------------
    # 13. JOIN RESULTS BACK TO GRID
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, grid_id_field, zonal_stat_table, grid_id_field,["SDc", "SDc_MIN_MAX"])

    # ----------------------------------------------------------------------
    # 14. RENAME OUTPUT FIELDS
    # ----------------------------------------------------------------------
    arcpy.management.AlterField(grid_fl, "SDc", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "SDc_MIN_MAX", std_output_index_name, std_output_index_alias)

    # ----------------------------------------------------------------------
    # 15. CLEANUP
    # ----------------------------------------------------------------------

    arcpy.AddMessage("Cleaning intermediate datasets...")

    for item in [
        landscape_rad,
        landscape_sin,
        landscape_cos,
        zonal_sin_tbl,
        zonal_cos_tbl,
        zonal_stat_table
    ]:
        if arcpy.Exists(item):
            try:
                arcpy.management.Delete(item)
            except Exception:
                arcpy.AddWarning(f"Could not delete intermediate dataset: {item}")

    arcpy.ClearWorkspaceCache_management()
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("R_SDc calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
