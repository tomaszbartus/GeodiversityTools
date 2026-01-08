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
