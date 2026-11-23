# coding=utf-8
"""
Geodiversity Tool: A_Nc (Number of Polygon Categories)
Calculates the number of unique polygon categories per grid cell
and creates a new, standalone output feature class with user-defined fields.
"""

import arcpy
import geodiversity_core as core

arcpy.env.overwriteOutput = True
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

# Nazwy robocze i lokalizacje tymczasowe w pamięci RAM.
# Definiujemy je przed blokiem try, aby finally mógł je bezpiecznie usunąć
# także wtedy, gdy wyjątek wystąpi przed utworzeniem tych datasetów.
stat_zone_field_ID = "StatZoneID"
dissolved_fl = "memory\\temp_dissolved"
nc_table = "memory\\temp_nc_table"
working_grid_memory = None
non_null_lyr = "temp_nc_non_null_lyr"

try:
    # --- INPUT PARAMETERS ---
    landscape_fl = arcpy.GetParameterAsText(0)    # 0 - Input landscape feature class
    landscape_attr = arcpy.GetParameterAsText(1)  # 1 - Landscape category attribute
    grid_fl = arcpy.GetParameterAsText(2)         # 2 - Analytical grid feature class
    grid_id_field = arcpy.GetParameterAsText(3)   # 3 - Analytical grid identification field
    null_handling_mode = arcpy.GetParameterAsText(4)  # 4 - Handling of empty grid cells

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    out_fc_path = arcpy.GetParameterAsText(5)     # 5 - Output feature class path (DE Feature Class)

    # Domyślne nazwy pól wynikowych. Używane, gdy użytkownik pozostawi pole puste.
    default_raw_field = "R_Nc_feature_A"
    default_std_field = "SR_Nc_feature_A"

    out_raw_field = (arcpy.GetParameterAsText(6) or "").strip()   # 6 - Output partial criteria field name
    out_std_field = (arcpy.GetParameterAsText(7) or "").strip()   # 7 - Output std. partial criteria field name

    if not out_raw_field:
        out_raw_field = default_raw_field
        arcpy.AddMessage(f"Raw output field not provided; using default '{default_raw_field}'.")

    if not out_std_field:
        out_std_field = default_std_field
        arcpy.AddMessage(f"Standardized output field not provided; using default '{default_std_field}'.")

    # ----------------------------------------------------------------------
    # OBSŁUGA PUSTYCH PÓL SIATKI W STANDARYZACJI MIN–MAX
    # ----------------------------------------------------------------------
    include_zero = core.resolve_empty_cell_mode(null_handling_mode)
    if include_zero:
        arcpy.AddMessage(
            "Empty-cell handling: 0 included in the Min–Max range (MIN = 0), "
            "MAX from observed category counts."
        )
    else:
        arcpy.AddMessage(
            "Empty-cell handling: empty cells ignored in standardization, "
            "MIN and MAX from observed category counts."
        )

    # 1. Walidacja danych wejściowych
    arcpy.AddMessage("Validating input feature classes...")
    core.check_gdb_feature(grid_fl)
    core.check_gdb_feature(landscape_fl)

    # Nazwa pola może dotrzeć w postaci kwalifikowanej ("warstwa.pole") —
    # normalizujemy ją przed użyciem w filtrach i w Dissolve.
    landscape_attr = core.resolve_field_name(
        landscape_fl, landscape_attr, "Landscape category attribute"
    )

    # 2. Przygotowanie bezpiecznej kopii strefowej w pamięci RAM (oryginalna siatka nietknięta!)
    working_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # Czyszczenie śmieci w pamięci (jeśli pozostały po poprzednich sesjach)
    # — spójnie z pozostałymi narzędziami wektorowymi (np. A_Ne).
    for item in (dissolved_fl, nc_table, non_null_lyr):
        if arcpy.Exists(item):
            arcpy.management.Delete(item)

    # 3. Walidacja zarezerwowanych nazw pól.
    #    Pola te są używane wewnętrznie przez narzędzie; jeśli wystąpią jako
    #    kategoria krajobrazu, dojdzie do kolizji nazw w wyniku SpatialJoin.
    #    Porównujemy bez względu na wielkość liter, bo GDB traktuje nazwy pól
    #    nierozróżniająco.
    reserved_field_names = {"statzoneid", "join_count", "join_count_mm"}
    if landscape_attr.lower() in reserved_field_names:
        arcpy.AddError(
            f"Field '{landscape_attr}' is reserved for internal use. "
            f"Choose another category attribute."
        )
        raise arcpy.ExecuteError

    # 4. Usunięcie z roboczej kopii siatki pól, które kolidują z polami
    #    tworzonymi przez SpatialJoin / AddField. Oryginalna siatka pozostaje
    #    nietknięta — modyfikujemy wyłącznie kopię w memory\.
    working_fields = {f.name: f.type for f in arcpy.ListFields(working_grid_memory)}
    for field_name in ("Join_Count", "Join_Count_MM"):
        if field_name not in working_fields:
            continue

        if field_name.lower() == grid_id_field.lower():
            arcpy.AddError(
                f"Field '{field_name}' is used as the grid identification field "
                f"and cannot be removed from the working copy."
            )
            raise arcpy.ExecuteError

        arcpy.AddWarning(
            f"Field '{field_name}' already exists in the analytical grid; "
            f"removing it from the in-memory working copy."
        )
        arcpy.management.DeleteField(working_grid_memory, field_name)

    # 5. Pominięcie poligonów bez kategorii (NULL lub pusty ciąg w landscape_attr).
    #    Brak kategorii nie jest osobną klasą. Liczenie go jako kategorii
    #    sztucznie zawyżałoby Nc, dlatego tworzymy warstwę z filtrem zawierającą
    #    wyłącznie rekordy z faktycznie przypisaną kategorią.
    #    Używamy MakeFeatureLayer, a nie Select, ponieważ Select kopiuje geometrię
    #    wejściową i przy danych 3D kończy się błędem 160163 (Z values).
    arcpy.AddMessage("Filtering out features with NULL category value...")
    total_count = int(arcpy.management.GetCount(landscape_fl)[0])

    # Typ pola pobieramy, aby dla pól tekstowych odfiltrować również puste ciągi.
    # Nazwy pól w GDB porównujemy bez względu na wielkość liter.
    landscape_field_types = {f.name.lower(): f.type for f in arcpy.ListFields(landscape_fl)}
    landscape_field_type = landscape_field_types.get(landscape_attr.lower())

    field_delimited = arcpy.AddFieldDelimiters(landscape_fl, landscape_attr)
    where_clause = f"{field_delimited} IS NOT NULL"
    if landscape_field_type == "String":
        # Pusty ciąg to brak kategorii zapisany inaczej niż NULL —
        # traktujemy go identycznie jak NULL i pomijamy w obliczeniach.
        where_clause += f" AND {field_delimited} <> ''"

    arcpy.management.MakeFeatureLayer(landscape_fl, non_null_lyr, where_clause)
    non_null_count = int(arcpy.management.GetCount(non_null_lyr)[0])
    null_count = total_count - non_null_count

    if null_count > 0:
        arcpy.AddWarning(
            f"{null_count} landscape feature(s) have a NULL or empty value in "
            f"'{landscape_attr}' and were ignored in the Nc calculation."
        )

    if non_null_count == 0:
        arcpy.AddError(
            f"All landscape features have a NULL or empty value in '{landscape_attr}'. "
            f"There are no categories to count."
        )
        raise arcpy.ExecuteError

    # 6. Agregacja (Dissolve) poligonów krajobrazowych według kategorii
    arcpy.AddMessage("Dissolving landscape polygons by category attribute...")
    arcpy.management.Dissolve(non_null_lyr, dissolved_fl, landscape_attr)

    # 7. Połączenie przestrzenne (Spatial Join) wykonane na roboczej kopii w RAM
    arcpy.AddMessage("Spatially joining dissolved polygons with analytical grid...")
    arcpy.analysis.SpatialJoin(
        target_features=working_grid_memory,
        join_features=dissolved_fl,
        out_feature_class=nc_table,
        join_operation="JOIN_ONE_TO_ONE",
        join_type="KEEP_ALL",
        match_option="INTERSECT"
    )

    # 8. Normalizacja Min-Max liczby kategorii
    arcpy.AddMessage("Calculating Min-Max standardization for category counts...")
    std_field_temp = "Join_Count_MM"

    fields_in_table = [f.name for f in arcpy.ListFields(nc_table)]
    if std_field_temp not in fields_in_table:
        arcpy.management.AddField(nc_table, std_field_temp, "DOUBLE")

    # Pobranie wartości skrajnych (min/max). Join_Count = 0 oznacza wyłącznie
    # pole bez pokrycia (pole pokryte ma co najmniej jedną kategorię), dlatego
    # w trybie pomijającym puste pola odrzucamy zera z zakresu.
    join_counts = [row[0] for row in arcpy.da.SearchCursor(nc_table, ["Join_Count"]) if row[0] is not None]
    range_values = join_counts if include_zero else [v for v in join_counts if v > 0]
    min_val, max_val = core.min_max_bounds(range_values, include_zero)
    arcpy.AddMessage(f"Using MIN={min_val} and MAX={max_val} for standardization.")

    # Wypełnienie pola znormalizowanego
    with arcpy.da.UpdateCursor(nc_table, ["Join_Count", std_field_temp]) as cursor:
        for row in cursor:
            row[1] = core.standardize_min_max(row[0], min_val, max_val)
            cursor.updateRow(row)

    # 9. Bezpieczny zapis do NOWEJ klasy obiektów pod wskazaną ścieżką (baza z oryginału)
    core.safe_write_to_new_feature_class(
        grid_fl=grid_fl,
        grid_id_field=grid_id_field,
        result_table=nc_table,
        raw_value_field="Join_Count",
        std_value_field=std_field_temp,
        output_fc_path=out_fc_path,
        output_raw_field=out_raw_field,
        output_std_field=out_std_field,
        # Chronimy również warstwę krajobrazu przed nadpisaniem przez output.
        protected_inputs=[landscape_fl],
        raw_field_type="LONG"
    )

    arcpy.AddMessage("Tool A_Nc finished successfully.")

except arcpy.ExecuteError:
    # Błąd geoprzetwarzania — przekazujemy komunikaty narzędzia i przerywamy pracę.
    arcpy.AddError(arcpy.GetMessages(2))
    raise

except Exception as e:
    # Inny błąd Pythona — dodajemy czytelny komunikat i również przerywamy pracę,
    # aby narzędzie w ArcGIS Pro zgłosiło status "Failed", a nie "Completed".
    arcpy.AddError(f"Error in A_Nc execution: {str(e)}")
    raise

finally:
    # Końcowe czyszczenie zasobów tymczasowych — wykonuje się również po błędzie.
    # Delete usuwa datasety z memory\, a ClearWorkspaceCache zwalnia cache/locki.
    arcpy.AddMessage("Cleaning up temporary memory layers...")

    # "memory\\temp_working_grid" jest dodawany jawnie, ponieważ core tworzy go
    # pod stałą nazwą — nawet jeśli prepare_grid_zone_copy przerwie się w połowie.
    temp_items = {dissolved_fl, nc_table, non_null_lyr, working_grid_memory, "memory\\temp_working_grid"}

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