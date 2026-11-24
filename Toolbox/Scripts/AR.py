# coding=utf-8
"""
Toolbox: GeodiversityTools (for ArcGIS Pro)
Tool: AR (Aggregating Ratings)
Version: v.1.0.0.
Short description: Aggregates multiple standardized partial criteria feature classes (with optional weights) into a final summary geodiversity index and performs Min-Max standardization.
Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
2026-11-11
"""

import arcpy
import csv
import io
import geodiversity_core as core

arcpy.env.overwriteOutput = True
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

try:
    # --- INPUT PARAMETERS (Zgodnie z konfiguracją w ArcGIS Pro) ---
    criteria_table = arcpy.GetParameterAsText(0)  # [0] Tabela wartości: [Kryterium, Pole, Waga]
    grid_fl = arcpy.GetParameterAsText(1)  # [1] Bazowa siatka analityczna
    grid_id_field = arcpy.GetParameterAsText(2)  # [2] Pole identyfikatora siatki

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(3)  # [3] Ścieżka wyjściowej klasy obiektów

    # Domyślne nazwy pól wynikowych. Używane, gdy użytkownik pozostawi pole puste.
    default_sum_field = "R_AR"
    default_std_field = "SR_AR"

    output_sum_field = (arcpy.GetParameterAsText(4) or "").strip()  # [4] Nazwa pola sumy atrybutów
    output_std_field = (arcpy.GetParameterAsText(5) or "").strip()  # [5] Nazwa pola zestandaryzowanej sumy

    if not output_sum_field:
        output_sum_field = default_sum_field
        arcpy.AddMessage(f"Sum output field not provided; using default '{default_sum_field}'.")

    if not output_std_field:
        output_std_field = default_std_field
        arcpy.AddMessage(f"Standardized output field not provided; using default '{default_std_field}'.")

    # Parsowanie Table of values z inteligentną obsługą domyślnej wagi (1.0)
    criteria_rows = []
    if criteria_table:
        rows_raw = criteria_table.split(";")
        for row_str in rows_raw:
            row_str = row_str.strip()
            if not row_str:
                continue

            f = io.StringIO(row_str)
            reader = csv.reader(f, delimiter=' ')
            parts = next(reader, None)

            if parts:
                try:
                    # Próbujemy pobrać wagę jako ostatni element
                    weight = float(parts[-1])
                    field_name = parts[-2]
                    layer_path = " ".join(parts[:-2]).strip("'").strip('"')
                except (ValueError, IndexError):
                    # Jeśli waga nie została podana (lub nie jest liczbą), domyślnie przyjmujemy 1.0
                    weight = 1.0
                    if len(parts) >= 2:
                        field_name = parts[-1]
                        layer_path = " ".join(parts[:-1]).strip("'").strip('"')
                    else:
                        continue

                criteria_rows.append((layer_path, field_name, weight))

    if not criteria_rows:
        raise Exception("No valid criteria rows provided in the Value Table.")

    arcpy.AddMessage(f"Loaded {len(criteria_rows)} criteria rows for aggregation.")

    # 1. Walidacja siatki bazowej i utworzenie wyjściowej klasy obiektów
    core.check_gdb_feature(grid_fl)
    core.check_2d(grid_fl, "Analytical grid")

    # Nazwa pola może dotrzeć w postaci kwalifikowanej ("grid_1000.OBJECTID").
    grid_id_field = core.resolve_field_name(
        grid_fl, grid_id_field, "Analytical grid identification field"
    )

    arcpy.AddMessage(f"Creating output feature class from reference grid at: {output_fc_path}...")
    if arcpy.Exists(output_fc_path):
        arcpy.management.Delete(output_fc_path)

    # Klonujemy geometrię oryginalnej siatki jako bazę wynikową (non-destructive)
    arcpy.management.CopyFeatures(grid_fl, output_fc_path)
    while not arcpy.Exists(output_fc_path):
        pass

    # 2. Odczyt danych z poszczególnych kryteriów do słowników RAM i obliczenie sumy ważonej
    aggregated_scores = {}
    total_weight = 0.0

    for idx, (layer, field, weight) in enumerate(criteria_rows):
        arcpy.AddMessage(f"Processing criterion {idx + 1}: {layer} (Field: {field}, Weight: {weight})...")
        core.check_gdb_feature(layer)

        layer_dict = {}
        with arcpy.da.SearchCursor(layer, [grid_id_field, field]) as cursor:
            for row in cursor:
                g_id = row[0]
                val = row[1]
                if g_id is not None:
                    layer_dict[g_id] = float(val) if val is not None else 0.0

        for g_id, val in layer_dict.items():
            if g_id not in aggregated_scores:
                aggregated_scores[g_id] = 0.0
            aggregated_scores[g_id] += val * weight

        total_weight += weight

    # 3. Dodanie nowych pól wynikowych do docelowej klasy obiektów
    arcpy.management.AddField(output_fc_path, output_sum_field, "DOUBLE", field_alias=output_sum_field)
    arcpy.management.AddField(output_fc_path, output_std_field, "DOUBLE", field_alias=output_std_field)

    # 4. Zapis surowych sum do nowej klasy obiektów oraz zebranie wartości do Min-Max
    raw_sums = []
    with arcpy.da.UpdateCursor(output_fc_path, [grid_id_field, output_sum_field]) as cursor:
        for row in cursor:
            g_id = row[0]
            if g_id in aggregated_scores:
                s_val = aggregated_scores[g_id]
                row[1] = s_val
                raw_sums.append(s_val)
            else:
                row[1] = 0.0
                raw_sums.append(0.0)
            cursor.updateRow(row)

    # 5. Min-Max Standardization ostatecznej sumy
    arcpy.AddMessage("Calculating Min-Max standardization for aggregated index...")
    min_sum = float(min(raw_sums)) if raw_sums else 0.0
    max_sum = float(max(raw_sums)) if raw_sums else 0.0

    with arcpy.da.UpdateCursor(output_fc_path, [output_sum_field, output_std_field]) as cursor:
        for row in cursor:
            raw_v = row[0]
            if raw_v is None:
                row[1] = 0.0
            elif max_sum == min_sum:
                row[1] = 0.0
            else:
                row[1] = (raw_v - min_sum) / (max_sum - min_sum)
            cursor.updateRow(row)

    # 6. Automatyczne dodanie do aktywnej mapy w ArcGIS Pro.
    #    Poza ArcGIS Pro (lub bez aktywnej mapy) nie przerywamy narzędzia —
    #    output jest już zapisany, więc zgłaszamy tylko ostrzeżenie.
    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        map_obj = aprx.activeMap
        if map_obj:
            map_obj.addDataFromPath(output_fc_path)
        arcpy.AddMessage("Aggregation completed successfully. Output layer added to map.")
    except Exception as exc:
        arcpy.AddWarning(
            f"Aggregation completed successfully, but the output could not be "
            f"added to the current map: {exc}"
        )

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError(f"Python error occurred: {str(e)}")

finally:
    arcpy.ClearWorkspaceCache_management()