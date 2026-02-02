# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),  
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]
- Planned new metrics and diversity indices
- Further improvements to handling of shapefiles
- Updates to documentation and installation instructions

---

## [0.2.0] - 2026-02-02
### Added
- New Index: Introduced the Steinhaus Vertical Relief Index (`R_M`) for measuring landform energy and vertical diversity using a scale-independent, additive approach based on Steinhaus (1947).
- Spatial Overlap Validation: Added a pre-processing check to ensure that the landscape feature layer and the analytical grid have a common spatial extent.
- Data Format Enforcement: Added a restriction to prevent the use of shapefiles, ensuring all operations are performed within Geodatabases (`.gdb`) for data integrity.


### Fixed
- Coordinate System Inheritance: Prevented the automatic inheritance of Z- and M-coordinates in output feature classes, resolving potential geometry compatibility issues.
- Field Name Conflicts: Fixed an issue where the tool would fail if output fields already existed in the attribute table.
- Resource Cleanup: Improved the "intermediate data" removal process to ensure memory is cleared even if the script execution is interrupted.

### Changed
- Performance Overhaul: Re-engineered core logic using In-Memory Dictionary Mapping. Processing time for large datasets (~4,300 zones) was reduced from 40 minutes to under 60 seconds.
- Dynamic Attribute Naming: Improved the prefix generation logic for partial criteria attributes, making them more intuitive and based on source vector layer names.
- Enhanced Spatial Logic: Refined the assignment of extreme points to grid cells using optimized spatial join and axial validation.

---

## [0.1.0] - 2026-01-07
### Added
- Initial official release of Geodiversity Tools
- Tools for polygon, line, point, and raster diversity metrics
- **Included tools:**
  - **Vector:**
    - **polygon:**  
      - `A_Ne` – landscape element diversity (Ne metric)  
      - `A_Nc` – landscape element richness (Nc metric)  
      - `A_SHDI` – Shannon–Weaver diversity index  
    - **line:**  
      - `L_Tl` – line-based diversity / linear feature metrics  
    - **point:**  
      - `P_Ne` – point-based Ne metric  
      - `P_Nc` – point-based Nc metric  
      - `P_Hu` – point-based Shannon entropy metric  
  - **Raster:**  
    - `R_SD` – standard deviation of raster attribute  
    - `R_SDc` – circular standard deviation of raster attribute
- Documentation updated:
  - Installation instructions (including correct folder location outside ArcGIS Pro projects)
  - Input data requirements (`.gdb` recommended, `.shp` not fully supported)
  - Usage examples
- Sample test data (TestData.ppkx and TestData.md)
- Symbology files for five-class bonitation of statistical zones

### Fixed
- Folder naming issue: tools now work properly only if `GeodiversityTools/` folder name is preserved
- Handling of `.shp` vs `.gdb` input datasets clarified
- Script paths configuration documented
- Minor bug fixes in Python scripts for ArcGIS Pro 3.x compatibility

### Changed
- Python scripts adapted to avoid errors with temporary fields and workspace locks
- Documentation now highlights recommended installation outside project directories

---

## [0.0.1] - 2025-12-20
### Added
- Prototype scripts for polygon diversity metrics
- Test data and sample ArcGIS Pro project
- Initial documentation draft
