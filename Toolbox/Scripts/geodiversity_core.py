# coding=utf-8
import os

import arcpy

# Nazwa pola strefowego wspólnego dla wszystkich narzędzi georóżnorodności.
ZONE_FIELD_NAME = "StatZoneID"

# StatZoneID jest zawsze tworzone jako LONG, dlatego identyfikator siatki
# musi mieścić się w tym zakresie.
LONG_MIN = -2147483648
LONG_MAX = 2147483647

# Typy pól dopuszczalne dla identyfikatora siatki.
# Uwaga: arcpy zwraca nazwy typów pola ("SmallInteger", "Integer"),
# a nie nazwy z domeny narzędzia ("Short", "Long").
ALLOWED_ID_FIELD_TYPES = ("SmallInteger", "Integer", "BigInteger", "OID")

# Etykiety opcji obsługi pustych pól siatki (identyczne we wszystkich
# narzędziach wektorowych poza AR). Wartość 0 w klasie wynikowej jest zawsze
# zapisywana dla pustego pola; opcja decyduje wyłącznie o zakresie Min–Max.
EMPTY_CELLS_ZERO = "Empty cells = 0 (MIN = 0)"
EMPTY_CELLS_IGNORED = "Empty cells ignored in standardization (MIN/MAX from observed values)"


def resolve_empty_cell_mode(value):
    """Zamienia etykietę wybraną w formularzu na informację, czy zero wchodzi
    do zakresu Min–Max.

    Zwraca True, gdy dolny kraniec zakresu ma wynosić 0, albo False, gdy puste
    pola mają być pominięte przy wyznaczaniu zakresu. Brak wyboru lub nieznana
    etykieta kończy się wyjątkiem — skrypt nie ma żadnej wartości domyślnej.
    """
    text = (value or "").strip()
    if not text:
        raise Exception(
            "Empty-cell handling mode was not selected. "
            "Choose one of the options in the tool form."
        )

    normalized = " ".join(text.replace("¦", "|").split()).lower()
    if normalized.startswith("empty cells ignored"):
        return False
    if normalized.startswith("empty cells = 0") or normalized.startswith("empty cells=0"):
        return True

    raise Exception(f"Unrecognized empty-cell handling mode: '{text}'.")


def min_max_bounds(values, include_zero):
    """Zwraca (MIN, MAX) dla listy wartości.

    include_zero=True  -> MIN = 0 (zero jest dolnym krańcem skali),
    include_zero=False -> MIN = najmniejsza wartość z listy.

    Wartości None są pomijane. Pusta lista daje (0.0, 0.0).
    """
    numeric = [float(v) for v in values if v is not None]
    if not numeric:
        return 0.0, 0.0

    low = 0.0 if include_zero else min(numeric)
    return low, max(numeric)


def standardize_min_max(value, low, high):
    """Standaryzacja Min–Max z zabezpieczeniem pustych pól.

    Zwraca 0.0 dla wartości None, dla stałego zakresu (high <= low) oraz dla
    wartości leżących poniżej dolnego krańca zakresu. Drugi przypadek obejmuje
    puste pola w trybie pomijającym: ich wartość surowa (0) leży poniżej MIN,
    więc standaryzowana wartość jest przypisywana, a nie liczona ze wzoru.
    """
    if value is None or high <= low:
        return 0.0

    numeric = float(value)
    if numeric <= low:
        return 0.0

    return (numeric - low) / (high - low)


def _normalize_path(path):
    """Zwraca znormalizowaną ścieżkę, aby porównywać datasety niezależnie od
    wielkości liter i separatorów."""
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(path)).rstrip("\\/")


def _catalog_path(fc):
    """Zwraca catalogPath dla istniejącego datasetu lub oryginalny tekst,
    jeśli datasetu nie da się opisać (np. jeszcze nie istnieje)."""
    try:
        return arcpy.Describe(fc).catalogPath
    except Exception:
        return fc


def _validate_output_field_name(field_name, role, grid_fl, grid_id_field, other_name=None):
    """
    Sprawdza poprawność nazwy pola wyjściowego zanim cokolwiek zostanie
    utworzone. Dzięki temu błąd jest zgłaszany od razu, a nie po wykonaniu
    Dissolve/SpatialJoin.
    """
    if not field_name or not field_name.strip():
        arcpy.AddError(f"Error: {role} name is empty.")
        raise arcpy.ExecuteError

    name = field_name.strip()

    if len(name) > 64:
        arcpy.AddError(f"Error: {role} name '{name}' is longer than 64 characters.")
        raise arcpy.ExecuteError

    # W geobazie nazwa pola musi zaczynać się od litery i może zawierać
    # litery, cyfry, podkreślenia oraz spacje.
    if not name[0].isalpha() or not all(ch.isalnum() or ch in "_ " for ch in name):
        arcpy.AddError(
            f"Error: {role} name '{name}' is not a valid geodatabase field name. "
            f"Use letters, digits and underscores, starting with a letter."
        )
        raise arcpy.ExecuteError

    if other_name and name.lower() == other_name.strip().lower():
        arcpy.AddError(
            f"Error: {role} name '{name}' is the same as the other output field name. "
            f"Choose two different names."
        )
        raise arcpy.ExecuteError

    if grid_id_field and name.lower() == grid_id_field.strip().lower():
        arcpy.AddError(
            f"Error: {role} name '{name}' is used as the grid identification field. "
            f"Choose another name."
        )
        raise arcpy.ExecuteError

    grid_field_names = {f.name.lower() for f in arcpy.ListFields(grid_fl)}
    if name.lower() in grid_field_names:
        arcpy.AddError(
            f"Error: {role} name '{name}' already exists in the analytical grid. "
            f"Choose another name."
        )
        raise arcpy.ExecuteError

    # Zwracamy oczyszczoną nazwę, aby dalsze operacje nie używały spacji
    # na początku lub końcu wprowadzonej nazwy.
    return name


def _validate_output_workspace(output_fc_path):
    """
    Blokuje zapis wyników do shapefile oraz do folderów, które nie są
    geobazą. W takich miejscach AddField ignoruje aliasy, skraca nazwy pól
    i stosuje inne limity, co kończy się błędem w połowie zapisu.
    """
    if output_fc_path.lower().endswith(".shp"):
        arcpy.AddError(
            f"Error: Output '{output_fc_path}' is a shapefile. "
            f"Geodiversity Tools require GDB feature classes."
        )
        raise arcpy.ExecuteError

    workspace = os.path.dirname(output_fc_path)
    if not workspace or not arcpy.Exists(workspace):
        return

    desc = arcpy.Describe(workspace)
    if getattr(desc, "workspaceType", None) == "FileSystem":
        arcpy.AddError(
            f"Error: Output workspace '{workspace}' is a folder, not a geodatabase. "
            f"Choose a feature class inside a geodatabase."
        )
        raise arcpy.ExecuteError


def _validate_grid_id_field(fc, field_name):
    """
    Sprawdza, czy pole identyfikacyjne siatki nadaje się do użycia jako
    StatZoneID (LONG): poprawny typ, brak NULL-i, unikalne wartości,
    a dla BigInteger także mieszczenie się w zakresie LONG.
    """
    fields = {f.name.lower(): f for f in arcpy.ListFields(fc)}
    field = fields.get(field_name.lower())

    if field is None:
        arcpy.AddError(
            f"Error: Field '{field_name}' does not exist in the analytical grid."
        )
        raise arcpy.ExecuteError

    if field.type not in ALLOWED_ID_FIELD_TYPES:
        arcpy.AddError(
            f"Error: Field '{field_name}' has type '{field.type}'. "
            f"Use a Short, Long, BigInteger or ObjectID field as the grid "
            f"identification field."
        )
        raise arcpy.ExecuteError

    # OID jest unikalny i niepusty z definicji - skanowanie nie jest potrzebne.
    if field.type == "OID":
        return

    seen = set()
    null_count = 0
    min_value = None
    max_value = None

    with arcpy.da.SearchCursor(fc, [field_name]) as cursor:
        for (value,) in cursor:
            if value is None:
                null_count += 1
                continue

            if value in seen:
                arcpy.AddError(
                    f"Error: Field '{field_name}' contains a duplicate value "
                    f"'{value}'. Grid identification values must be unique."
                )
                raise arcpy.ExecuteError
            seen.add(value)

            if field.type == "BigInteger":
                if min_value is None or value < min_value:
                    min_value = value
                if max_value is None or value > max_value:
                    max_value = value

    if null_count > 0:
        arcpy.AddError(
            f"Error: Field '{field_name}' contains {null_count} NULL value(s). "
            f"Grid identification values cannot be NULL."
        )
        raise arcpy.ExecuteError

    if field.type == "BigInteger" and min_value is not None:
        if min_value < LONG_MIN or max_value > LONG_MAX:
            arcpy.AddError(
                f"Error: Field '{field_name}' contains values outside the LONG range "
                f"({LONG_MIN} to {LONG_MAX}). Use a Long field or values that fit "
                f"in that range."
            )
            raise arcpy.ExecuteError


def check_gdb_feature(fc):
    """Blokuje pliki Shapefile, wymagając baz GDB."""
    desc = arcpy.Describe(fc)
    if desc.dataType == "ShapeFile" or desc.catalogPath.lower().endswith(".shp"):
        arcpy.AddError(f"Error: Layer '{desc.name}' is a Shapefile.")
        arcpy.AddError("Geodiversity Tools require GDB feature classes.")
        raise arcpy.ExecuteError


def check_2d(fc, role="Input feature class"):
    """
    Blokuje dane z geometrią Z/M. Narzędzia kopiujące geometrię (Select,
    CopyFeatures) przy ustawionym outputZFlag = "Disabled" kończą się wtedy
    błędem 160163 ("Geometry cannot have Z values"), dlatego wymagamy
    danych 2D.
    """
    desc = arcpy.Describe(fc)
    has_z = getattr(desc, "hasZ", False)
    has_m = getattr(desc, "hasM", False)
    if not (has_z or has_m):
        return

    dimensions = "/".join(
        name for name, present in (("Z", has_z), ("M", has_m)) if present
    )
    arcpy.AddError(
        f"Error: {role} '{desc.name}' contains {dimensions} values. "
        f"Geodiversity Tools require 2D feature classes."
    )
    raise arcpy.ExecuteError


def resolve_field_name(fc, field_value, role="Field"):
    """Zamienia wartość parametru typu Field na nazwę pola istniejącego w 'fc'.

    ArcGIS Pro potrafi przekazać nazwę kwalifikowaną (np. "geostanowiska.ranga")
    albo pusty ciąg, gdy pole nie zostało wybrane. Dissolve i inne narzędzia
    zgłaszają wtedy mylący błąd "ERROR 999999 ... The table was not found.",
    dlatego nazwę normalizujemy i sprawdzamy przed użyciem.

    Zwraca nazwę pola w brzmieniu z klasy obiektów.
    """
    text = (field_value or "").strip()
    if not text:
        raise Exception(
            f"{role} was not selected. Choose a field in the tool form."
        )

    # Nazwa kwalifikowana: "warstwa.pole" lub "baza.gdb\\klasa.pole".
    # Nazwy pól w GDB nie zawierają kropek, więc wystarczy ostatni segment.
    name = text.split(".")[-1].strip()
    for field in arcpy.ListFields(fc):
        if field.name.lower() == name.lower():
            return field.name

    raise Exception(
        f"{role} '{text}' was not found in '{arcpy.Describe(fc).name}'."
    )


def make_category_layer(fc, field_name, out_layer):
    """Tworzy warstwę z obiektami, którym przypisano kategorię.

    Obiekty z NULL lub pustym ciągiem w polu kategorii nie są odrębną klasą —
    są pomijane w obliczeniach (zob. rozdział 3.8.1 manuala). Używamy
    MakeFeatureLayer, a nie Select, ponieważ Select kopiuje geometrię wejściową
    i przy danych 3D kończy się błędem 160163 (Z values).

    Zwraca nazwę utworzonej warstwy.
    """
    total_count = int(arcpy.management.GetCount(fc)[0])

    # Typ pola pobieramy, aby dla pól tekstowych odfiltrować również puste ciągi.
    field_types = {f.name.lower(): f.type for f in arcpy.ListFields(fc)}
    field_type = field_types.get(field_name.lower())

    field_delimited = arcpy.AddFieldDelimiters(fc, field_name)
    where_clause = f"{field_delimited} IS NOT NULL"
    if field_type == "String":
        # Pusty ciąg to brak kategorii zapisany inaczej niż NULL —
        # traktujemy go identycznie jak NULL i pomijamy w obliczeniach.
        where_clause += f" AND {field_delimited} <> ''"

    arcpy.management.MakeFeatureLayer(fc, out_layer, where_clause)
    non_null_count = int(arcpy.management.GetCount(out_layer)[0])
    null_count = total_count - non_null_count

    if null_count > 0:
        arcpy.AddWarning(
            f"{null_count} landscape feature(s) have a NULL or empty value in "
            f"'{field_name}' and were ignored in the calculation."
        )

    if non_null_count == 0:
        arcpy.AddError(
            f"All landscape features have a NULL or empty value in '{field_name}'. "
            f"There are no categories to count."
        )
        raise arcpy.ExecuteError

    return out_layer


def prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID=ZONE_FIELD_NAME):
    """
    Tworzy bezpieczną, tymczasową kopię siatki w pamięci RAM (memory\\)
    i dodaje w niej pole StatZoneID. Oryginalna siatka użytkownika pozostaje nietknięta!
    Zwraca ścieżkę do roboczej kopii w pamięci.
    """
    temp_grid_memory = "memory\\temp_working_grid"
    if arcpy.Exists(temp_grid_memory):
        arcpy.management.Delete(temp_grid_memory)

    # Nazwa pola może dotrzeć w postaci kwalifikowanej ("grid_1000.OBJECTID").
    grid_id_field = resolve_field_name(
        grid_fl, grid_id_field, "Analytical grid identification field"
    )

    # Siatka musi być 2D: CopyFeatures z outputZFlag = "Disabled" nie potrafi
    # skopiować geometrii Z/M i kończy się błędem 160163.
    check_2d(grid_fl, "Analytical grid")

    # Kopiujemy siatkę do RAM-u (oryginał na dysku nie jest dotykany)
    arcpy.management.CopyFeatures(grid_fl, temp_grid_memory)

    # 1. Walidacja identyfikatora siatki (typ, NULL-e, unikalność, zakres LONG).
    #    Wykonujemy ją na kopii w pamięci, więc skanujemy pełny dataset.
    _validate_grid_id_field(temp_grid_memory, grid_id_field)

    # 2. Pole strefowe musi być LONG i zawierać wartości grid_id_field.
    #    Jeżeli w siatce użytkownika istnieje już pole o tej nazwie, usuwamy je
    #    z kopii roboczej - mogło mieć inny typ lub niepowiązane wartości,
    #    co prowadziłoby do cichych błędów przy dopasowywaniu wyników.
    existing_fields = {f.name.lower(): f for f in arcpy.ListFields(temp_grid_memory)}
    zone_field = existing_fields.get(stat_zone_field_ID.lower())
    same_as_id_field = stat_zone_field_ID.lower() == grid_id_field.lower()

    if zone_field is not None:
        if same_as_id_field:
            # To samo pole jest identyfikatorem i polem strefowym - wartości są
            # już poprawne, wystarczy sprawdzić typ.
            if zone_field.type not in ("SmallInteger", "Integer"):
                arcpy.AddError(
                    f"Error: Field '{stat_zone_field_ID}' is used as the grid "
                    f"identification field, so it must be a Short or Long field "
                    f"(found '{zone_field.type}')."
                )
                raise arcpy.ExecuteError
            return temp_grid_memory

        arcpy.AddWarning(
            f"Field '{stat_zone_field_ID}' already exists in the analytical grid; "
            f"it will be recalculated from '{grid_id_field}' in the in-memory "
            f"working copy."
        )
        arcpy.management.DeleteField(temp_grid_memory, stat_zone_field_ID)

    arcpy.management.AddField(temp_grid_memory, stat_zone_field_ID, "LONG")
    arcpy.management.CalculateField(
        temp_grid_memory, stat_zone_field_ID, f"!{grid_id_field}!", "PYTHON3"
    )

    return temp_grid_memory


def safe_write_to_new_feature_class(
        grid_fl,
        grid_id_field,
        result_table,
        raw_value_field,
        std_value_field,
        output_fc_path,
        output_raw_field,
        output_std_field,
        protected_inputs=None
):
    """
    Tworzy nową, niezależną klasę obiektów wynikowych pod wskazaną pełną ścieżką,
    kopiując geometrię oryginalnej siatki, dodając pola zdefiniowane przez użytkownika
    i zapisując dane kursorowo na podstawie identyfikatora. Oryginalna siatka pozostaje bezpieczna.

    protected_inputs: opcjonalna lista datasetów wejściowych (np. warstwa
    krajobrazu), których nie wolno nadpisać ścieżką wyjściową.
    """
    arcpy.AddMessage(f"Creating output feature class at: {output_fc_path}...")

    # Nazwa pola może dotrzeć w postaci kwalifikowanej ("grid_1000.OBJECTID").
    grid_id_field = resolve_field_name(
        grid_fl, grid_id_field, "Analytical grid identification field"
    )

    # 1. Walidacja nazw pól wyjściowych - przed usunięciem lub utworzeniem
    #    czegokolwiek, aby błąd pojawił się natychmiast.
    output_raw_field = _validate_output_field_name(
        output_raw_field, "Raw output field", grid_fl, grid_id_field,
        other_name=output_std_field
    )
    output_std_field = _validate_output_field_name(
        output_std_field, "Standardized output field", grid_fl, grid_id_field,
        other_name=output_raw_field
    )

    # 2. Zabezpieczenie przed nadpisaniem danych wejściowych. Wcześniej
    #    wskazanie siatki (lub innego wejścia) jako output usuwało oryginał.
    if not output_fc_path or not output_fc_path.strip():
        arcpy.AddError("Error: Output feature class path is empty.")
        raise arcpy.ExecuteError

    _validate_output_workspace(output_fc_path)

    protected = {_normalize_path(_catalog_path(grid_fl))}
    for item in (protected_inputs or ()):
        if item:
            protected.add(_normalize_path(_catalog_path(item)))

    if _normalize_path(_catalog_path(output_fc_path)) in protected:
        arcpy.AddError(
            f"Error: Output path '{output_fc_path}' points to an input dataset. "
            f"Choose a different output location."
        )
        raise arcpy.ExecuteError

    # 3. Usunięcie istniejącej warstwy o tej samej nazwie (jeśli użytkownik nadpisuje)
    if arcpy.Exists(output_fc_path):
        arcpy.management.Delete(output_fc_path)

    # 4. Klonowanie oryginalnej siatki wejściowej bezpośrednio do wskazanej ścieżki docelowej
    arcpy.management.CopyFeatures(grid_fl, output_fc_path)

    # CopyFeatures jest synchroniczne - zamiast pętli oczekującej w
    # nieskończoność sprawdzamy wynik jednorazowo.
    if not arcpy.Exists(output_fc_path):
        arcpy.AddError(f"Error: Output '{output_fc_path}' was not created.")
        raise arcpy.ExecuteError

    # 5. Odczyt wyników z tabeli roboczej do słownika RAM { StatZoneID: (raw_val, std_val) }
    results_dict = {}
    with arcpy.da.SearchCursor(result_table, ["StatZoneID", raw_value_field, std_value_field]) as cursor:
        for zid, raw_val, std_val in cursor:
            if zid is not None:
                results_dict[zid] = (raw_val, std_val)

    # 6. Dodanie zadeklarowanych przez użytkownika pól do nowej klasy obiektów
    arcpy.management.AddField(output_fc_path, output_raw_field, "DOUBLE", field_alias=output_raw_field)
    arcpy.management.AddField(output_fc_path, output_std_field, "DOUBLE", field_alias=output_std_field)

    # 7. Zapis kursorowy w nowej klasie obiektów na podstawie identyfikatora siatki
    update_fields = [grid_id_field, output_raw_field, output_std_field]
    with arcpy.da.UpdateCursor(output_fc_path, update_fields) as cursor:
        for row in cursor:
            g_id = row[0]
            if g_id in results_dict:
                raw_v, std_v = results_dict[g_id]
                row[1] = raw_v if raw_v is not None else 0.0
                row[2] = std_v if std_v is not None else 0.0
            else:
                row[1] = 0.0
                row[2] = 0.0
            cursor.updateRow(row)

    # 8. Automatyczne dodanie nowej warstwy do aktywnej mapy w ArcGIS Pro.
    #    Poza ArcGIS Pro (lub bez aktywnej mapy) nie przerywamy narzędzia -
    #    output jest już zapisany, więc zgłaszamy tylko ostrzeżenie.
    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        map_obj = aprx.activeMap
        if map_obj:
            map_obj.addDataFromPath(output_fc_path)
    except Exception as exc:
        arcpy.AddWarning(
            f"Output was created, but could not be added to the current map: {exc}"
        )

    arcpy.AddMessage("Successfully generated output feature class.")
