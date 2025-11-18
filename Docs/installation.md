# Installation Guide  
## Geodiversity Tools for ArcGIS Pro

This document provides step-by-step instructions for installing and using the Geodiversity Tools toolbox in ArcGIS Pro.

---

## 1. Download the Repository
1. Open the project page on GitHub.
2. Click **Code → Download ZIP**.
3. Extract the ZIP file to a location of your choice (e.g., `C:\GeodiversityTools`).

You should now have a directory structure similar to:

GeodiversityTools/
├── Docs/
├── Scripts/
├── Symbology/
├── TestData/
├── Toolbox/
│ └── GeodiversityTools.atbx
└── README.md

---

## 2. Add Toolbox to ArcGIS Pro
1. Open **ArcGIS Pro**.
2. Go to the **Catalog** pane.
3. Right-click **Toolboxes → Add Toolbox**.
4. Browse to:
...\GeodiversityTools\Toolbox\GeodiversityTools.atbx

5. Confirm.

The toolbox will now appear in your Toolboxes list.

---

## 3. Configure Script Paths (if needed)
Tools may reference external Python script files located in:
...\GeodiversityTools\scripts\

If you move the repository, update script paths:

1. Right-click a tool → **Properties**.
2. Go to **Source**.
3. Update the **Script File** location.
4. Save.

---

## 4. Test the Installation
Run any tool (e.g., *R_SDc Calculator*) on a sample raster and polygon grid layer.

If you encounter an error:
- ensure that raster paths contain no special characters,
- check that statistics and temporary folders are writable.

---

## 5. Optional: Install Python Dependencies
All tools use the default ArcGIS Pro Python environment (`arcpy`).  
No additional installation is required.

---

## 6. Updating the Toolbox
To update to a newer version:

1. Download the new version from GitHub.
2. Replace old toolbox + scripts.
3. Restart ArcGIS Pro.

---

For troubleshooting, see the FAQs in `usage_examples.md`.