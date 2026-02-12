# Geodiversity Tools for ArcGIS Pro

**Author:** Tomasz Bartuś  
**Version:** 0.2.0  
**ArcGIS Pro:** 3.x

## Overview

This repository contains a set of geoprocessing tools designed to calculate partial criteria used in the assessment of landscape geodiversity.  
The tools are implemented as:

- a custom ArcGIS Pro Toolbox (`.atbx`)
- a collection of Python scripts (`.py`)
- documentation for installation and usage

The workflows support analyses such as:

- vector-based landscape metrics:
  - diversity of polygonal (A) features based on the number of elements (A_Ne) and number of categories (A_Nc)
  - diversity of polygonal (A) features based on Shannon-Weaver diversity index (A_SHDI)
  - diversity of linear (L) features based on the total length of features (L_Tl)
  - diversity of point (P) features based on the number of elements (P_Ne), number of categories (P_Nc) and unit entrophy (P_Hu)
- raster-based (R) landscape metrics:
  - diversity of continuous regionalized variables based on: standard deviation (R_SD), circular standard deviation (R_SDc) and Steinhaus vertical relief index (R_M)

These tools are intended for landscape analysis, geodiversity assessment, environmental planning, and scientific research.

```

## Repository Structure

GeodiversityTools/
│
├── Docs/
│ ├── GeodiversityTool.pdf
│ ├── installation.md
│ ├── licence.md
│ └── ...
│
├── Symbology/
│ ├── Colors.md
│ ├── GeodiversityTools.stylex
│
├── TestData/
│ ├── TestData.md
│ ├── TestData.ppkx
│
├── Toolbox/
│ ├── Images/
│ │ ├── A_Nc.png
│ │ ├── A_Ne.png
│ │ ├── A_SHDI.png
│ │ └── ...
│ │
│ ├── Scripts/
│ │ ├── A_Nc.py
│ │ ├── A_Ne.py
│ │ ├── A_SHDI.py
│ │ └── ...
│ └── GeodiversityTools.atbx
│
├── CHANGELOG.md
└── README.md

```

## Features

- Easy-to-use ArcGIS Pro interface (GUI)
- Script tools fully compatible with ModelBuilder
- Clean Python implementation using `arcpy` and Spatial Analyst
- Support for analyses of regionalized discrete and continuous variables
- Support for grid-based analysis and raster–polygon overlays
- Support for file geodatabase (`.gdb`) feature classes; shapefiles (`.shp`) are not supported.
- Integrated output standardization of geodiversity metrics, ensuring their comparability for cross-grid and cross-region analyses
- Designed for reproducible scientific workflows

---

## Requirements

- **ArcGIS Pro 3.x**
- **Python 3.x (ArcGIS Pro environment)**

---

## Installation

👉 See **[Docs/installation.md](Docs/installation.md)** for full installation instructions.

---

## Manual

👉 See **[Docs/GeodiversityTools.pdf](Docs/GeodiversityTools.pdf)** for method and indexes documentation.

---

## Test Data

Test data have been prepared for testing diversity indices. For more information, see:

👉 **[TestData/TestData.md](TestData/TestData.md)**

---

## Citation

If you use these tools in research, please cite appropriately:
Bartuś, T. (2026). Geodiversity Tools for ArcGIS Pro (version 0.2.0). https://github.com/tomaszbartus/GeodiversityTools.

---

## Bibliography

The following bibliographic items describe the scientific foundations of geodiversity assessment and apply the indicators discussed:

- Bartuś, T., & Mastej, W. (2023). Morphodiversity as a Tool in Geoconservation: A Case Study in a Mountain Area (Pieniny Mts, Poland). Sustainability, 15(14), 11357. https://doi.org/10.3390/SU151411357
- Mastej, W., & Bartuś, T. (2024). Supervised classification of morphodiversity using artificial neural networks on the example of the Pieniny Mts (Poland). CATENA, 242, 108086. https://doi.org/10.1016/j.catena.2024.108086
- Bartuś, T., & Mastej, W. (2025). HOW to use continuous variables in geodiversity assessments – RASTER Continuous Morphodiversity Model. Environmental Modelling and Software, 193, 106597. https://doi.org/10.1016/j.envsoft.2025.106597.

---

## License

This project is distributed under the MIT License.  
See **[Docs/licence.md](Docs/licence.md)** for details.

---

## Contact

For questions or collaboration, please contact:

**Tomasz Bartuś**  
bartus[at]agh.edu.pl
