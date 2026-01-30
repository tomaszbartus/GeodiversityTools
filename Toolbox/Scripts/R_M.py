# Geodiversity Tool R_M (memory)
# Calculates the vertical relief index (R_M) (Steinhaus, 1947) for a selected landscape feature (raster)
# within each polygon of an analytical grid
# Author: Tomasz Bartuś (bartus[at]agh.edu.pl)
# Date: 2026-01-28

import arcpy
import numpy as np
from arcpy.sa import ExtractValuesToPoints
import math

# Allow overwriting outputs
arcpy.env.overwriteOutput = True
# Prevent Z-coordinate and M-coordinate inheritance in feature classes
arcpy.env.outputZFlag = "Disabled"
arcpy.env.outputMFlag = "Disabled"

# ----------------------------------------------------------------------
# Helper class definition: ProfileLine
# ----------------------------------------------------------------------
# Represents a single transect line (WE or NS) used for relief analysis.
# Encapsulates geometry (start/end points) and metadata (direction,
# optional Zone ID) to ensure logical consistency during
# extrema detection and spatial assignment.
class ProfileLine:
    def __init__(self, start_point, end_point, direction, stat_zone_id=None):
        self.start = start_point
        self.end = end_point
        self.direction = direction
        self.stat_zone_id = stat_zone_id

try:
    # ----------------------------------------------------------------------
    # INPUT PARAMETERS
    # ----------------------------------------------------------------------
    landscape_ras = arcpy.GetParameterAsText(0)  # Input raster
    grid_fl = arcpy.GetParameterAsText(1)       # Analytical grid (polygon)
    grid_id_field = arcpy.GetParameterAsText(2) # Field ID in grid

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

    aprx = arcpy.mp.ArcGISProject("CURRENT")
    map_obj = aprx.activeMap

    # ----------------------------------------------------------------------
    # VALIDATE DATA FORMATS (BLOCK SHAPEFILES)
    # ----------------------------------------------------------------------
    def check_gdb_feature(fc):
        desc = arcpy.Describe(fc)
        if desc.dataType == "ShapeFile" or desc.catalogPath.lower().endswith(".shp"):
            arcpy.AddError(f"Error: Layer '{desc.name}' is a Shapefile.")
            arcpy.AddError("Geodiversity Tools require GDB feature classes.")
            raise arcpy.ExecuteError

    check_gdb_feature(grid_fl)

    # ----------------------------------------------------------------------
    # CHECK EXTENTS
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Recalculating feature class extent for the grid...")
    arcpy.management.RecalculateFeatureClassExtent(grid_fl)

    ext_ras = arcpy.Describe(landscape_ras).extent
    ext_grid = arcpy.Describe(grid_fl).extent
    if ext_ras.disjoint(ext_grid):
        arcpy.AddError("Raster layer does not overlap with grid.")
        raise arcpy.ExecuteError
    arcpy.AddMessage("Input validation passed.")

    # ----------------------------------------------------------------------
    # OUTPUT FIELD NAMES
    # ----------------------------------------------------------------------
    output_index_name = f"{prefix}_R_M"
    output_index_alias = f"{prefix}_R_M"
    std_output_index_name = f"{prefix}_RM_MM"
    std_output_index_alias = f"Std_{prefix}_R_M"
    existing_fields = [f.name.upper() for f in arcpy.ListFields(grid_fl)]
    if output_index_name.upper() in existing_fields or std_output_index_name.upper() in existing_fields:
        arcpy.AddError(f"Fields '{output_index_name}' and/or '{std_output_index_name}' already exist. Remove them first.")
        raise Exception("Field name conflict")

    # ----------------------------------------------------------------------
    # REMOVE LOCKS
    # ----------------------------------------------------------------------
    try:
        arcpy.AddMessage("Removing existing locks...")
        arcpy.management.RemoveLocks(landscape_ras)
        arcpy.management.RemoveLocks(grid_fl)
    except:
        pass

    # ----------------------------------------------------------------------
    # 1. CREATE in grid_fl TEMPORARY STATISTICAL ZONE FIELD
    # ----------------------------------------------------------------------
    arcpy.AddMessage(f"Creating temporary zone field: {stat_zone_field_ID}...")
    if stat_zone_field_ID in [f.name for f in arcpy.ListFields(grid_fl)]:
        arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)
    arcpy.management.AddField(grid_fl, stat_zone_field_ID, "LONG")
    arcpy.management.CalculateField(grid_fl, stat_zone_field_ID, f"!{grid_id_field}!", "PYTHON3")

    # ----------------------------------------------------------------------
    # 2. CREATE grid_fl FEATURES CENTROID TABLE
    # ----------------------------------------------------------------------
    # Generates a reference table containing the geometric center (centroid)
    # of each grid cell. These coordinates are crucial for aligning
    # the global profile lines (Step 3) with the center of each analysis zone.
    arcpy.AddMessage("Creating in-memory table of centroids...")
    centroid_table = r"memory\centroids_table"
    arcpy.management.CreateTable("memory", "centroids_table")
    arcpy.management.AddField(centroid_table, stat_zone_field_ID, "LONG")
    arcpy.management.AddField(centroid_table, "CENTROID_X", "DOUBLE")
    arcpy.management.AddField(centroid_table, "CENTROID_Y", "DOUBLE")

    with arcpy.da.SearchCursor(grid_fl, ["SHAPE@", stat_zone_field_ID]) as s_cursor, \
         arcpy.da.InsertCursor(centroid_table, [stat_zone_field_ID, "CENTROID_X", "CENTROID_Y"]) as i_cursor:
        for row in s_cursor:
            centroid = row[0].centroid
            i_cursor.insertRow([row[1], centroid.X, centroid.Y])
    arcpy.AddMessage("Centroids stored successfully.")

    # ----------------------------------------------------------------------
    # 3. GENERATE GLOBAL PROFILES
    # ----------------------------------------------------------------------
    # Calculates and defines a set of horizontal (W-E) and vertical (N-S)
    # transects that span the entire extent of the study area. Each profile
    # is strictly aligned with the X or Y coordinate of at least one
    # polygon centroid, ensuring that every analysis zone is intersected
    # through its geometric center.
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

    arcpy.AddMessage(f"Generated {len(ys_unique)} W–E and {len(xs_unique)} N–S profiles ({len(profiles)} total).")

    profile_fc = r"memory\profile_lines"
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
    # Visualization of the GLOBAL PROFILES (can be commented)
    # ----------------------------------------------------------------------
    # Adds the calculated global transects to the current map as a polyline
    # layer. This is a Quality Control (QC) step to verify that profiles
    # correctly intersect the center of each grid cell before point detection.
    profile_fc_view = fr"{workspace_gdb}\profile_lines_view"
    arcpy.management.CopyFeatures(profile_fc, profile_fc_view)
    map_obj.addDataFromPath(profile_fc_view)
    arcpy.AddMessage("Profile lines added to map.")

    # ----------------------------------------------------------------------
    # 4. DETECT EXTREMA ALONG PROFILES
    # ----------------------------------------------------------------------
    # Extracts elevation values from the raster at each profile point and
    # identifies local terrain minima and maxima. This step simplifies the
    # continuous surface into a discrete set of significant topographic
    # points, which are the basis for calculating the Steinhaus vertical relief index.
    arcpy.AddMessage("Detecting extrema along profiles...")

    # Wygenerowanie punktów profilów dla ekstrakcji wartości
    temp_points_fc = r"memory\profile_points"
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


    # Definition of the local extrema detection algorithm (minima and maxima)
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

    # Create the extreme_points feature class (in memory)
    extreme_fc = r"memory\extreme_points"
    arcpy.management.CreateFeatureclass("memory", "extreme_points", "POINT", spatial_reference=grid_sr)
    arcpy.management.AddField(extreme_fc, "ProfileID", "LONG")
    arcpy.management.AddField(extreme_fc, "Direction", "TEXT")
    arcpy.management.AddField(extreme_fc, "Z", "DOUBLE")

    with arcpy.da.InsertCursor(extreme_fc, ["SHAPE@", "ProfileID", "Direction", "Z"]) as icursor:
        for ep in extreme_points:
            icursor.insertRow([ep["POINT"], ep["PROFILE_ID"], ep["DIRECTION"], ep["Z"]])

    # ----------------------------------------------------------------------
    # 4a. Visualization of the DETECTED EXTREMA (can be commented)
    # ----------------------------------------------------------------------
    # Adds the local minima and maxima points to the current map. This
    # Quality Control (QC) step allows the user to visually confirm that
    # the elevation trend analysis is working correctly along the profiles.
    # extreme_fc_view = fr"{workspace_gdb}\extreme_points_view"
    # if arcpy.Exists(extreme_fc_view):
    #     arcpy.management.Delete(extreme_fc_view)
    # arcpy.management.CopyFeatures(extreme_fc, extreme_fc_view)
    # map_obj.addDataFromPath(extreme_fc_view)
    # arcpy.AddMessage("Extrema points added to map for visualization.")

    # ----------------------------------------------------------------------
    # 5. ASSIGN StatZoneID TO EXTREME POINTS (CENTROID + SPATIAL CHECK)
    # ----------------------------------------------------------------------
    # Filters and assigns detected extrema to specific analysis zones.
    # A point is assigned only if it aligns with the polygon's centroid axis
    # and is physically located within its boundaries. This dual verification
    # prevents "point-stealing" by adjacent polygons sharing the same
    # global profile.
    arcpy.AddMessage("Assigning StatZoneID to extreme points (Direction + Spatial Check)...")

    if stat_zone_field_ID not in [f.name for f in arcpy.ListFields(extreme_fc)]:
        arcpy.management.AddField(extreme_fc, stat_zone_field_ID, "LONG")

    # Prepare dictionaries for rapid spatial lookup (ZIDs and geometries)
    poly_geom_dict = {row[0]: row[1] for row in arcpy.da.SearchCursor(grid_fl, [stat_zone_field_ID, "SHAPE@"])}
    centroid_dict = {row[0]: (row[1], row[2]) for row in
                     arcpy.da.SearchCursor(centroid_table, [stat_zone_field_ID, "CENTROID_X", "CENTROID_Y"])}

    eps_x = rast.meanCellWidth / 2.0
    eps_y = rast.meanCellHeight / 2.0

    # Update StatZoneID using spatial join logic (Axis + Containment)
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

    arcpy.AddMessage("Assignment completed.")

    # ----------------------------------------------------------------------
    # 5a. Visualization of the DETECTED EXTREMA (can be commented)
    # ----------------------------------------------------------------------
    # Adds the local minima and maxima points to the current map. This
    # Quality Control (QC) step allows the user to visually confirm that
    # the elevation trend analysis is working correctly along the profiles.
    # arcpy.AddMessage("Exporting extreme points to workspace for visualization...")
    # extreme_points_view = fr"{workspace_gdb}\extreme_points_view"
    # if arcpy.Exists(extreme_points_view):
    #     arcpy.management.Delete(extreme_points_view)
    # arcpy.management.CopyFeatures(extreme_fc, extreme_points_view)
    # map_obj.addDataFromPath(extreme_points_view)
    # arcpy.AddMessage("Extreme points layer added to map.")

    # ----------------------------------------------------------------------
    # 6. CREATE BORDER POINTS (PROFILE INTERSECTIONS WITH POLYGONS)
    # ----------------------------------------------------------------------
    # Identifies the intersection points between global profile lines and
    # polygon boundaries. These points act as the "start" and "end" markers
    # for each local transect, ensuring that the vertical relief calculation
    # accounts for the elevation change from the polygon's edge to the
    # first/last internal extremum.
    arcpy.AddMessage("Creating border points per polygon...")

    border_points_assigned_fc = r"memory\border_points_assigned"
    arcpy.management.CreateFeatureclass("memory", "border_points_assigned", "POINT", spatial_reference=grid_sr)
    arcpy.management.AddField(border_points_assigned_fc, "ProfileID", "LONG")
    arcpy.management.AddField(border_points_assigned_fc, "Direction", "TEXT")
    arcpy.management.AddField(border_points_assigned_fc, "Z", "DOUBLE")
    arcpy.management.AddField(border_points_assigned_fc, stat_zone_field_ID, "LONG")

    with arcpy.da.InsertCursor(border_points_assigned_fc,
                               ["SHAPE@", "ProfileID", "Direction", "Z", stat_zone_field_ID]) as icursor, \
            arcpy.da.SearchCursor(grid_fl, ["SHAPE@", stat_zone_field_ID]) as s_cursor:

        for poly_geom, zid in s_cursor:
            centroid = poly_geom.centroid
            xmin, xmax, ymin, ymax = poly_geom.extent.XMin, poly_geom.extent.XMax, poly_geom.extent.YMin, poly_geom.extent.YMax

            lines = {
                "N-S": arcpy.Polyline(arcpy.Array([arcpy.Point(centroid.X, ymin), arcpy.Point(centroid.X, ymax)]), grid_sr),
                "W-E": arcpy.Polyline(arcpy.Array([arcpy.Point(xmin, centroid.Y), arcpy.Point(xmax, centroid.Y)]), grid_sr)
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
    # 6a. Visualization of the ASSIGNED BORDER POINTS (can be commented)
    # ----------------------------------------------------------------------
    # Adds the intersection points between profiles and polygon boundaries
    # to the map. This Quality Control (QC) step ensures that each analysis
    # zone has correctly identified entry and exit elevation markers.
    # border_points_assigned_view = fr"{workspace_gdb}\border_points_assigned_view"
    # if arcpy.Exists(border_points_assigned_view):
    #     arcpy.management.Delete(border_points_assigned_view)
    # arcpy.management.CopyFeatures(border_points_assigned_fc, border_points_assigned_view)
    # map_obj.addDataFromPath(border_points_assigned_view)
    # arcpy.AddMessage("Border points layer added to map.")

    # ----------------------------------------------------------------------
    # 7. CALCULATE Z FOR BORDER POINTS
    # ----------------------------------------------------------------------
    # Performs a spatial sampling of the input raster to assign elevation
    # values to the newly created border intersection points. This ensures
    # that the start and end of each local transect are vertically anchored
    # to the terrain surface for accurate relief summation.
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

    # Remove NULL Z
    arcpy.management.MakeFeatureLayer(border_points_assigned_z_fc, "assigned_points_lyr", "Z IS NOT NULL")
    non_null_assigned_fc = r"memory\border_points_assigned_z_nonnull"
    arcpy.management.CopyFeatures("assigned_points_lyr", non_null_assigned_fc)
    border_points_assigned_z_fc = non_null_assigned_fc

    # ----------------------------------------------------------------------
    # 7a. Visualization of the BORDER POINTS WITH Z VALUES (can be commented)
    # ----------------------------------------------------------------------
    # Adds the border intersection points to the map after successful
    # elevation extraction. This Quality Control (QC) step allows for
    # verification that each point has been correctly "draped" over the
    # raster surface and contains valid Z data for final calculations.
    # assigned_z_view = fr"{workspace_gdb}\border_points_assigned_z_view"
    # if arcpy.Exists(assigned_z_view):
    #     arcpy.management.Delete(assigned_z_view)
    # arcpy.management.CopyFeatures(border_points_assigned_z_fc, assigned_z_view)
    # map_obj.addDataFromPath(assigned_z_view)
    # arcpy.AddMessage("Border points with Z values added to map.")

    # ----------------------------------------------------------------------
    # 8. MERGE EXTREME POINTS AND BORDER POINTS INTO ONE FEATURE CLASS
    # ----------------------------------------------------------------------
    # Consolidation of all detected topographic markers into a single dataset.
    # This unified collection of extrema and boundary points forms the
    # complete "elevation chain" required to compute the total vertical
    # displacement (μ) for each analytical zone.
    arcpy.AddMessage("Merging extreme points and border points into one feature class...")

    all_points_fc = fr"{workspace_gdb}\all_profile_points"

    if arcpy.Exists(all_points_fc):
        arcpy.management.Delete(all_points_fc)

    arcpy.management.CreateFeatureclass(
        out_path=workspace_gdb,
        out_name="all_profile_points",
        geometry_type="POINT",
        spatial_reference=grid_sr
    )

    # Add fields
    arcpy.management.AddField(all_points_fc, "Direction", "TEXT", field_length=10)
    arcpy.management.AddField(all_points_fc, "Z", "DOUBLE")
    arcpy.management.AddField(all_points_fc, stat_zone_field_ID, "LONG")

    fields = ["SHAPE@", "Direction", "Z", stat_zone_field_ID]

    # EXTREME POINTS
    with arcpy.da.SearchCursor(extreme_fc, fields) as s_cur, \
            arcpy.da.InsertCursor(all_points_fc, fields) as i_cur:
        for row in s_cur:
            i_cur.insertRow(row)

    # BORDER POINTS
    with arcpy.da.SearchCursor(border_points_assigned_z_fc, fields) as s_cur, \
            arcpy.da.InsertCursor(all_points_fc, fields) as i_cur:
        for row in s_cur:
            i_cur.insertRow(row)

    arcpy.AddMessage("All profile-related points successfully merged.")

    # ----------------------------------------------------------------------
    # 8a. Visualization of the MERGED PROFILE POINTS (can be commented)
    # ----------------------------------------------------------------------
    # Adds the final consolidated dataset of extrema and border points to
    # the map. This Quality Control (QC) step allows for a comprehensive
    # review of the entire "elevation chain" before the statistical
    # calculation of the vertical relief index.
    arcpy.AddMessage("Adding merged profile points to map...")
    for lyr in map_obj.listLayers():
        if lyr.name == "all_profile_points":
            map_obj.removeLayer(lyr)
            break
    map_obj.addDataFromPath(all_points_fc)
    arcpy.AddMessage("All profile points layer added to map.")

    # ----------------------------------------------------------------------
    # 9. CREATE MEMORY TABLE FOR VERTICAL RELIEF CALCULATION
    # ----------------------------------------------------------------------
    # Initializes a temporary relational structure to store the computed
    # relief values. This table serves as an intermediate workspace where
    # total elevation changes (μ) are aggregated for each analysis zone
    # before being joined back to the primary grid.
    arcpy.AddMessage("Creating in-memory table for vertical relief calculations...")
    vr_table = r"memory\vertical_relief"
    if arcpy.Exists(vr_table):
        arcpy.management.Delete(vr_table)

    # Create table in memory
    arcpy.management.CreateTable("memory", "vertical_relief")

    # Add fields
    arcpy.management.AddField(vr_table, "StatZoneID", "LONG")
    arcpy.management.AddField(vr_table, "MU_NS", "DOUBLE")
    arcpy.management.AddField(vr_table, "MU_WE", "DOUBLE")
    arcpy.management.AddField(vr_table, "MU", "DOUBLE")
    arcpy.management.AddField(vr_table, "A", "DOUBLE")
    arcpy.management.AddField(vr_table, "A_sqrt", "DOUBLE")
    arcpy.management.AddField(vr_table, "RM", "DOUBLE")
    arcpy.management.AddField(vr_table, "RM_MM", "DOUBLE")

    arcpy.AddMessage("Memory table 'vertical_relief' created successfully.")

    # ----------------------------------------------------------------------
    # 10. CALCULATE MU_NS, MU_WE, MU FOR EACH GRID CELL (OPTIMIZED)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Optimizing calculations: loading points to memory...")

    # Zapewnienie listy unikalnych ID stref
    stat_zone_ids = [row[0] for row in arcpy.da.SearchCursor(grid_fl, [stat_zone_field_ID])]

    # Group points by StatZoneID in a dictionary
    points_map = {}
    fields = ["Z", "Direction", "SHAPE@X", "SHAPE@Y", stat_zone_field_ID]

    with arcpy.da.SearchCursor(all_points_fc, fields) as s_cursor:
        for z, direct, px, py, zid in s_cursor:
            if zid not in points_map:
                points_map[zid] = []
            points_map[zid].append((z, direct, px, py))

    arcpy.AddMessage(f"Processing {len(stat_zone_ids)} zones using RAM-based dictionary...")

    with arcpy.da.InsertCursor(vr_table, ["StatZoneID", "MU_NS", "MU_WE", "MU"]) as i_cursor:
        for zid in stat_zone_ids:
            zone_data = points_map.get(zid, [])

            if not zone_data:
                i_cursor.insertRow([zid, 0, 0, 0])
                continue

            # --- μ_NS --- (Sort by Y)
            ns_points = sorted([p for p in zone_data if p[1] == "N-S"], key=lambda x: x[3])
            z_ns = [p[0] for p in ns_points]
            mu_ns = sum([abs(z_ns[i] - z_ns[i - 1]) ** 0.5 for i in range(1, len(z_ns))]) if len(z_ns) > 1 else 0

            # --- μ_WE --- (Sort by X)
            we_points = sorted([p for p in zone_data if p[1] == "W-E"], key=lambda x: x[2])
            z_we = [p[0] for p in we_points]
            mu_we = sum([abs(z_we[i] - z_we[i - 1]) ** 0.5 for i in range(1, len(z_we))]) if len(z_we) > 1 else 0

            mu = (mu_ns + mu_we) / 2.0
            i_cursor.insertRow([zid, mu_ns, mu_we, mu])


    arcpy.AddMessage("Calculations completed.")

    # ----------------------------------------------------------------------
    # 11. CALCULATION M attributes (Steinhaus, 1947)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating area-based attributes A, A_sqrt and vertical relief index M...")

    # ----------------------------------------------------------------------
    # 11a. READ GRID CELL AREAS
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Reading grid cell areas from analytical grid...")

    area_dict = {}
    with arcpy.da.SearchCursor(grid_fl, [stat_zone_field_ID, "SHAPE@AREA"]) as cursor:
        for zid, area in cursor:
            area_dict[zid] = area

    arcpy.AddMessage(f"Read area values for {len(area_dict)} grid cells.")

    # ----------------------------------------------------------------------
    # 11b. UPDATE A AND A_sQRT IN vertical_relief TABLE
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Populating A and A_sqrt fields...")

    with arcpy.da.UpdateCursor(vr_table, ["StatZoneID", "A", "A_sqrt"]) as cursor:
        for row in cursor:
            zid = row[0]
            if zid in area_dict:
                area = area_dict[zid]
                row[1] = area
                row[2] = math.sqrt(area) if area > 0 else None
                cursor.updateRow(row)

    arcpy.AddMessage("Fields A and A_sqrt calculated successfully.")

    # ----------------------------------------------------------------------
    # 11c. CALCULATE M (R_M)
    # M = μ / sqrt(A)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating vertical relief index M (RM)...")

    with arcpy.da.UpdateCursor(vr_table, ["MU", "A_sqrt", "RM"]) as cursor:
        for mu, a_sqrt, rm in cursor:
            if mu is not None and a_sqrt not in (None, 0):
                cursor.updateRow([mu, a_sqrt, mu / a_sqrt])
            else:
                cursor.updateRow([mu, a_sqrt, None])

    arcpy.AddMessage("RM values calculated.")

    # ----------------------------------------------------------------------
    # 12. MIN–MAX STANDARDIZATION (RM_MM)
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Calculating min–max standardized RM (RM_MM)...")

    rm_values = [
        row[0] for row in arcpy.da.SearchCursor(vr_table, ["RM"])
        if row[0] is not None
    ]

    if rm_values:
        rm_min = min(rm_values)
        rm_max = max(rm_values)

        if rm_max > rm_min:
            with arcpy.da.UpdateCursor(vr_table, ["RM", "RM_MM"]) as cursor:
                for rm, rm_mm in cursor:
                    if rm is not None:
                        cursor.updateRow([rm, (rm - rm_min) / (rm_max - rm_min)])
                    else:
                        cursor.updateRow([rm, None])
            arcpy.AddMessage("RM_MM standardization completed.")
        else:
            arcpy.AddWarning("RM values are constant. RM_MM set to 0.")
            with arcpy.da.UpdateCursor(vr_table, ["RM_MM"]) as cursor:
                for row in cursor:
                    row[0] = 0
                    cursor.updateRow(row)
    else:
        arcpy.AddWarning("No valid RM values found. RM_MM not calculated.")

    # ----------------------------------------------------------------------
    # 13. PERSIST FINAL RESULTS TO GEODATABASE
    # ----------------------------------------------------------------------
    # Exports the calculated Vertical Relief (Steinhaus Index) from temporary
    # memory to the permanent workspace. This final feature class integrates
    # the source geometry with the computed μ values, ready for thematic
    # mapping and further spatial analysis.
    verification_table = fr"{workspace_gdb}\vertical_relief_copy"
    if arcpy.Exists(verification_table):
        arcpy.management.Delete(verification_table)
    arcpy.management.CopyRows(vr_table, verification_table)
    arcpy.AddMessage(f"Verification table created in GDB: {verification_table}")

    # ----------------------------------------------------------------------
    # 14. JOIN RESULTS BACK TO THE GRID LAYER
    # ----------------------------------------------------------------------
    arcpy.AddMessage("Joining results back to the analytical grid...")
    arcpy.management.JoinField(grid_fl, stat_zone_field_ID, verification_table, stat_zone_field_ID, ["RM", "RM_MM"])

    # ----------------------------------------------------------------------
    # 15. RENAME JOINED FIELDS
    # ----------------------------------------------------------------------
    # AlterField requires a Geodatabase source, which aligns with the current workspace requirements
    arcpy.management.AlterField(grid_fl, "RM", output_index_name, output_index_alias)
    arcpy.management.AlterField(grid_fl, "RM_MM", std_output_index_name, std_output_index_alias)

except arcpy.ExecuteError:
    arcpy.AddError("Geoprocessing error occurred:")
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as e:
    arcpy.AddError(f"Python error occurred: {str(e)}")

finally:
    # ----------------------------------------------------------------------
    # 16. CLEANUP & FINALIZATION
    # ----------------------------------------------------------------------
    try:
        # 16a. Remove temporary StatZoneID field to finalize schema
        if arcpy.Exists(grid_fl) and stat_zone_field_ID in [f.name for f in arcpy.ListFields(grid_fl)]:
            arcpy.AddMessage("Removing temporary zone field from analytical grid...")
            arcpy.management.DeleteField(grid_fl, stat_zone_field_ID)

        # 16b. Cleanup of temporary datasets from system memory (RAM) only
        intermediate_memory_data = [
            r"memory\centroids_table",
            r"memory\profile_lines",
            r"memory\profile_points",
            r"memory\profile_points_values",
            r"memory\extreme_points",
            r"memory\border_points_assigned",
            r"memory\border_points_assigned_z",
            r"memory\border_points_assigned_z_nonnull",
            r"memory\vertical_relief",
            r"memory\vertical_relief_copy"  # na wypadek gdybyś testował w pamięci
        ]

        for item in intermediate_memory_data:
            if arcpy.Exists(item):
                arcpy.management.Delete(item)

        arcpy.AddMessage("Intermediate memory cleaned.")

    except:
        arcpy.AddWarning("Cleanup could not remove all temporary elements.")

    arcpy.ClearWorkspaceCache_management()
    arcpy.AddMessage("Workspace cache cleared. Script finished.")