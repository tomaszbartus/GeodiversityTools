# Geodiversity Tools for ArcGIS Pro  
**Author:** Tomasz Bartuś  
**Version:** 1.0 (development)  
**ArcGIS Pro:** 3.x  

## Overview
This repository contains a set of geoprocessing tools designed to calculate key criteria used in the assessment of landscape geodiversity.  
The tools are implemented as:

- a custom ArcGIS Pro Toolbox (`.atbx`)
- a collection of Python scripts (`.py`)
- documentation for installation and usage

The workflows support analyses such as:

- circular standard deviation (SDc, R_SDc)
- local morphodiversity indicators
- terrain variability statistics
- raster-based landscape metrics

These tools are intended for landscape analysis, geodiversity assessment, environmental planning, and scientific research.

---

## Repository Structure

GeodiversityTools/
│
├── Docs/
│ ├── installation.md
│ ├── usage_examples.md
│ └── ...
│
├── Scripts/
│ ├── A_Nc.py
│ ├── A_Ne.py
│ ├── A_SHDI.py
│ └── ...
│
├── Symbology/
│ ├── Colors.md
│ ├── GeodiversityTools.stylex
│
├── TestData/
│
├── Toolbox/
│ └── GeodiversityTools.atbx
│
└── README.md

---

## Features
- Easy-to-use ArcGIS Pro interface (GUI)
- Script tools fully compatible with ModelBuilder
- Clean Python implementation using `arcpy` and Spatial Analyst
- Support for grid-based analysis and raster–polygon overlays
- Designed for reproducible scientific workflows

---

## Requirements
- **ArcGIS Pro 3.x**  
- **Python 3.x (ArcGIS Pro environment)**  
- Spatial Analyst extension (for raster operations)

---

## Installation
See **[docs/installation.md](docs/installation.md)** for full installation instructions.

---

## Usage Examples
Examples of running the tools in ArcGIS Pro and Python can be found in:

👉 **[docs/usage_examples.md](docs/usage_examples.md)**

---

## Citation
If you use these tools in research, please cite appropriately:
Bartuś, T. (2025). Geodiversity Tools for ArcGIS Pro (version 1.0).

---

## License
This project is distributed under the MIT License.  
See `LICENSE` for details.

---

## Contact
For questions or collaboration, please contact:

**Tomasz Bartuś**  
bartus@agh.edu.pl