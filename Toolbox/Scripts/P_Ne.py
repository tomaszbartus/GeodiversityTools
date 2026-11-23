# coding=utf-8
"""
Geodiversity Tool: P_Ne (Number of Geosites / Point Features)
Calculates the number of geosites (point features) within each polygon of the analytical grid
and creates a new, standalone output feature class with user-defined fields.
Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
Refactored for GeodiversityTools Core Architecture
"""

import arcpy
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
    grid_fl = arcpy.GetParameterAsText(1)  # 1 - analytical grid
    grid_id_field = arcpy.GetParameterAsText(2)  # 2 - grid ID field
    null_handling_mode = arcpy.GetParameterAsText(3)  # 3 - handling of empty grid cells

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(4)  # 4 - Output feature class path (DE Feature Class, Output)

    # Domyślne nazwy pól wynikowych. Używane, gdy użytkownik pozostawi pole puste.
    default_raw_field = "R_Ne_feature_P"
    default_std_field = "SR_Ne_feature_P"

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
            "MAX from observed Ne values."
        )
    else:
        arcpy.AddMessage(
            "Empty-cell handling: empty cells ignored in standardization, "
            "MIN and MAX from observed Ne values."
        )

    # Lokalizacje tymczasowe w pamięci RAM
    stat_zone_field_ID = "StatZoneID"
    intersect_fc = "memory\\temp_pne_intersect"

    # 1. Walidacja wstępna przez moduł core
    arcpy.AddMessage("Validating input feature classes...")
    core.check_gdb_feature(grid_fl)
    core.check_gdb_feature(landscape_fl)

    # 2. Przygotowanie bezpiecznej kopii strefowej w pamięci RAM (oryginalna siatka nietknięta!)
    working_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # Czyszczenie śmieci po poprzednich uruchomieniach
    if arcpy.Exists(intersect_fc):
        try:
            arcpy.management.Delete(intersect_fc)
        except:
            pass

    # ----------------------------------------------------------------------
    # 3. SPATIAL JOIN – count points inside each grid cell (na kopii w RAM)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("SPATIALLY JOINING landscape points with the analytical grid...")
    arcpy.analysis.SpatialJoin(
        working_grid_memory, landscape_fl, intersect_fc,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", "", "INTERSECT"
    )

    # Tworzymy nowe pole 'Ne' zamiast AlterField (ponieważ AlterField nie działa w memory\)
    arcpy.management.AddField(intersect_fc, "Ne", "DOUBLE")
    arcpy.management.CalculateField(intersect_fc, "Ne", "!Join_Count!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 4. STANDARYZACJA MIN–MAX LICZBY ELEMENTÓW
    #    Puste pola mają Ne = 0. W klasie wynikowej zawsze zostaje 0; opcja
    #    decyduje wyłącznie o tym, czy to zero wchodzi do zakresu Min–Max.
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Standardizing Ne (Min–Max)...")

    if "Ne_MIN_MAX" not in [f.name for f in arcpy.ListFields(intersect_fc)]:
        arcpy.management.AddField(intersect_fc, "Ne_MIN_MAX", "DOUBLE")

    ne_values = [row[0] for row in arcpy.da.SearchCursor(intersect_fc, ["Ne"]) if row[0] is not None]

    if not ne_values:
        arcpy.AddWarning("No Ne values were calculated for the analytical grid.")

    # Ne = 0 może oznaczać wyłącznie puste pole (pole z obiektami ma Ne >= 1),
    # dlatego w trybie pomijającym puste pola odrzucamy zera z zakresu.
    range_values = ne_values if include_zero else [v for v in ne_values if v > 0]
    min_ne, max_ne = core.min_max_bounds(range_values, include_zero)
    arcpy.AddMessage(f"Using MIN={min_ne} and MAX={max_ne} for standardization.")

    with arcpy.da.UpdateCursor(intersect_fc, ["Ne", "Ne_MIN_MAX"]) as cursor:
        for row in cursor:
            row[1] = core.standardize_min_max(row[0], min_ne, max_ne)
            cursor.updateRow(row)

    arcpy.AddMessage("Min–Max standardization completed successfully.")

    # ----------------------------------------------------------------------
    # 6. BEZPIECZNY ZAPIS DO NOWEJ KLASY OBIEKTÓW
    # ----------------------------------------------------------------------
    core.safe_write_to_new_feature_class(
        grid_fl=grid_fl,
        grid_id_field=grid_id_field,
        result_table=intersect_fc,
        raw_value_field="Ne",
        std_value_field="Ne_MIN_MAX",
        output_fc_path=output_fc_path,
        output_raw_field=output_raw_field,
        output_std_field=output_std_field,
        raw_field_type="LONG"
    )

    # ----------------------------------------------------------------------
    # 7. CLEANUP
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Cleaning intermediate datasets...")
    for item in (intersect_fc, working_grid_memory):
        if arcpy.Exists(item):
            try:
                arcpy.management.Delete(item)
            except:
                pass

    arcpy.ClearWorkspaceCache_management()
    arcpy.AddMessage("P_Ne calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError(f"Python error occurred: {str(e)}")

finally:
    arcpy.ClearWorkspaceCache_management()