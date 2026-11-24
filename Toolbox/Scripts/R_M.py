# coding=utf-8
"""
Toolbox: GeodiversityTools (for ArcGIS Pro)
Tool: R_M (Steinhaus Vertical Relief Index for Raster)
Version: v.1.0.0.
Short description: Calculates the Steinhaus Vertical Relief Index (R_M) (Steinhaus, 1947) for a selected landscape feature (raster) within each polygon of an analytical grid and performs Min-Max standardization.
Exports profile lines (RM_Lines) and extreme points (RM_Points) to the target GDB.
Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
2026-11-11
"""

import arcpy
import numpy as np
from arcpy.sa import ExtractValuesToPoints
import math
import geodiversity_core as core

# Allow overwriting outputs
arcpy.env.overwriteOutput = True
# Prevent Z-coordinate and M-coordinate inheritance in feature classes
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"


# Helper class definition: ProfileLine
class ProfileLine:
    def __init__(self, start_point, end_point, direction, stat_zone_id=None):
        self.start = start_point
        self.end = end_point
        self.direction = direction
        self.stat_zone_id = stat_zone_id


try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS FROM TOOL
    # ----------------------------------------------------------------------
    landscape_ras = arcpy.GetParameterAsText(0)  # Wejściowy raster
    grid_fl = arcpy.GetParameterAsText(1)  # Siatka analityczna (Feature Class)
    grid_id_field = arcpy.GetParameterAsText(2)  # Pole identyfikatora strefy w siatce

    # --- USER-DEFINED OUTPUT PARAMETERS ---
    output_fc_path = arcpy.GetParameterAsText(3)  # Ścieżka wyjściowej klasy obiektów
    output_raw_field = arcpy.GetParameterAsText(4)  # Nazwa pola surowego wskaźnika R_M
    output_std_field = arcpy.GetParameterAsText(5)  # Nazwa pola zestandaryzowanego (Min-Max)

    # ----------------------------------------------------------------------
    # WORKSPACE AND METADATA
    # ----------------------------------------------------------------------
    workspace_gdb = arcpy.Describe(grid_fl).path
    desc_land = arcpy.Describe(landscape_ras)
    base_name = desc_land.name
    prefix = arcpy.ValidateTableName(base_name[:3].upper(), workspace_gdb)
    stat_zone_field_ID = "StatZoneID"
    grid_sr = arcpy.Describe(grid_fl).spatialReference
    rast = arcpy.Raster(landscape_ras)

    # 1. Walidacja przez moduł core
    core.check_gdb_feature(grid_fl)

    arcpy.AddMessage("Recalculating feature class extent for the grid...")
    arcpy.management.RecalculateFeatureClassExtent(grid_fl)

    ext_ras = arcpy.Describe(landscape_ras).extent
    ext_grid = arcpy.Describe(grid_fl).extent
    if ext_ras.disjoint(ext_grid):
        arcpy.AddError("Raster layer does not overlap with grid.")
        raise arcpy.ExecuteError
    arcpy.AddMessage("Input validation passed.")

    # ----------------------------------------------------------------------
    # REMOVE LOCKS
    # ----------------------------------------------------------------------
    try:
        arcpy.AddMessage("Removing existing locks...")
        arcpy.management.RemoveLocks(landscape_ras)
        arcpy.management.RemoveLocks(grid_fl)
    except:
        pass

    # Przygotowanie bezpiecznej kopii roboczej siatki w pamięci RAM z polem StatZoneID
    temp_grid_memory = core.prepare_grid_zone_copy(grid_fl, grid_id_field, stat_zone_field_ID)

    # ----------------------------------------------------------------------
    # 2. CREATE CENTROID TABLE
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Creating in-memory table of centroids...")
    centroid_table = r"memory\centroids_table"
    if arcpy.Exists(centroid_table):
        arcpy.management.Delete(centroid_table)
    arcpy.management.CreateTable("memory", "centroids_table")
    arcpy.management.AddField(centroid_table, stat_zone_field_ID, "LONG")
    arcpy.management.AddField(centroid_table, "CENTROID_X", "DOUBLE")
    arcpy.management.AddField(centroid_table, "CENTROID_Y", "DOUBLE")

    with arcpy.da.SearchCursor(temp_grid_memory, ["SHAPE@", stat_zone_field_ID]) as s_cursor, \
            arcpy.da.InsertCursor(centroid_table, [stat_zone_field_ID, "CENTROID_X", "CENTROID_Y"]) as i_cursor:
        for row in s_cursor:
            centroid = row[0].centroid
            i_cursor.insertRow([row[1], centroid.X, centroid.Y])
    arcpy.AddMessage("Centroids stored successfully.")

    # ----------------------------------------------------------------------
    # 3. GENERATE GLOBAL PROFILES
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Generating global profiles...")
    profiles = []

    xmin, ymin, xmax, ymax = ext_ras.XMin, ext_ras.YMin, ext_ras.XMax, ext_ras.YMax
    x_tol, y_tol = rast.meanCellWidth / 2.0, rast.meanCellHeight / 2.0

    ys_sorted = sorted([row[0] for row in arcpy.da.SearchCursor(centroid_table, ["CENTROID_Y"])])
    ys_unique = []
    for y in ys_sorted:
        if not any(abs(y - yu) <= y_tol for yu in ys_unique):
            ys_unique.append(y)
    for y in ys_unique:
        profiles.append(ProfileLine(start_point=(xmin, y), end_point=(xmax, y), direction="W-E"))

    xs_sorted = sorted([row[0] for row in arcpy.da.SearchCursor(centroid_table, ["CENTROID_X"])])
    xs_unique = []
    for x in xs_sorted:
        if not any(abs(x - xu) <= x_tol for xu in xs_unique):
            xs_unique.append(x)
    for x in xs_unique:
        profiles.append(ProfileLine(start_point=(x, ymin), end_point=(x, ymax), direction="N-S"))

    profile_fc = r"memory\profile_lines"
    if arcpy.Exists(profile_fc):
        arcpy.management.Delete(profile_fc)
    arcpy.management.CreateFeatureclass("memory", "profile_lines", "POLYLINE", spatial_reference=grid_sr)
    arcpy.management.AddField(profile_fc, "Direction", "TEXT")
    arcpy.management.AddField(profile_fc, "StatZoneID", "LONG")

    profile_oid_map = {}
    with arcpy.da.InsertCursor(profile_fc, ["SHAPE@", "Direction", "StatZoneID"]) as icursor:
        for pl in profiles:
            line_geom = arcpy.Polyline(arcpy.Array([arcpy.Point(*pl.start), arcpy.Point(*pl.end)]), grid_sr)
            oid = icursor.insertRow([line_geom, pl.direction, pl.stat_zone_id])
            profile_oid_map[pl] = oid

    # ----------------------------------------------------------------------
    # 4. DETECT EXTREMA ALONG PROFILES
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Detecting extrema along profiles...")

    temp_points_fc = r"memory\profile_points"
    if arcpy.Exists(temp_points_fc):
        arcpy.management.Delete(temp_points_fc)
    arcpy.management.CreateFeatureclass("memory", "profile_points", "POINT", spatial_reference=grid_sr)
    arcpy.management.AddField(temp_points_fc, "ProfileID", "LONG")
    arcpy.management.AddField(temp_points_fc, "Direction", "TEXT")
    arcpy.management.AddField(temp_points_fc, "StatZoneID", "LONG")

    for pl in profiles:
        profile_id = profile_oid_map[pl]
        n_points = max(int(max(abs(pl.end[0] - pl.start[0]), abs(pl.end[1] - pl.start[1])) / rast.meanCellWidth), 1)
        x_coords = np.linspace(pl.start[0], pl.end[0], n_points)
        y_coords = np.linspace(pl.start[1], pl.end[1], n_points)
        with arcpy.da.InsertCursor(temp_points_fc, ["SHAPE@", "ProfileID", "Direction", "StatZoneID"]) as icursor:
            for x, y in zip(x_coords, y_coords):
                icursor.insertRow([arcpy.Point(x, y), profile_id, pl.direction, pl.stat_zone_id])

    points_with_values = r"memory\profile_points_values"
    ExtractValuesToPoints(temp_points_fc, rast, points_with_values, interpolate_values="INTERPOLATE",
                          add_attributes="VALUE_ONLY")
    values_field = "RASTERVALU"


    def detect_extrema(values, points):
        extrema = []
        valid_indices = [i for i, v in enumerate(values) if v is not None]
        if len(valid_indices) < 3:
            return extrema
        for i in range(1, len(values) - 1):
            if values[i] is None or values[i - 1] is None or values[i + 1] is None:
                continue
            if (values[i] > values[i - 1] and values[i] > values[i + 1]) or (
                    values[i] < values[i - 1] and values[i] < values[i + 1]):
                extrema.append((points[i], values[i]))
        if values[0] is not None:
            extrema.insert(0, (points[0], values[0]))
        if values[-1] is not None:
            extrema.append((points[-1], values[-1]))
        return extrema


    extreme_points = []
    profile_dict = {}
    with arcpy.da.SearchCursor(points_with_values,
                               ["Shape@", "ProfileID", "Direction", "StatZoneID", values_field]) as cursor:
        for shp, pid, direction, zid, val in cursor:
            if pid not in profile_dict:
                profile_dict[pid] = {"points": [], "values": [], "direction": direction, "zid": zid}
            profile_dict[pid]["points"].append(shp)
            profile_dict[pid]["values"].append(val)

    for pid, data in profile_dict.items():
        extrema_pts = detect_extrema(data["values"], data["points"])
        for ep, z_val in extrema_pts:
            extreme_points.append({"POINT": ep, "PROFILE_ID": pid, "DIRECTION": data["direction"], "Z": z_val})

    extreme_fc = r"memory\extreme_points"
    if arcpy.Exists(extreme_fc):
        arcpy.management.Delete(extreme_fc)
    arcpy.management.CreateFeatureclass("memory", "extreme_points", "POINT", spatial_reference=grid_sr)
    arcpy.management.AddField(extreme_fc, "ProfileID", "LONG")
    arcpy.management.AddField(extreme_fc, "Direction", "TEXT")
    arcpy.management.AddField(extreme_fc, "Z", "DOUBLE")

    with arcpy.da.InsertCursor(extreme_fc, ["SHAPE@", "ProfileID", "Direction", "Z"]) as icursor:
        for ep in extreme_points:
            icursor.insertRow([ep["POINT"], ep["PROFILE_ID"], ep["DIRECTION"], ep["Z"]])

    # ----------------------------------------------------------------------
    # 5. ASSIGN StatZoneID TO EXTREME POINTS
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Assigning StatZoneID to extreme points...")
    if stat_zone_field_ID not in [f.name for f in arcpy.ListFields(extreme_fc)]:
        arcpy.management.AddField(extreme_fc, stat_zone_field_ID, "LONG")

    poly_geom_dict = {row[0]: row[1] for row in arcpy.da.SearchCursor(temp_grid_memory, [stat_zone_field_ID, "SHAPE@"])}
    centroid_dict = {row[0]: (row[1], row[2]) for row in
                     arcpy.da.SearchCursor(centroid_table, [stat_zone_field_ID, "CENTROID_X", "CENTROID_Y"])}

    eps_x = rast.meanCellWidth / 2.0
    eps_y = rast.meanCellHeight / 2.0

    with arcpy.da.UpdateCursor(extreme_fc, ["SHAPE@", "Direction", stat_zone_field_ID]) as u_cur:
        for geom, direction, current_zid in u_cur:
            if geom is None:
                continue
            px = geom.firstPoint.X
            py = geom.firstPoint.Y
            assigned_zid = None

            for zid_c, (xc, yc) in centroid_dict.items():
                on_correct_line = False
                if direction == "W-E":
                    if abs(py - yc) <= eps_y:
                        on_correct_line = True
                elif direction == "N-S":
                    if abs(px - xc) <= eps_x:
                        on_correct_line = True

                if on_correct_line:
                    poly = poly_geom_dict[zid_c]
                    if poly.contains(geom):
                        assigned_zid = zid_c
                        break
            u_cur.updateRow([geom, direction, assigned_zid])

    # ----------------------------------------------------------------------
    # 6. CREATE BORDER POINTS
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Creating border points per polygon...")
    border_points_assigned_fc = r"memory\border_points_assigned"
    if arcpy.Exists(border_points_assigned_fc):
        arcpy.management.Delete(border_points_assigned_fc)
    arcpy.management.CreateFeatureclass("memory", "border_points_assigned", "POINT", spatial_reference=grid_sr)
    arcpy.management.AddField(border_points_assigned_fc, "ProfileID", "LONG")
    arcpy.management.AddField(border_points_assigned_fc, "Direction", "TEXT")
    arcpy.management.AddField(border_points_assigned_fc, "Z", "DOUBLE")
    arcpy.management.AddField(border_points_assigned_fc, stat_zone_field_ID, "LONG")

    with arcpy.da.InsertCursor(border_points_assigned_fc,
                               ["SHAPE@", "ProfileID", "Direction", "Z", stat_zone_field_ID]) as icursor, \
            arcpy.da.SearchCursor(temp_grid_memory, ["SHAPE@", stat_zone_field_ID]) as s_cursor:
        for poly_geom, zid in s_cursor:
            centroid = poly_geom.centroid
            xmin, xmax, ymin, ymax = poly_geom.extent.XMin, poly_geom.extent.XMax, poly_geom.extent.YMin, poly_geom.extent.YMax

            lines = {
                "N-S": arcpy.Polyline(arcpy.Array([arcpy.Point(centroid.X, ymin), arcpy.Point(centroid.X, ymax)]),
                                      grid_sr),
                "W-E": arcpy.Polyline(arcpy.Array([arcpy.Point(xmin, centroid.Y), arcpy.Point(xmax, centroid.Y)]),
                                      grid_sr)
            }
            for direction, line in lines.items():
                intersect = line.intersect(poly_geom, 1)
                if intersect is None:
                    continue
                if isinstance(intersect, arcpy.PointGeometry):
                    icursor.insertRow([intersect, -1, direction, None, zid])
                elif isinstance(intersect, arcpy.Multipoint):
                    for pt in intersect:
                        icursor.insertRow([arcpy.PointGeometry(pt, grid_sr), -1, direction, None, zid])
                elif isinstance(intersect, arcpy.Array):
                    for pt in intersect:
                        icursor.insertRow([arcpy.PointGeometry(pt, grid_sr), -1, direction, None, zid])

    # ----------------------------------------------------------------------
    # 7. CALCULATE Z FOR BORDER POINTS
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Extracting Z values for assigned border points...")
    border_points_assigned_z_fc = r"memory\border_points_assigned_z"
    ExtractValuesToPoints(border_points_assigned_fc, rast, border_points_assigned_z_fc,
                          interpolate_values="INTERPOLATE", add_attributes="VALUE_ONLY")

    z_field = "RASTERVALU"
    if "Z" not in [f.name for f in arcpy.ListFields(border_points_assigned_z_fc)]:
        arcpy.management.AddField(border_points_assigned_z_fc, "Z", "DOUBLE")

    with arcpy.da.UpdateCursor(border_points_assigned_z_fc, ["Z", z_field]) as cursor:
        for row in cursor:
            row[0] = row[1]
            cursor.updateRow(row)

    arcpy.management.MakeFeatureLayer(border_points_assigned_z_fc, "assigned_points_lyr", "Z IS NOT NULL")
    non_null_assigned_fc = r"memory\border_points_assigned_z_nonnull"
    if arcpy.Exists(non_null_assigned_fc):
        arcpy.management.Delete(non_null_assigned_fc)
    arcpy.management.CopyFeatures("assigned_points_lyr", non_null_assigned_fc)
    border_points_assigned_z_fc = non_null_assigned_fc

    # ----------------------------------------------------------------------
    # 8. MERGE EXTREME POINTS AND BORDER POINTS
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Merging extreme points and border points...")
    all_points_fc = r"memory\all_profile_points"
    if arcpy.Exists(all_points_fc):
        arcpy.management.Delete(all_points_fc)

    arcpy.management.CreateFeatureclass(out_path="memory", out_name="all_profile_points", geometry_type="POINT",
                                        spatial_reference=grid_sr)
    arcpy.management.AddField(all_points_fc, "Direction", "TEXT", field_length=10)
    arcpy.management.AddField(all_points_fc, "Z", "DOUBLE")
    arcpy.management.AddField(all_points_fc, stat_zone_field_ID, "LONG")

    fields = ["SHAPE@", "Direction", "Z", stat_zone_field_ID]
    with arcpy.da.SearchCursor(extreme_fc, fields) as s_cur, arcpy.da.InsertCursor(all_points_fc, fields) as i_cur:
        for row in s_cur:
            i_cur.insertRow(row)
    with arcpy.da.SearchCursor(border_points_assigned_z_fc, fields) as s_cur, arcpy.da.InsertCursor(all_points_fc,
                                                                                                    fields) as i_cur:
        for row in s_cur:
            i_cur.insertRow(row)

    # ----------------------------------------------------------------------
    # 9. CREATE TABLE FOR VERTICAL RELIEF CALCULATION
    # ----------------------------------------------------------------------
    vr_table = r"memory\vertical_relief"
    if arcpy.Exists(vr_table):
        arcpy.management.Delete(vr_table)
    arcpy.management.CreateTable("memory", "vertical_relief")
    arcpy.management.AddField(vr_table, "StatZoneID", "LONG")
    arcpy.management.AddField(vr_table, "MU_NS", "DOUBLE")
    arcpy.management.AddField(vr_table, "MU_WE", "DOUBLE")
    arcpy.management.AddField(vr_table, "MU", "DOUBLE")
    arcpy.management.AddField(vr_table, "A", "DOUBLE")
    arcpy.management.AddField(vr_table, "A_sqrt", "DOUBLE")
    arcpy.management.AddField(vr_table, "RM", "DOUBLE")
    arcpy.management.AddField(vr_table, "RM_MM", "DOUBLE")

    # ----------------------------------------------------------------------
    # 10. CALCULATE MU_NS, MU_WE, MU
    # ----------------------------------------------------------------------
    stat_zone_ids = [row[0] for row in arcpy.da.SearchCursor(temp_grid_memory, [stat_zone_field_ID])]
    points_map = {}
    p_fields = ["Z", "Direction", "SHAPE@X", "SHAPE@Y", stat_zone_field_ID]

    with arcpy.da.SearchCursor(all_points_fc, p_fields) as s_cursor:
        for z, direct, px, py, zid in s_cursor:
            if zid not in points_map:
                points_map[zid] = []
            points_map[zid].append((z, direct, px, py))

    with arcpy.da.InsertCursor(vr_table, ["StatZoneID", "MU_NS", "MU_WE", "MU"]) as i_cursor:
        for zid in stat_zone_ids:
            zone_data = points_map.get(zid, [])
            if not zone_data:
                # Pole bez pikseli z danymi (poza obszarem rastra). Wartości
                # pozostają NULL, aby nie wchodziły do zakresu Min–Max; w klasie
                # wynikowej i tak trafią jako 0.
                i_cursor.insertRow([zid, None, None, None])
                continue

            ns_points = sorted([p for p in zone_data if p[1] == "N-S"], key=lambda x: x[3])
            z_ns = [p[0] for p in ns_points]
            mu_ns = sum([abs(z_ns[i] - z_ns[i - 1]) ** 0.5 for i in range(1, len(z_ns))]) if len(z_ns) > 1 else 0

            we_points = sorted([p for p in zone_data if p[1] == "W-E"], key=lambda x: x[2])
            z_we = [p[0] for p in we_points]
            mu_we = sum([abs(z_we[i] - z_we[i - 1]) ** 0.5 for i in range(1, len(z_we))]) if len(z_we) > 1 else 0

            mu = (mu_ns + mu_we) / 2.0
            i_cursor.insertRow([zid, mu_ns, mu_we, mu])

    # ----------------------------------------------------------------------
    # 11. CALCULATE M & STANDARDIZATION
    # ----------------------------------------------------------------------
    area_dict = {row[0]: row[1] for row in arcpy.da.SearchCursor(temp_grid_memory, [stat_zone_field_ID, "SHAPE@AREA"])}

    # Komórki bez pikseli rastra (poza obszarem opracowania) nie mają danych,
    # więc nie mogą wchodzić do zakresu Min–Max. Sprawdzamy to zonalnie, bo
    # punkty profilu potrafią trafić na granicę rastra i dać wtedy RM = 0.
    arcpy.AddMessage("Checking which grid cells contain raster pixels...")
    zone_stats_table = r"memory\rm_zone_counts"
    if arcpy.Exists(zone_stats_table):
        arcpy.management.Delete(zone_stats_table)
    arcpy.sa.ZonalStatisticsAsTable(
        temp_grid_memory, stat_zone_field_ID, rast, zone_stats_table, "DATA", "MEAN"
    )
    zones_with_data = {
        row[0] for row in arcpy.da.SearchCursor(zone_stats_table, [stat_zone_field_ID, "MEAN"])
        if row[0] is not None and row[1] is not None
    }

    with arcpy.da.UpdateCursor(vr_table, ["StatZoneID", "A", "A_sqrt", "MU", "RM"]) as cursor:
        for row in cursor:
            zid = row[0]
            if zid in area_dict:
                area = area_dict[zid]
                row[1] = area
                row[2] = math.sqrt(area) if area > 0 else None
                mu = row[3]
                a_sqrt = row[2]
                if mu is not None and a_sqrt not in (None, 0) and zid in zones_with_data:
                    row[4] = mu / a_sqrt
                else:
                    row[4] = None
                cursor.updateRow(row)

    rm_values = [row[0] for row in arcpy.da.SearchCursor(vr_table, ["RM"]) if row[0] is not None]
    if rm_values:
        rm_min = min(rm_values)
        rm_max = max(rm_values)
        with arcpy.da.UpdateCursor(vr_table, ["RM", "RM_MM"]) as cursor:
            for rm, rm_mm in cursor:
                if rm is not None:
                    if rm_max > rm_min:
                        cursor.updateRow([rm, (rm - rm_min) / (rm_max - rm_min)])
                    else:
                        cursor.updateRow([rm, 0])
                else:
                    cursor.updateRow([rm, None])

    # ----------------------------------------------------------------------
    # 12. BEZPIECZNY ZAPIS DO NOWEJ KLASY OBIEKTÓW (Non-destructive)
    # ----------------------------------------------------------------------
    core.safe_write_to_new_feature_class(
        grid_fl=grid_fl,
        grid_id_field=grid_id_field,
        result_table=vr_table,
        raw_value_field="RM",
        std_value_field="RM_MM",
        output_fc_path=output_fc_path,
        output_raw_field=output_raw_field,
        output_std_field=output_std_field
    )

    # ----------------------------------------------------------------------
    # 13. ZAPIS WARSTW POMOCNICZYCH (RM_Lines & RM_Points)
    # ----------------------------------------------------------------------
    target_gdb = arcpy.Describe(output_fc_path).path

    out_lines_path = fr"{target_gdb}\RM_Lines"
    out_points_path = fr"{target_gdb}\RM_Points"

    arcpy.AddMessage(f"Exporting profile lines to: {out_lines_path}...")
    if arcpy.Exists(out_lines_path):
        arcpy.management.Delete(out_lines_path)
    arcpy.management.CopyFeatures(profile_fc, out_lines_path)

    arcpy.AddMessage(f"Exporting extreme points to: {out_points_path}...")
    if arcpy.Exists(out_points_path):
        arcpy.management.Delete(out_points_path)
    arcpy.management.CopyFeatures(all_points_fc, out_points_path)

    # Dodanie pomocniczych warstw do aktywnej mapy
    aprx = arcpy.mp.ArcGISProject("CURRENT")
    map_obj = aprx.activeMap
    if map_obj:
        map_obj.addDataFromPath(out_lines_path)
        map_obj.addDataFromPath(out_points_path)

    arcpy.AddMessage("Steinhaus Vertical Relief Index calculated successfully.")

    # ----------------------------------------------------------------------
    # 14. CLEANUP
    # ----------------------------------------------------------------------
    for t in [centroid_table, profile_fc, temp_points_fc, points_with_values, extreme_fc, border_points_assigned_fc,
              border_points_assigned_z_fc, non_null_assigned_fc, all_points_fc, vr_table, temp_grid_memory,
              r"memory\rm_zone_counts"]:
        if arcpy.Exists(t):
            try:
                arcpy.management.Delete(t)
            except:
                pass

    arcpy.ClearWorkspaceCache_management()
    if workspace_gdb.endswith(".gdb"):
        arcpy.management.Compact(workspace_gdb)

    arcpy.AddMessage("R_M calculation completed successfully.")

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError("Python error occurred:")
    arcpy.AddError(str(e))

finally:
    arcpy.ClearWorkspaceCache_management()