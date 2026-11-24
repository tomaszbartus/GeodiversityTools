# coding=utf-8
"""
Toolbox: GeodiversityTools (for ArcGIS Pro)
Tool: P_Hu (Unit Entropy of Point Features)
Version: v.1.0.0.
Short description: Calculates the unit entropy (Hu) of point features within each polygon of the analytical grid and creates a new, standalone output feature class with user-defined fields.
Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
2026-11-11
"""

import arcpy
import math
import geodiversity_core as core

# Allow overwrite
arcpy.env.overwriteOutput = True
# Prevent Z-coordinate and M-coordinate inheritance in feature classes
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_fl = arcpy.GetParameterAsText(0)  # 0 - point feature layer
    landscape_attr = arcpy.GetParameterAsText(1)  # 1 - geosites category field
    grid_fl = arcpy.GetParameterAsText(2)  # 2 - grid layer
    grid_id_field = arcpy.GetParameterAsText(3)  # 3 - grid ID field
    null_handling_mode = arcpy.GetParameterAsText(4)  # 4 - Handling of empty grid cells

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(5)  # 5 - Output feature class path (DE Feature Class, Output)

    # Domyślne nazwy pól wynikowych. Używane, gdy użytkownik pozostawi pole puste.
    default_raw_field = "R_Hu_feature_P"
    default_std_field = "SR_Hu_feature_P"

    output_raw_field = (arcpy.GetParameterAsText(6) or "").strip()  # 6 - Output partial criteria field name (String, Input)
    output_std_field = (arcpy.GetParameterAsText(7) or "").strip()  # 7 - Output std. partial criteria field name (String, Input)

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
            "MAX from observed Hu values."
        )
    else:
        arcpy.AddMessage(
            "Empty-cell handling: empty cells ignored in standardization, "
            "MIN and MAX from observed Hu values."
        )

    # Lokalizacje tymczasowe w pamięci RAM
    stat_zone_field_ID = "StatZoneID"
    intersect_fc = "memory\\temp_phu_intersect"
    tabulate_intersection_table = "memory\\temp_phu_ti_tbl"
    Hu_table = "memory\\temp_phu_tbl"

    # 1. Walidacja wstępna przez moduł core
    arcpy.AddMessage("Validating input feature classes...")
    core.check_gdb_feature(grid_fl)
    core.check_gdb_feature(landscape_fl)

    # Filtr kategorii: obiekty bez kategorii (NULL lub pusty ciąg w polu
    # kategorii) są pomijane — nie tworzą odrębnej klasy (zob. rozdział 3.8.1).
    # Dalej używamy warstwy landscape_lyr zamiast landscape_fl.
    landscape_attr = core.resolve_field_name(
        landscape_fl, landscape_attr, "Landscape category attribute"
    )
    landscape_lyr = core.make_category_layer(
        landscape_fl, landscape_attr, "temp_phu_category_lyr"
    )

    # 2. Przygotowanie bezpiecznej kopii strefowej w pamięci RAM (oryginalna siatka nietknięta!)
    working_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # Czyszczenie śmieci po poprzednich uruchomieniach
    intermediate_items = [intersect_fc, tabulate_intersection_table, Hu_table]
    for item in intermediate_items:
        if arcpy.Exists(item):
            try:
                arcpy.management.Delete(item)
            except:
                pass

    # ----------------------------------------------------------------------
    # 3. SPATIAL JOIN (na kopii w RAM)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("SPATIALLY JOINING landscape points with the analytical grid...")
    arcpy.analysis.SpatialJoin(working_grid_memory, landscape_lyr, intersect_fc, "JOIN_ONE_TO_ONE", "KEEP_ALL", "",
                               "INTERSECT")

    # Dodajemy pole 'Ne' zamiast AlterField (ponieważ AlterField nie działa w memory\)
    arcpy.management.AddField(intersect_fc, "Ne", "DOUBLE")
    arcpy.management.CalculateField(intersect_fc, "Ne", "!Join_Count!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 4. TABULATE INTERSECTION (z użyciem kopii w RAM)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating Tabulate Intersection...")
    arcpy.analysis.TabulateIntersection(working_grid_memory, stat_zone_field_ID, landscape_lyr,
                                        tabulate_intersection_table, landscape_attr)

    # ----------------------------------------------------------------------
    # 5. q_i = PNT_COUNT / Ne
    # ----------------------------------------------------------------------
    arcpy.management.JoinField(tabulate_intersection_table, stat_zone_field_ID, intersect_fc, stat_zone_field_ID,
                               ["Ne"])

    arcpy.management.AddField(tabulate_intersection_table, "q_i", "DOUBLE")
    arcpy.management.CalculateField(tabulate_intersection_table, "q_i", "(!PNT_COUNT! / !Ne!) if !Ne! > 0 else 0",
                                    "PYTHON3")

    # ----------------------------------------------------------------------
    # 6. CALCULATE UNIT ENTROPY H_i = -(q_i * ln(q_i))
    # ----------------------------------------------------------------------
    arcpy.management.AddField(tabulate_intersection_table, "H_i", "DOUBLE")
    arcpy.management.CalculateField(tabulate_intersection_table, "H_i",
                                    "-(!q_i! * math.log(!q_i!)) if !q_i! > 0 else 0", "PYTHON3")

    # ----------------------------------------------------------------------
    # 7. SUMMARIZE ALL H_i
    # ----------------------------------------------------------------------
    arcpy.analysis.Statistics(tabulate_intersection_table, Hu_table, [["H_i", "SUM"]], stat_zone_field_ID)

    # ----------------------------------------------------------------------
    # 8. SAFE MIN–MAX STANDARDIZATION FOR Hu
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing P_Hu (Min–Max)...")

    hu_values = [row[0] for row in arcpy.da.SearchCursor(Hu_table, ["SUM_H_i"]) if row[0] is not None]
    if not hu_values:
        arcpy.AddWarning("No Hu values were calculated for the analytical grid.")

    min_SUM_H_i, max_SUM_H_i = core.min_max_bounds(hu_values, include_zero)
    arcpy.AddMessage(f"Using MIN={min_SUM_H_i} and MAX={max_SUM_H_i} for standardization.")

    std_field_name = "SUM_H_i_MIN_MAX"
    if std_field_name not in [f.name for f in arcpy.ListFields(Hu_table)]:
        arcpy.management.AddField(Hu_table, std_field_name, "DOUBLE")

    with arcpy.da.UpdateCursor(Hu_table, ["SUM_H_i", std_field_name]) as cursor:
        for row in cursor:
            row[1] = core.standardize_min_max(row[0], min_SUM_H_i, max_SUM_H_i)
            cursor.updateRow(row)

    # ----------------------------------------------------------------------
    # 9. BEZPIECZNY ZAPIS DO NOWEJ KLASY OBIEKTÓW
    # ----------------------------------------------------------------------
    core.safe_write_to_new_feature_class(
        grid_fl=grid_fl,
        grid_id_field=grid_id_field,
        result_table=Hu_table,
        raw_value_field="SUM_H_i",
        std_value_field=std_field_name,
        output_fc_path=output_fc_path,
        output_raw_field=output_raw_field,
        output_std_field=output_std_field
    )

    arcpy.AddMessage(f"Unit entropy calculated successfully.")

    # ----------------------------------------------------------------------
    # 10. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    for fc in intermediate_items:
        if arcpy.Exists(fc):
            try:
                arcpy.management.Delete(fc)
            except:
                pass

    if arcpy.Exists(working_grid_memory):
        arcpy.management.Delete(working_grid_memory)

    if arcpy.Exists(landscape_lyr):
        arcpy.management.Delete(landscape_lyr)

    arcpy.ClearWorkspaceCache_management()
    arcpy.AddMessage("P_Hu calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError(f"Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()