# Usage Examples  
## Geodiversity Tools for ArcGIS Pro

This document contains examples showing how to run the tools from ArcGIS Pro and from Python.

---

# 1. Running Tools in ArcGIS Pro (GUI)

## Example: Circular Standard Deviation (R_SDc)

1. Open **ArcGIS Pro**.
2. Load:
   - a raster layer representing your terrain variable (e.g., slope, aspect),
   - a polygon grid to aggregate results.
3. Open the toolbox:
GeodiversityTools → R_SDc Calculator

4. Set parameters:
- **Input Raster**
- **Input Polygon Layer**
- **Output Field Name**
- **Ignore NoData** (optional)

5. Click **Run**.

The output field will be added to the polygon attribute table.

---

# 2. Running Tools from Python (ArcPy)

All tools can also be executed programmatically.

## Example: Run R_SDc tool from Python

```python
import arcpy

toolbox_path = r"C:\GeodiversityTools\toolbox\GeodiversityTools.atbx"
arcpy.ImportToolbox(toolbox_path)

arcpy.RSDc_Calculator_GeodiversityTools(
 in_raster=r"C:\data\slope.tif",
 in_polygons=r"C:\data\grid.gdb\cells",
 out_field="RSDC",
 ignore_nodata="true"
)

3. ModelBuilder Usage

Tools are compatible with ModelBuilder.

Example workflow:

Add Terrain Variable Raster

Add Grid Layer

Connect to:

R_SDc Calculator

Slope Statistics Tool

Export model as .atbx if needed.

4. Output Interpretation
R_SDc (Circular Standard Deviation)

Values close to 0 = low directional variability

Values closer to 1 (scaled) or higher = high terrain directional diversity

Useful for morphodiversity classification

Other outputs

Mean slope

StdDev slope

Range

Terrain variability metrics

5. Troubleshooting
Tool fails with: “ERROR 999999”

Check whether raster has NoData values.

Use Copy Raster before processing.

Ensure that the polygon grid has an integer/object ID field.

Tool does not appear in toolbox

Reset toolbox by removing and re-adding it.

Ensure .atbx and .py files are in the correct paths.

Slow performance

Store data in the same GDB.

Avoid network drives.

Enable parallel processing in Environments.