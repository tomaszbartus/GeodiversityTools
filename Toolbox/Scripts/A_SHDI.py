# coding=utf-8
"""
Geodiversity Tool: A_SHDI (Shannon-Weaver Diversity Index)
Calculates the Shannon–Weaver diversity index (SHDI) for a selected landscape feature
in each polygon of an analytical grid and creates a new, standalone output feature class with user-defined fields.
Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
Refactored for GeodiversityTools Core Architecture
"""

import arcpy
import math
import geodiversity_core as core

arcpy.env.overwriteOutput = True
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

# Nazwy robocze i lokalizacje tymczasowe w pamięci RAM.
# Definiujemy je przed blokiem try, aby finally mógł je bezpiecznie usunąć
# także wtedy, gdy wyjątek wystąpi przed utworzeniem tych datasetów.
stat_zone_field_ID = "StatZoneID"
out_intersect_fc = "memory\\temp_shdi_intersect"
out_mts_fc = "memory\\temp_shdi_mts"
freq_table = "memory\\temp_shdi_freq"
shdi_table = "memory\\temp_shdi_table"
working_grid_memory = None
non_null_lyr = "temp_shdi_non_null_lyr"

try:
    # --- INPUT PARAMETERS ---
    landscape_fl = arcpy.GetParameterAsText(0)  # 0 - Input landscape feature layer
    landscape_attr = arcpy.GetParameterAsText(1)  # 1 - Landscape category attribute
    grid_fl = arcpy.GetParameterAsText(2)  # 2 - Analytical grid feature layer
    grid_id_field = arcpy.GetParameterAsText(3)  # 3 - Analytical grid identification field
    null_handling_mode = arcpy.GetParameterAsText(4)  # 4 - Handling of empty grid cells

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(5)  # 5 - Output feature class path (DE Feature Class, Output)

    # Domyślne nazwy pól wynikowych. Używane, gdy użytkownik pozostawi pole puste.
    default_raw_field = "R_SHDI_feature_A"
    default_std_field = "SR_SHDI_feature_A"

    output_raw_field = (arcpy.GetParameterAsText(6) or "").strip()  # 6 - Output partial criteria field name
    output_std_field = (arcpy.GetParameterAsText(7) or "").strip()  # 7 - Output std. partial criteria field name

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
            "MAX from observed SHDI values."
        )
    else:
        arcpy.AddMessage(
            "Empty-cell handling: empty cells ignored in standardization, "
            "MIN and MAX from observed SHDI values."
        )

    # 1. Walidacja danych wejściowych
    arcpy.AddMessage("Validating input feature classes...")
    core.check_gdb_feature(grid_fl)
    core.check_gdb_feature(landscape_fl)

    # 2. Walidacja pola kategorii krajobrazu.
    #    Domena parametru w .atbx dopuszcza tylko Short/Long/BigInteger/Text,
    #    ale skrypt może być uruchomiony również poza ArcGIS Pro, dlatego
    #    sprawdzamy to także tutaj.
    #    Nazwa pola może dotrzeć w postaci kwalifikowanej ("warstwa.pole") —
    #    normalizujemy ją przed sprawdzeniem typu i użyciem w filtrach.
    landscape_attr = core.resolve_field_name(
        landscape_fl, landscape_attr, "Landscape category attribute"
    )
    landscape_fields = {f.name.lower(): f for f in arcpy.ListFields(landscape_fl)}
    landscape_field = landscape_fields.get(landscape_attr.lower())

    if landscape_field is None:
        arcpy.AddError(
            f"Error: Field '{landscape_attr}' does not exist in the landscape feature class."
        )
        raise arcpy.ExecuteError

    allowed_category_types = ("String", "SmallInteger", "Integer", "BigInteger")
    if landscape_field.type not in allowed_category_types:
        arcpy.AddError(
            f"Error: Field '{landscape_attr}' has type '{landscape_field.type}'. "
            f"Use a Short, Long, BigInteger or Text field as the landscape "
            f"category attribute."
        )
        raise arcpy.ExecuteError

    # 3. StatZoneID jest nazwą zarezerwowaną. safe_write_to_new_feature_class
    #    odczytuje wynik właśnie po tym polu, więc krajobraz nie może mieć pola
    #    o tej samej nazwie — Intersect przemianowałby jedno z nich i wynik
    #    zostałby po cichu zapisany do złych komórek.
    if stat_zone_field_ID.lower() in landscape_fields:
        arcpy.AddError(
            f"Field '{stat_zone_field_ID}' in the landscape feature class is "
            f"reserved for internal use. Rename or remove it before running the tool."
        )
        raise arcpy.ExecuteError

    # 4. Przygotowanie bezpiecznej kopii strefowej w pamięci RAM
    #    (oryginalna siatka użytkownika pozostaje nietknięta).
    working_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # 5. Redukcja pól roboczej kopii siatki do samego StatZoneID.
    #    Dzięki temu pola siatki (np. ID) nie kolidują z polem kategorii
    #    krajobrazu podczas Intersect. Wcześniej taka kolizja przemianowywała
    #    landscape_attr (np. na "ID_1") i po cichu psuła wyniki.
    for field in arcpy.ListFields(working_grid_memory):
        if field.required or field.name.lower() == stat_zone_field_ID.lower():
            continue
        arcpy.management.DeleteField(working_grid_memory, field.name)

    # Czyszczenie śmieci w pamięci (jeśli pozostały po poprzednich sesjach)
    for item in (out_intersect_fc, out_mts_fc, freq_table, shdi_table, non_null_lyr):
        if arcpy.Exists(item):
            arcpy.management.Delete(item)

    # 6. Pominięcie poligonów bez kategorii (NULL lub pusty ciąg).
    #    Brak kategorii nie jest osobną klasą — liczenie go jako klasy
    #    sztucznie zawyżałoby SHDI. MakeFeatureLayer nie kopiuje geometrii,
    #    więc dane 3D nie powodują błędu 160163.
    arcpy.AddMessage("Filtering out features with NULL category value...")
    total_count = int(arcpy.management.GetCount(landscape_fl)[0])

    if total_count == 0:
        arcpy.AddError("The landscape feature class contains no features.")
        raise arcpy.ExecuteError

    # Nazwy pól w GDB porównujemy bez względu na wielkość liter.
    field_delimited = arcpy.AddFieldDelimiters(landscape_fl, landscape_attr)
    where_clause = f"{field_delimited} IS NOT NULL"
    if landscape_field.type == "String":
        # Pusty ciąg to brak kategorii zapisany inaczej niż NULL —
        # traktujemy go identycznie jak NULL i pomijamy w obliczeniach.
        where_clause += f" AND {field_delimited} <> ''"

    arcpy.management.MakeFeatureLayer(landscape_fl, non_null_lyr, where_clause)
    non_null_count = int(arcpy.management.GetCount(non_null_lyr)[0])
    null_count = total_count - non_null_count

    if null_count > 0:
        arcpy.AddWarning(
            f"{null_count} landscape feature(s) have a NULL or empty value in "
            f"'{landscape_attr}' and were ignored in the SHDI calculation."
        )

    if non_null_count == 0:
        arcpy.AddError(
            f"All landscape features have a NULL or empty value in "
            f"'{landscape_attr}'. There are no categories to calculate SHDI for."
        )
        raise arcpy.ExecuteError

    # 7. Przecięcie poligonów krajobrazu z siatką analityczną.
    #    Przy wyjściu poligonowym Intersect zapisuje wyłącznie przecięcia
    #    o dodatniej powierzchni — samo dotknięcie granicy komórki nie tworzy
    #    poligonu i nie wpływa na proporcje powierzchni.
    arcpy.AddMessage("Intersecting landscape polygons with the analytical grid...")
    arcpy.analysis.Intersect([non_null_lyr, working_grid_memory], out_intersect_fc, "ALL", "", "INPUT")

    if int(arcpy.management.GetCount(out_intersect_fc)[0]) == 0:
        arcpy.AddError(
            "No landscape features with a valid category value intersect the "
            "analytical grid. Check that both inputs overlap and use the same "
            "coordinate system."
        )
        raise arcpy.ExecuteError

    # Ostrzeżenie o układzie geograficznym: !SHAPE.area! zwraca wtedy stopnie
    # kwadratowe, więc proporcje powierzchni (a zatem i SHDI) są przybliżone.
    intersect_sr = arcpy.Describe(out_intersect_fc).spatialReference
    if getattr(intersect_sr, "type", None) == "Geographic":
        arcpy.AddWarning(
            f"The processing coordinate system is geographic "
            f"('{intersect_sr.name}'). Areas are calculated in square degrees, "
            f"so SHDI values may be approximate. Use a projected coordinate "
            f"system for accurate results."
        )

    # 8. Usunięcie zbędnych atrybutów z wyniku Intersect. Zostawiamy tylko
    #    StatZoneID i pole kategorii, dzięki czemu nazwy pól roboczych
    #    (SHDI_AREA, SHDI_P itd.) nie mogą kolidować z polami wejściowymi.
    keep_fields = {stat_zone_field_ID.lower(), landscape_attr.lower()}
    for field in arcpy.ListFields(out_intersect_fc):
        if field.required or field.name.lower() in keep_fields:
            continue
        arcpy.management.DeleteField(out_intersect_fc, field.name)

    intersect_field_names = {f.name.lower() for f in arcpy.ListFields(out_intersect_fc)}
    if landscape_attr.lower() not in intersect_field_names:
        arcpy.AddError(
            f"Category field '{landscape_attr}' was not preserved by Intersect. "
            f"Check the input field names."
        )
        raise arcpy.ExecuteError

    # 9. Rozbicie geometrii wieloczęściowych na pojedyncze poligony.
    #    Dane po Clip mogą zawierać multipoligony — każdy kawałek ma być
    #    osobnym poligonem, tak jak w pozostałych narzędziach poligonowych.
    #    Na wartość SHDI nie wpływa to ujemnie: powierzchnie części są
    #    sumowane per kategoria w kroku 11.
    arcpy.AddMessage("Converting multipart elements to singlepart...")
    arcpy.management.MultipartToSinglepart(out_intersect_fc, out_mts_fc)

    # 10. Pole powierzchni. Nazwa jest unikalna, bo landscape_attr może
    #     nazywać się np. "SHDI_AREA".
    area_field = "SHDI_AREA"
    mts_field_names = {f.name.lower() for f in arcpy.ListFields(out_mts_fc)}
    suffix = 1
    while area_field.lower() in mts_field_names:
        area_field = f"SHDI_AREA_{suffix}"
        suffix += 1

    arcpy.management.AddField(out_mts_fc, area_field, "DOUBLE")
    arcpy.management.CalculateField(out_mts_fc, area_field, "!SHAPE.area!", "PYTHON3")

    # 11. Suma powierzchni per (komórka, kategoria).
    arcpy.AddMessage("Calculating area statistics per grid cell and category...")
    arcpy.analysis.Statistics(
        out_mts_fc,
        freq_table,
        [[area_field, "SUM"]],
        [stat_zone_field_ID, landscape_attr]
    )

    # Deterministyczna nazwa pola sumy: Statistics tworzy "SUM_<pole>".
    freq_field_names = {f.name.lower(): f.name for f in arcpy.ListFields(freq_table)}
    area_sum_field = f"SUM_{area_field}"
    if area_sum_field.lower() in freq_field_names:
        area_sum_field = freq_field_names[area_sum_field.lower()]
    else:
        # Zabezpieczenie na wypadek skrócenia nazwy przez geobazę.
        sum_candidates = [n for n in freq_field_names.values() if n.lower().startswith("sum_")]
        if not sum_candidates:
            arcpy.AddError("Could not find the summed area field in the statistics table.")
            raise arcpy.ExecuteError
        area_sum_field = sum_candidates[0]

    # Pole kategorii nie jest już potrzebne — usuwamy je, aby nazwy pól
    # SHDI_P / SHDI_LN_P / SHDI_TERM były na pewno unikalne.
    arcpy.management.DeleteField(freq_table, landscape_attr)

    p_field = "SHDI_P"
    ln_p_field = "SHDI_LN_P"
    term_field = "SHDI_TERM"
    arcpy.management.AddField(freq_table, p_field, "DOUBLE")
    arcpy.management.AddField(freq_table, ln_p_field, "DOUBLE")
    arcpy.management.AddField(freq_table, term_field, "DOUBLE")

    # 12. p_i = A_i / A_total w komórce; H = -Σ p_i·ln(p_i).
    total_area = {}
    with arcpy.da.SearchCursor(freq_table, [stat_zone_field_ID, area_sum_field]) as cursor:
        for zone_id, area in cursor:
            if zone_id is None:
                continue
            area_val = float(area) if area is not None else 0.0
            total_area[zone_id] = total_area.get(zone_id, 0.0) + area_val

    with arcpy.da.UpdateCursor(
        freq_table,
        [stat_zone_field_ID, area_sum_field, p_field, ln_p_field, term_field]
    ) as cursor:
        for zone_id, area, p_old, ln_p_old, term_old in cursor:
            area_val = float(area) if area is not None else 0.0
            zone_total = total_area.get(zone_id, 0.0)
            p_val = area_val / zone_total if zone_total > 0 else 0.0

            # Zabezpieczenie przed minimalnym przekroczeniem 1.0 przez zaokrąglenia.
            p_val = min(max(p_val, 0.0), 1.0)

            if p_val > 0:
                ln_p_val = math.log(p_val)
                term_val = -p_val * ln_p_val
            else:
                ln_p_val = 0.0
                term_val = 0.0

            cursor.updateRow([zone_id, area_val, p_val, ln_p_val, term_val])

    # 13. Suma składników SHDI per komórka.
    arcpy.AddMessage("Aggregating SHDI values per grid cell...")
    arcpy.analysis.Statistics(freq_table, shdi_table, [[term_field, "SUM"]], stat_zone_field_ID)

    shdi_field_names = {f.name.lower(): f.name for f in arcpy.ListFields(shdi_table)}
    sum_term_field = f"SUM_{term_field}"
    if sum_term_field.lower() in shdi_field_names:
        sum_term_field = shdi_field_names[sum_term_field.lower()]
    else:
        sum_candidates = [n for n in shdi_field_names.values() if n.lower().startswith("sum_")]
        if not sum_candidates:
            arcpy.AddError("Could not find the summed SHDI field in the statistics table.")
            raise arcpy.ExecuteError
        sum_term_field = sum_candidates[0]

    # 14. Normalizacja Min–Max. Puste komórki nie trafiają do tabeli
    #     statystyk, więc w trybie "Replace NULL with 0" dolny kraniec zakresu
    #     wynosi 0, a w trybie "Keep NULL" zakres wyznaczają wyłącznie pola
    #     z danymi.
    arcpy.AddMessage("Standardizing SHDI (Min–Max)...")
    h_values = [
        float(row[0]) for row in arcpy.da.SearchCursor(shdi_table, [sum_term_field])
        if row[0] is not None
    ]

    if not h_values:
        arcpy.AddError("No SHDI values were calculated for the analytical grid.")
        raise arcpy.ExecuteError

    # Wartość 0 jest tu prawdziwą entropią pola o jednej kategorii, dlatego
    # nie odfiltrowujemy zer — puste pola po prostu nie mają wiersza w tabeli.
    min_val, max_val = core.min_max_bounds(h_values, include_zero)
    arcpy.AddMessage(f"Using MIN={min_val} and MAX={max_val} for standardization.")

    std_field_temp = f"{sum_term_field}_MM"
    existing_std_fields = {f.name.lower() for f in arcpy.ListFields(shdi_table)}
    if std_field_temp.lower() not in existing_std_fields:
        arcpy.management.AddField(shdi_table, std_field_temp, "DOUBLE")

    with arcpy.da.UpdateCursor(shdi_table, [sum_term_field, std_field_temp]) as cursor:
        for row in cursor:
            row[1] = core.standardize_min_max(row[0], min_val, max_val)
            cursor.updateRow(row)

    # 15. Bezpieczny zapis do NOWEJ klasy obiektów pod wskazaną ścieżką.
    core.safe_write_to_new_feature_class(
        grid_fl=grid_fl,
        grid_id_field=grid_id_field,
        result_table=shdi_table,
        raw_value_field=sum_term_field,
        std_value_field=std_field_temp,
        output_fc_path=output_fc_path,
        output_raw_field=output_raw_field,
        output_std_field=output_std_field,
        # Chronimy również warstwę krajobrazu przed nadpisaniem przez output.
        protected_inputs=[landscape_fl]
    )

    arcpy.AddMessage("Tool A_SHDI finished successfully.")

except arcpy.ExecuteError:
    # Błąd geoprzetwarzania — przekazujemy komunikaty narzędzia i przerywamy pracę.
    arcpy.AddError(arcpy.GetMessages(2))
    raise

except Exception as e:
    # Inny błąd Pythona — dodajemy czytelny komunikat i również przerywamy pracę,
    # aby narzędzie w ArcGIS Pro zgłosiło status "Failed", a nie "Completed".
    arcpy.AddError(f"Error in A_SHDI execution: {str(e)}")
    raise

finally:
    # Końcowe czyszczenie zasobów tymczasowych — wykonuje się również po błędzie.
    arcpy.AddMessage("Cleaning up temporary memory layers...")

    # "memory\\temp_working_grid" jest dodawany jawnie, ponieważ core tworzy go
    # pod stałą nazwą — nawet jeśli prepare_grid_zone_copy przerwie się w połowie.
    temp_items = {
        out_intersect_fc, out_mts_fc, freq_table, shdi_table,
        non_null_lyr, working_grid_memory, "memory\\temp_working_grid"
    }

    for item in temp_items:
        if not item:
            continue
        try:
            if arcpy.Exists(item):
                arcpy.management.Delete(item)
        except Exception as e:
            # Nie przerywamy sprzątania, jeśli pojedynczy dataset jest zablokowany.
            arcpy.AddWarning(f"Could not delete temporary dataset '{item}': {e}")

    try:
        arcpy.ClearWorkspaceCache_management()
    except Exception:
        # Brak cache do wyczyszczenia nie jest błędem krytycznym.
        pass
