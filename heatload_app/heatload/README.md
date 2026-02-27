# HeatLoad — Thermal Wattage Calculator

A web app that reads AutoCAD DWG/DXF files, extracts wall and window dimensions per room,
and calculates the heating/cooling wattage using a user-defined formula.

---

## Requirements

- Python 3.8+
- [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter) (free, for DWG → DXF conversion)
- Flask

---

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install ODA File Converter

Download from: https://www.opendesign.com/guestfiles/oda_file_converter

Default install path (Windows):
```
C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe
```

If you installed it elsewhere, open `app.py` and update this line:
```python
ODA_CONVERTER_PATH = r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"
```

### 3. Run the app

```bash
python app.py
```

Then open your browser and go to: http://localhost:5000

---

## Usage

### Step 1 — Upload Drawing
- Upload your DWG or DXF file
- Enter the **layer name(s)** where walls are drawn (e.g. `WALLS`, `A-WALL`, `MIMARI`)
- Enter the **layer name(s)** where windows are drawn (or leave blank if on same layer)
- Optionally upload a screenshot of the drawing to help identify layer names

### Step 2 — Configure
- Enter city, inside temperature, outside temperature
- Set wall height, U-values for walls and windows
- Review parsed rooms (or add rooms manually)

### Step 3 — Formula
Enter your heat load formula using these built-in variables:

| Variable | Description |
|---|---|
| `wall_length` | Net wall length in meters (walls minus windows) |
| `window_length` | Window length in meters |
| `wall_area` | wall_length × wall_height |
| `window_area` | window_length × wall_height |
| `wall_height` | Wall height in meters |
| `U_wall` | U-value of walls (W/m²K) |
| `U_window` | U-value of windows (W/m²K) |
| `delta_T` | T_inside − T_outside |
| `T_inside` | Indoor design temperature |
| `T_outside` | Outdoor design temperature |

**Example formula:**
```
(wall_area * U_wall * delta_T) + (window_area * U_window * delta_T)
```

You can also add custom variables (e.g. safety factors) in JSON format.

### Step 4 — Results
- View wattage per room with visual bar chart
- See total building heat load in W and kW
- Export results to CSV

---

## Notes

- Dimensions in DXF files are in **millimeters** — the app converts to meters automatically
- Rooms are identified by **text labels** in the drawing; each wall/window segment is assigned to the nearest room label
- DXF files can be uploaded directly without ODA Converter

---

## Troubleshooting

**DWG conversion fails:**
- Make sure ODA File Converter is installed and the path in `app.py` is correct
- Try exporting to DXF directly from AutoCAD (File → Save As → AutoCAD 2018 DXF)

**No rooms found:**
- Check that your text labels are on a visible layer in the DXF
- Try adding rooms manually in Step 2

**Wrong dimensions:**
- Verify the layer name matches exactly (case-insensitive) what is in your DWG/DXF
- Open the DXF in a text editor and search for your layer name to confirm
