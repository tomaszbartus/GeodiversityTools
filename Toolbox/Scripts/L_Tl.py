# coding=utf-8
"""
Geodiversity Tool: L_Tl (Total Line Length)
Calculates the total length of line features of a selected landscape feature
within each polygon of an analytical grid and creates a new, standalone output feature class with user-defined fields.
Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
Refactored for GeodiversityTools Core Architecture
"""

import arcpy
import geodiversity_core as core

arcpy.env.overwriteOutput = True
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

try:
    # --- INPUT PARAMETERS ---
    landscape_fl = arcpy.GetParameterAsText(0)  # 0 - Line feature layer
    grid_fl = arcpy.GetParameterAsText(1)  # 1 - Analytical grid layer
    grid_id_field = arcpy.GetParameterAsText(2)  # 2 - Grid ID field
    null_handling_mode = arcpy.GetParameterAsText(3)  # 3 - Handling of empty grid cells

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(4)  # 4 - Output feature class path (DE Feature Class, Output)

    # Domyślne nazwy pól wynikowych. Używane, gdy użytkownik pozostawi pole puste.
    default_raw_field = "R_Tl_feature_L"
    default_std_field = "SR_Tl_feature_L"

    output_raw_field = (arcpy.GetParameterAsText(5) or "").strip()  # 5 - Output partial criteria field name (String, Input)
    output_std_field = (arcpy.GetParameterAsText(6) or "").strip()  # 6 - Output std. partial criteria field name (String, Input)

    if not output_raw_field:
        output_raw_field = default_raw_field
        arcpy.AddMessage(f"Raw output field not provided; using default '{default_raw_field}'.")

    if not output_std_field:
        output_std_field = default_std_field
        arcpy.AddMessage(f"Standardized output field not provided; using default '{default_std_field}'.")

    # ----------------------------------------------------------------------
    # OBSŁUGA PUSTYCH PÓL SIATKI W STANDARYZACJI MIN–MAX
    # ----------------------------------------------------------------------
    include_zero = core.resolve_empty_cell_mode(null_handling_mode)
    if include_zero:
        arcpy.AddMessage(
            "Empty-cell handling: 0 included in the Min–Max range (MIN = 0), "
            "MAX from observed Lines_Length values."
        )
    else:
        arcpy.AddMessage(
            "Empty-cell handling: empty cells ignored in standardization, "
            "MIN and MAX from observed Lines_Length values."
        )

    # Lokalizacje tymczasowe w pamięci RAM
    stat_zone_field_ID = "StatZoneID"
    intersect_fc = "memory\\temp_ltl_intersect"
    dissolved_fc = "memory\\temp_ltl_dissolved"

    # 1. Walidacja wstępna przez moduł core
    arcpy.AddMessage("Validating input feature classes...")
    core.check_gdb_feature(grid_fl)
    core.check_gdb_feature(landscape_fl)

    # 2. Przygotowanie bezpiecznej kopii strefowej w pamięci RAM (oryginalna siatka nietknięta!)
    working_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # Czyszczenie śmieci po poprzednich uruchomieniach
    for item in (intersect_fc, dissolved_fc):
        if arcpy.Exists(item):
            arcpy.management.Delete(item)

    # 3. Intersect lines with the working grid copy in RAM
    arcpy.AddMessage("Intersecting landscape lines with the analytical grid...")
    arcpy.analysis.Intersect([landscape_fl, working_grid_memory], intersect_fc, "ALL")

    # 4. Dissolve lines by zone
    arcpy.AddMessage("Dissolving lines by grid zone...")
    arcpy.management.Dissolve(intersect_fc, dissolved_fc, stat_zone_field_ID)

    # 5. Create attribute fields (Lines_Length + Lines_Length_MIN_MAX)
    arcpy.AddMessage("Calculating total lines length per grid cell...")
    arcpy.management.AddField(dissolved_fc, "Lines_Length", "DOUBLE")

    # Używamy tokenu geometrycznego !SHAPE.length! zamiast ulotnego pola Shape_Length
    arcpy.management.CalculateField(dissolved_fc, "Lines_Length", "!SHAPE.length!", "PYTHON3")

    arcpy.management.AddField(dissolved_fc, "Lines_Length_MIN_MAX", "DOUBLE")

    # 6. Min-Max Standardization
    lines_values = [row[0] for row in arcpy.da.SearchCursor(dissolved_fc, ["Lines_Length"]) if row[0] is not None]

    if not lines_values:
        arcpy.AddWarning("No valid Lines_Length values found. MIN/MAX set to 0.")

    min_lines, max_lines = core.min_max_bounds(lines_values, include_zero)
    arcpy.AddMessage(f"Using MIN={min_lines} and MAX={max_lines} for standardization.")

    with arcpy.da.UpdateCursor(dissolved_fc, ["Lines_Length", "Lines_Length_MIN_MAX"]) as cursor:
        for row in cursor:
            row[1] = core.standardize_min_max(row[0], min_lines, max_lines)
            cursor.updateRow(row)

    arcpy.AddMessage("Min–Max standardization completed successfully.")

    # 7. Zapis wyników do NOWEJ klasy obiektów pod zadeklarowaną ścieżką
    core.safe_write_to_new_feature_class(
        grid_fl=grid_fl,
        grid_id_field=grid_id_field,
        result_table=dissolved_fc,
        raw_value_field="Lines_Length",
        std_value_field="Lines_Length_MIN_MAX",
        output_fc_path=output_fc_path,
        output_raw_field=output_raw_field,
        output_std_field=output_std_field
    )

    # 8. Cleanup (w tym usunięcie roboczej kopii siatki z pamięci RAM)
    arcpy.AddMessage("Cleaning intermediate memory layers...")
    for fc in (intersect_fc, dissolved_fc):
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    if arcpy.Exists(working_grid_memory):
        arcpy.management.Delete(working_grid_memory)

    arcpy.ClearWorkspaceCache_management()
    arcpy.AddMessage("Tool L_Tl finished successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("A geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError(f"Error in L_Tl execution: {str(e)}")

finally:
    arcpy.ClearWorkspaceCache_management()