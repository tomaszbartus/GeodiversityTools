# coding=utf-8
"""
Geodiversity Tool: P_Nc (Number of Point Features Categories)
Calculates the number of point feature categories of a selected landscape feature
within each polygon of an analytical grid and creates a new, standalone output feature class.
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
    landscape_fl = arcpy.GetParameterAsText(0)             # 0 - Point feature layer
    landscape_attr = arcpy.GetParameterAsText(1)           # 1 - Geosites category field
    grid_fl = arcpy.GetParameterAsText(2)                  # 2 - Grid layer
    grid_id_field = arcpy.GetParameterAsText(3)            # 3 - Grid ID field
    null_handling_mode = arcpy.GetParameterAsText(4)       # 4 - Handling of empty grid cells

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(5)  # 5 - Output feature class path (DE Feature Class, Output)

    # Domyślne nazwy pól wynikowych. Używane, gdy użytkownik pozostawi pole puste.
    default_raw_field = "R_Nc_feature_P"
    default_std_field = "SR_Nc_feature_P"

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
            "MAX from observed Nc values."
        )
    else:
        arcpy.AddMessage(
            "Empty-cell handling: empty cells ignored in standardization, "
            "MIN and MAX from observed Nc values."
        )

    # Lokalizacje tymczasowe w pamięci RAM
    stat_zone_field_ID = "StatZoneID"
    dissolved_fc = "memory\\temp_pnc_dissolved"
    nc_table = "memory\\temp_pnc_table"
    stats_table = "memory\\temp_pnc_stats"

    # 1. Walidacja danych wejściowych
    arcpy.AddMessage("Validating input feature classes...")
    core.check_gdb_feature(grid_fl)
    core.check_gdb_feature(landscape_fl)

    # 2. Przygotowanie bezpiecznej kopii strefowej w pamięci RAM (oryginalna siatka nietknięta!)
    working_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # Czyszczenie śmieci po poprzednich uruchomieniach
    for item in (dissolved_fc, nc_table, stats_table):
        if arcpy.Exists(item):
            arcpy.management.Delete(item)

    # 3. Kopia punktów w pamięci RAM. Near dopisuje do danych wejściowych pola
    #    NEAR_FID/NEAR_DIST, dlatego pracujemy na kopii — klasa użytkownika
    #    pozostaje nietknięta, a nieudany przebieg nie zostawia w niej śmieci.
    arcpy.AddMessage("Copying landscape points to the in-memory workspace...")
    temp_points_memory = "memory\\temp_pnc_points"
    if arcpy.Exists(temp_points_memory):
        arcpy.management.Delete(temp_points_memory)

    #    Obiekty bez kategorii (NULL lub pusty ciąg) są pomijane — nie tworzą
    #    odrębnej klasy (zob. rozdział 3.8.1). Kopiujemy od razu przefiltrowany
    #    zbiór, więc dalsze kroki nie widzą rekordów bez kategorii.
    arcpy.AddMessage("Filtering out points with NULL category value...")
    landscape_attr = core.resolve_field_name(
        landscape_fl, landscape_attr, "Landscape category attribute"
    )
    non_null_lyr = core.make_category_layer(
        landscape_fl, landscape_attr, "temp_pnc_category_lyr"
    )
    arcpy.management.CopyFeatures(non_null_lyr, temp_points_memory)

    # 4. Near Analysis (powiązanie punktów z roboczą kopią siatki w RAM)
    arcpy.AddMessage("Performing Near analysis between points and analytical grid...")
    arcpy.analysis.Near(temp_points_memory, working_grid_memory)

    # 5. Dissolve points by category within each cell
    arcpy.AddMessage("Dissolving landscape points by category...")
    arcpy.management.Dissolve(temp_points_memory, dissolved_fc, [landscape_attr, "NEAR_FID"])

    # 6. Frequency analysis
    arcpy.AddMessage("Calculating frequency of point categories per grid cell...")
    arcpy.analysis.Frequency(dissolved_fc, nc_table, ["NEAR_FID"])

    # Uzupełnienie tabeli o brakujące komórki siatki
    arcpy.AddMessage("Completing table with missing grid cells...")
    all_near_fid = [row[0] for row in arcpy.da.SearchCursor(working_grid_memory, [stat_zone_field_ID]) if row[0] is not None]
    existing_near_fid = [row[0] for row in arcpy.da.SearchCursor(nc_table, ["NEAR_FID"]) if row[0] is not None]

    missing_near_fid = set(all_near_fid) - set(existing_near_fid)

    if missing_near_fid:
        with arcpy.da.InsertCursor(nc_table, ["NEAR_FID", "FREQUENCY"]) as cursor:
            for fid in missing_near_fid:
                cursor.insertRow([fid, 0])
        arcpy.AddMessage(f"Added {len(missing_near_fid)} missing records.")

    # 7. Min–Max Standardization for P_Nc
    arcpy.AddMessage("Standardizing P_Nc (Min–Max)...")

    frequencies = [row[0] for row in arcpy.da.SearchCursor(nc_table, ["FREQUENCY"]) if row[0] is not None]

    # FREQUENCY = 0 może oznaczać wyłącznie puste pole (pole z obiektami ma
    # co najmniej jedną kategorię), dlatego w trybie pomijającym puste pola
    # odrzucamy zera z zakresu standaryzacji.
    range_values = frequencies if include_zero else [v for v in frequencies if v > 0]
    min_FREQUENCY, max_FREQUENCY = core.min_max_bounds(range_values, include_zero)
    arcpy.AddMessage(f"Using MIN={min_FREQUENCY} and MAX={max_FREQUENCY} for standardization.")

    std_field_name = "FREQUENCY_MIN_MAX"
    if std_field_name not in [f.name for f in arcpy.ListFields(nc_table)]:
        arcpy.management.AddField(nc_table, std_field_name, "DOUBLE")

    with arcpy.da.UpdateCursor(nc_table, ["FREQUENCY", std_field_name]) as cursor:
        for row in cursor:
            row[1] = core.standardize_min_max(row[0], min_FREQUENCY, max_FREQUENCY)
            cursor.updateRow(row)

    arcpy.AddMessage("Standardization completed.")

    # 8. Zapis wyników do NOWEJ klasy obiektów (mapowanie po NEAR_FID jako StatZoneID)
    # Ponieważ safe_write oczekuje pola o nazwie "StatZoneID", dodajemy tymczasowe pole do nc_table
    if "StatZoneID" not in [f.name for f in arcpy.ListFields(nc_table)]:
        arcpy.management.AddField(nc_table, "StatZoneID", "LONG")
    arcpy.management.CalculateField(nc_table, "StatZoneID", "!NEAR_FID!", "PYTHON3")

    core.safe_write_to_new_feature_class(
        grid_fl=grid_fl,
        grid_id_field=grid_id_field,
        result_table=nc_table,
        raw_value_field="FREQUENCY",
        std_value_field=std_field_name,
        output_fc_path=output_fc_path,
        output_raw_field=output_raw_field,
        output_std_field=output_std_field,
        raw_field_type="LONG"
    )

    # 9. Cleanup. Klasa użytkownika nie wymaga sprzątania — Near pracował na
    #    kopii w pamięci, więc nie dopisał do niej pól NEAR_FID/NEAR_DIST.
    arcpy.AddMessage("Cleaning up temporary memory layers...")
    for item in (dissolved_fc, nc_table, stats_table, working_grid_memory,
                 temp_points_memory, non_null_lyr):
        if arcpy.Exists(item):
            arcpy.management.Delete(item)

    arcpy.ClearWorkspaceCache_management()
    arcpy.AddMessage("P_Nc calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError(f"Python error occurred: {str(e)}")

finally:
    arcpy.ClearWorkspaceCache_management()