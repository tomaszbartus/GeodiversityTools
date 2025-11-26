# Geodiversity Tool P_Ne
# Calculates the number of geosites (point features) within each polygon of the analytical grid
# Author: bartus@agh.edu.pl
# 2025-11-26

import arcpy

# Allow overwrite
arcpy.env.overwriteOutput = True

try:
    # ----------------------------------------------------------------------
    # PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)  # point feature layer
    grid_fl = arcpy.GetParameterAsText(1)       # analytical grid FL
    grid_id_field = arcpy.GetParameterAsText(2) # grid OBJECTID-like field

    # Workspace and prefix
    workspace_gdb = arcpy.Describe(grid_fl).path
    prefix = arcpy.Describe(landscape_fl).baseName[:3].upper()

    # ----------------------------------------------------------------------
    # CHECK IF OUTPUT FIELDS IN ANALYTICAL GRID ALREADY EXIST IN GRID TABLE
    # ----------------------------------------------------------------------
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]

    field_raw = (prefix + "_P_Ne").upper()
    field_std = ("Std_" + prefix + "_P_Ne").upper()
    field_mm = (prefix + "_P_NeMM").upper()

    if field_raw in existing_fields or field_std in existing_fields or field_mm in existing_fields:
        arcpy.AddError(
            f"Fields '{prefix}_P_Ne', 'Std_{prefix}_P_Ne' and/or '{prefix}_P_NeMM' already exist "
            f"in the analytical grid attribute table.\n"
            f"Please remove these fields before re-running the tool."
        )
        raise Exception("Field name conflict – remove existing fields and try again.")

    # ----------------------------------------------------------------------
    # 1. CREATE TEMPORARY LAYER WITH COUNT FIELD
    # ----------------------------------------------------------------------
    temp_landscape = arcpy.CreateUniqueName("temp_landscape", workspace_gdb)
    arcpy.management.CopyFeatures(landscape_fl, temp_landscape)
    arcpy.management.AddField(temp_landscape, "Count", "SHORT")

    with arcpy.da.UpdateCursor(temp_landscape, ["Count"]) as cursor:
        for row in cursor:
            row[0] = 1
            cursor.updateRow(row)

    # ----------------------------------------------------------------------
    # 2. SPATIAL JOIN WITH FIELD MAPPINGS
    # ----------------------------------------------------------------------
    temp_output = arcpy.CreateUniqueName("temp_spatial_join", workspace_gdb)

    # Configure FieldMappings
    field_mappings = arcpy.FieldMappings()
    field_mappings.addTable(grid_fl)

    # Create FieldMap for Count field
    fm_count = arcpy.FieldMap()
    fm_count.addInputField(temp_landscape, "Count")
    fm_count.mergeRule = "Sum"

    # Configure output field
    out_field = fm_count.outputField
    out_field.name = f"{prefix}_P_Ne"
    out_field.aliasName = f"{prefix}_P_Ne"
    out_field.type = "LONG"
    fm_count.outputField = out_field

    field_mappings.addFieldMap(fm_count)

    # Execute Spatial Join
    arcpy.analysis.SpatialJoin(grid_fl, temp_landscape, temp_output,"JOIN_ONE_TO_ONE","KEEP_ALL", field_mappings,"INTERSECT")

    # Transfer result field to grid
    arcpy.management.JoinField(grid_fl, grid_id_field, temp_output, "TARGET_FID", f"{prefix}_P_Ne")

    # ----------------------------------------------------------------------
    # 3. Standardization (Min-Max)
    # ----------------------------------------------------------------------
    arcpy.management.StandardizeField(grid_fl,f"{prefix}_P_Ne","MIN-MAX",0,1)

    # ----------------------------------------------------------------------
    # 4. Rename table attributes
    # ----------------------------------------------------------------------
    # Sprawdź czy pole zostało utworzone przez StandardizeField
    std_field_name = f"{prefix}_P_Ne_MIN_MAX"
    if std_field_name in [f.name for f in arcpy.ListFields(grid_fl)]:
        arcpy.management.AlterField(grid_fl, std_field_name,f"{prefix}_P_NeMM",f"Std_{landscape_fl}_A_Ne")

    # ----------------------------------------------------------------------
    # 5. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.management.Delete(temp_output)
    arcpy.management.Delete(temp_landscape)
    arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("Ne calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))