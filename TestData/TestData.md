# TestData.ppkx – Test Dataset for Geodiversity Toolbox

## Overview

**TestData.ppkx** is a test project prepared for validating and demonstrating the functionality of the **Geodiversity Toolbox** in the **ArcGIS Pro 3.x** environment.  
The project contains a single map (**TestData**) with a set of vector and raster layers representing different types of landscape features commonly used in geodiversity analyses.

All layers include predefined symbology to facilitate visual inspection and interpretation of results.

---

## Project Structure

The project contains one map named **TestData** with the following layers:

### Vector layers

- **Grid**  
  Analytical grid composed of **3 × 3 statistical zones**.

  - Size of one statistical zone: **250 m × 250 m**
  - Used as the reference spatial unit for geodiversity calculations.

- **Points**  
  Point feature class containing **54 point features** (e.g. geosites).

  - Attribute: `categories` (Short Integer)
  - Categories: **1–5**
  - Intended for testing point-based diversity metrics.

- **Lines**  
  Line feature class containing **8 linear features**.

  - Intended for testing linear landscape feature metrics.

- **Polygons**  
  Polygon feature class containing **7 polygon features**.
  - Attribute: `category`
  - Number of categories: **4**
  - Intended for testing area-based and categorical diversity metrics.

### Raster layers

- **DEM**  
  Digital Elevation Model raster layer used for terrain-based analyses.

- **Aspect**  
  Aspect raster derived from the DEM, representing slope aspect directions.

---

## Symbology

All layers are provided with predefined symbology:

- Categorical color schemes for vector layers
- Continuous color ramps for raster layers

This allows immediate visualization of the data and facilitates verification of analysis outputs.

---

## How to Use the Data

1. Open **ArcGIS Pro 3.x**.
2. Load the project by opening the file:
3. Once the project is opened, the **TestData** map will be available with all layers loaded and symbolized.
4. Add the **Geodiversity Toolbox** to your project:

- Open the **Catalog** pane
- Right-click **Toolboxes** → **Add Toolbox**
- Select the toolbox file: `GeodiversityTools.tbx` (or the corresponding `.atbx` file)

5. Run the tools from **Geodiversity Toolbox**, using:

- **Grid** as the analytical unit
- Point, line, polygon, or raster layers as input landscape features, depending on the tool

---

## Intended Purpose

This dataset is intended **exclusively for testing, demonstration, and validation** of:

- Script-based tools in the **Geodiversity Toolbox**
- Geodiversity indices and metrics applied in spatial landscape analyses
- Tool behavior with different geometry types (points, lines, polygons, rasters)

The data are not intended for real-world analyses.

---

## Software Requirements

- **ArcGIS Pro 3.x**
- **Geodiversity Toolbox** (added manually to the project)

---

## Notes

- All spatial data are provided in a consistent coordinate system.
- The dataset size is intentionally small to ensure fast tool execution and easy debugging.
- Users are encouraged to inspect attribute tables and layer symbology before running analyses.

---
