# coding=utf-8
"""
Geodiversity Tool: A_Ne (Number of Landscape Elements / Patches)
Calculates the number of individual landscape patches per grid cell
and creates a new, standalone output feature class with user-defined fields.
"""

import arcpy
import geodiversity_core as core

arcpy.env.overwriteOutput = True
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

# Ścieżki tymczasowe deklarujemy przed try, aby finally mógł je bezpiecznie
# posprzątać również wtedy, gdy błąd wystąpi przed ich utworzeniem.
stat_zone_field_ID = "StatZoneID"
intersect_fc = "memory\\temp_ne_intersect"
mts_fc = "memory\\temp_ne_mts"
ne_table = "memory\\temp_ne_table"
working_grid_memory = None

try:
    # --- INPUT PARAMETERS ---
    landscape_fl = arcpy.GetParameterAsText(0)   # 0 - Input landscape feature class
    grid_fl = arcpy.GetParameterAsText(1)        # 1 - Analytical grid feature class
    grid_id_field = arcpy.GetParameterAsText(2)  # 2 - Analytical grid identification field
    null_handling_mode = arcpy.GetParameterAsText(3)  # 3 - Handling of empty grid cells

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(4)   # 4 - Output feature class path (DE Feature Class, Output)

    # Domyślne nazwy pól wynikowych. Używane, gdy użytkownik pozostawi pole puste.
    default_raw_field = "R_Ne_feature_A"
    default_std_field = "SR_Ne_feature_A"

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
            "MAX from observed patch counts."
        )
    else:
        arcpy.AddMessage(
            "Empty-cell handling: empty cells ignored in standardization, "
            "MIN and MAX from observed patch counts."
        )

    # 1. Walidacja danych wejściowych
    arcpy.AddMessage("Validating input feature classes...")
    core.check_gdb_feature(grid_fl)
    core.check_gdb_feature(landscape_fl)

    # 2. Przygotowanie bezpiecznej kopii strefowej w pamięci RAM (oryginalna siatka nietknięta!)
    working_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # Czyszczenie śmieci w pamięci (jeśli pozostały po poprzednich sesjach)
    for item in (intersect_fc, mts_fc, ne_table):
        if arcpy.Exists(item):
            arcpy.management.Delete(item)

    # 3. Przecięcie poligonów krajobrazu z siatką analityczną.
    #    Przy wyjściu poligonowym Intersect zapisuje wyłącznie przecięcia
    #    o dodatniej powierzchni. Samo dotknięcie granicy komórki daje linię
    #    lub punkt, więc nie jest liczone jako poligon wewnątrz komórki.
    #    Uwaga: jeśli poligony krajobrazu nachodzą na siebie, Intersect pocię
    #    je wzdłuż wspólnych granic — wynik liczy wtedy fragmenty, a nie
    #    poligony. Warstwa krajobrazu powinna być rozłączna.
    arcpy.AddMessage("Intersecting landscape polygons with analytical grid...")
    arcpy.analysis.Intersect([landscape_fl, working_grid_memory], intersect_fc, "ALL")

    # Brak jakiegokolwiek przecięcia oznacza, że krajobraz nie pokrywa siatki.
    # Zamiast cicho zapisywać same zera zgłaszamy błąd — spójnie z A_Nc,
    # które przerywa pracę, gdy nie ma żadnej kategorii do policzenia.
    if int(arcpy.management.GetCount(intersect_fc)[0]) == 0:
        arcpy.AddError(
            "No landscape features intersect the analytical grid. "
            "Check that both inputs overlap and use the same coordinate system."
        )
        raise arcpy.ExecuteError

    # 4. Rozbicie geometrii wieloczęściowych na pojedyncze poligony.
    #    Po przecięciu jeden poligon może składać się z kilku kawałków; każdy
    #    kawałek jest osobnym poligonem wewnątrz komórki i jest liczony osobno.
    arcpy.AddMessage("Converting multipart elements to singlepart...")
    arcpy.management.MultipartToSinglepart(intersect_fc, mts_fc)

    # Pole robocze do zliczania. Nazwa "Count" mogłaby kolidować z polem
    # odziedziczonym z danych wejściowych, dlatego używamy unikalnej nazwy
    # i usuwamy ją, gdyby jednak istniała w kopii tymczasowej.
    count_field = "NE_CNT"
    mts_field_names = {f.name.lower() for f in arcpy.ListFields(mts_fc)}
    if count_field.lower() in mts_field_names:
        arcpy.management.DeleteField(mts_fc, count_field)

    arcpy.management.AddField(mts_fc, count_field, "SHORT")
    with arcpy.da.UpdateCursor(mts_fc, [count_field]) as cursor:
        for row in cursor:
            row[0] = 1
            cursor.updateRow(row)

    # 5. Zliczenie poligonów w każdej komórce siatki
    arcpy.AddMessage("Calculating summary statistics per grid cell...")
    arcpy.analysis.Statistics(mts_fc, ne_table, [[count_field, "SUM"]], stat_zone_field_ID)

    # 6. Normalizacja Min-Max liczby elementów.
    #    Puste komórki nie trafiają do tabeli Statistics, więc w trybie
    #    "Replace NULL with 0" dolny kraniec zakresu wynosi 0, a w trybie
    #    "Keep NULL" zakres wyznaczają wyłącznie pola z danymi.
    arcpy.AddMessage("Calculating Min-Max standardization for patch counts...")
    sum_field = f"SUM_{count_field}"
    std_field_temp = f"{sum_field}_MM"

    fields_in_table = [f.name for f in arcpy.ListFields(ne_table)]
    if std_field_temp not in fields_in_table:
        arcpy.management.AddField(ne_table, std_field_temp, "DOUBLE")

    counts = [row[0] for row in arcpy.da.SearchCursor(ne_table, [sum_field]) if row[0] is not None]
    if not counts:
        # Zabezpieczenie: Statistics nie powinno zwrócić pustej tabeli po
        # wcześniejszym sprawdzeniu GetCount(intersect_fc), ale nie chcemy
        # dzielić przez zero ani cicho zapisywać samych zer.
        arcpy.AddError("No patch counts were calculated for the analytical grid.")
        raise arcpy.ExecuteError

    min_val, max_val = core.min_max_bounds(counts, include_zero)
    arcpy.AddMessage(f"Using MIN={min_val} and MAX={max_val} for standardization.")

    # Wypełnienie pola znormalizowanego
    with arcpy.da.UpdateCursor(ne_table, [sum_field, std_field_temp]) as cursor:
        for row in cursor:
            row[1] = core.standardize_min_max(row[0], min_val, max_val)
            cursor.updateRow(row)

    # 7. Bezpieczny zapis do NOWEJ klasy obiektów pod wskazaną ścieżką
    core.safe_write_to_new_feature_class(
        grid_fl=grid_fl,
        grid_id_field=grid_id_field,
        result_table=ne_table,
        raw_value_field=sum_field,
        std_value_field=std_field_temp,
        output_fc_path=output_fc_path,
        output_raw_field=output_raw_field,
        output_std_field=output_std_field,
        # Chronimy również warstwę krajobrazu przed nadpisaniem przez output.
        protected_inputs=[landscape_fl],
        raw_field_type="LONG"
    )

    arcpy.AddMessage("Tool A_Ne finished successfully.")

except arcpy.ExecuteError:
    # Błąd geoprzetwarzania — przekazujemy komunikaty narzędzia i przerywamy pracę.
    arcpy.AddError(arcpy.GetMessages(2))
    raise

except Exception as e:
    # Inny błąd Pythona — dodajemy czytelny komunikat i również przerywamy pracę,
    # aby narzędzie w ArcGIS Pro zgłosiło status "Failed", a nie "Completed".
    arcpy.AddError(f"Error in A_Ne execution: {str(e)}")
    raise

finally:
    # Końcowe czyszczenie zasobów tymczasowych — wykonuje się również po błędzie.
    # Delete usuwa datasety z memory\, a ClearWorkspaceCache zwalnia cache/locki.
    arcpy.AddMessage("Cleaning up temporary memory layers...")

    # "memory\\temp_working_grid" jest dodawany jawnie, ponieważ core tworzy go
    # pod stałą nazwą — nawet jeśli prepare_grid_zone_copy przerwie się w połowie.
    temp_items = {intersect_fc, mts_fc, ne_table, working_grid_memory, "memory\\temp_working_grid"}

    for item in temp_items:
        if not item:
            continue
        try:
            if arcpy.Exists(item):
                arcpy.management.Delete(item)
        except Exception as e:
            # Nie przerywamy sprzątania, jeśli pojedynczy dataset jest zablokowany.
            arcpy.AddWarning(f"Could not delete temporary dataset '{item}': {e}")

    arcpy.ClearWorkspaceCache_management()
