# Geodiversity Tool R_SDcm
# Calculates the Modified Circular Standard Deviation (SDc) for a selected landscape feature (raster) in each polygon of an analytical grid.
# The script sets the circular standard deviation value to 0 in those cells of the analytical grid where the mean slope is lower than the slope threshold specified by the user
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# Date: 2025-11-29

import arcpy

# Allow to overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    # 0 - Analytical grid feature layer (polygon layer)
    # 1 - Analytical grid identification field (e.g. OBJECTID)
    # 2 - Diversity assessment attribute to modify
    # 3 - Input Slope raster
    # 4 - Slope threshold [°] (e.g., 5°)

    grid_fl = arcpy.GetParameterAsText(0)
    grid_id_field = arcpy.GetParameterAsText(1)
    grid_field_to_modify = arcpy.GetParameterAsText(2)
    slope_ras = arcpy.GetParameterAsText(3)
    slope_threshold = arcpy.GetParameterAsText(4)

    # Workspace (use geodatabase where the grid lives)
    workspace_gdb = arcpy.Describe(grid_fl).path

    # ----------------------------------------------------------------------
    # Prepare names and intermediate outputs
    # ----------------------------------------------------------------------

    prefix = grid_field_to_modify[:3].upper()
    mean_slope_table = f"{workspace_gdb}\\SLOPE_ZONAL_STAT"

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS IN ANALYTICAL GRID ALREADY EXIST
    # ----------------------------------------------------------------------
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    field_raw = f"{prefix}_SDcm"
    field_std = f"Std_{prefix}_SDcm"

    if field_raw in existing_fields or field_std in existing_fields:
        arcpy.AddError(
            f"Fields '{prefix}_SDc' and/or 'Std_{raster_base}_SDc' already exist "
            f"in the analytical grid attribute table.\nPlease remove these fields before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # 1. Calculate mean slope in the each grid cell
    # ----------------------------------------------------------------------
    arcpy.sa.ZonalStatisticsAsTable(grid_fl, grid_id_field, slope_ras, mean_slope_table, "DATA", "MEAN")

    # ----------------------------------------------------------------------
    # 2. Add to analytical grid table prefix_SDcm field attribute
    # ----------------------------------------------------------------------
    arcpy.management.AddField(grid_fl, field_raw, "DOUBLE")

    # ----------------------------------------------------------------------
    # 3. Join Analytical grid and mean_slope_table
    # ----------------------------------------------------------------------




except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()
