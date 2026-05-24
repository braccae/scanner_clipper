# Scanner Clipper 📸

A robust Python utility to automatically detect, extract, and clean individual photos from flatbed scanner batch scans. It identifies photo boundaries, handles rounded corners, and aggressively trims whitespace to deliver high-quality, borderless images.

## Features

- **Automatic Detection**: Finds multiple photos in a single high-resolution scan.
- **Whitespace Trimming**: Uses morphological noise reduction to remove scanner bed artifacts and "dust" before cropping.
- **Rounded Corner Support**: Adjustable "shaving" logic to eliminate the white slivers left behind by vintage physical prints.
- **Configurable Thresholding**: Tune the sensitivity of whitespace detection for different scanner beds.
- **WebP by Default**: Optimized for the web with configurable quality (defaults to WebP 90).
- **Debug Mode**: Generates intermediate masks and contour overlays to help optimize parameters.
- **EXIF Date Editing**: Bulk update 'Date Taken' tags in JPEGs, WebPs, and PNGs either in-place or copied to an output folder. Supports sequential increments and interactive folder walkthroughs.
- **Interactive Web Dashboard**: A zero-dependency visual interface to run all tools, explore local directories, stream active logs in real-time, and walk through photo albums with visual image previews.
- **Native Desktop App Wrapper**: Wrap the dashboard instantly into a native desktop window frame via a lightweight webview utility.




## Installation

This project uses `uv` for fast dependency management, but standard `pip` works as well.

### 1. Clone and Setup Environment

```bash
# Create a virtual environment and install in editable mode
uv venv
uv pip install -e .
```

## Usage

You can run the scripts using `uv run` (recommended):

### 1. Extract Photos from Scans
```bash
uv run scanner-clipper -i input/ -o output/
```

Or using the installed command directly (if your environment is activated):
```bash
scanner-clipper -i input/ -o output/
```

Or run the python file:
```bash
python scanner_clipper.py -i input/ -o output/
```

### 2. Downsize and Convert for Digital Frame
To downsize the extracted images and convert them to JPEG (ideal for digital picture frames):
```bash
uv run image-resizer -i output/ -o downsized/
```

Or run the python file:
```bash
python image_resizer.py -i output/ -o downsized/
```

### 3. Bulk Edit and Date EXIF Metadata
To update the EXIF 'date taken' tags across scanned albums:
```bash
uv run exif-date-editor -i output/
```

Or run in-place on a specific folder with a specified date:
```bash
uv run exif-date-editor -i output/summer_1995/ -d "August 1995"
```

### 4. Interactive Web Dashboard
To start the dark-mode graphical user interface in your browser:
```bash
uv run photo-dashboard
```

Or run the python file directly:
```bash
python gui.py
```
This launches a local web server at `http://localhost:8081` and opens it in your default browser automatically. It features a complete UI for the scanner clipper, resizer, bulk EXIF editor, and the visual interactive walkthrough.

### 5. Native Desktop Application
You can also run this application in a dedicated standalone native desktop window using `pywebview` (which uses your OS's native rendering engine instead of bundling a heavy browser instance):

1. Install `pywebview`:
```bash
pip install pywebview
```

2. Start the native application wrapper:
```bash
uv run photo-desktop
```

Or run the python file directly:
```bash
python desktop_app.py
```
This spawns a standalone window wrapping your dark-mode utilities dashboard.

### 6. Compiling into Standalone Native Binaries
To compile this entire project (Python code, static frontend templates, and dependency modules) into a **single, fully self-contained native executable** that can run on other machines without needing Python or libraries pre-installed:

1. Install `pyinstaller` and GUI bindings:
```bash
pip install pyinstaller pywebview PyQt6
```

2. Run the compiler command:
On Linux/macOS:
```bash
pyinstaller --onefile --windowed --add-data "index.html:." --name "PhotoUtils" desktop_app.py
```

On Windows:
```bash
pyinstaller --onefile --windowed --add-data "index.html;." --name "PhotoUtils" desktop_app.py
```

This generates a standalone native executable inside the `dist/` folder:
- **Linux**: `dist/PhotoUtils` (ELF binary)
- **Windows**: `dist/PhotoUtils.exe` (PE binary)
- **macOS**: `dist/PhotoUtils` (Mach-O binary) or `dist/PhotoUtils.app` (App bundle)

### 7. Automated Releases via GitHub Actions
A production-ready continuous integration (CI) workflow is configured at `.github/workflows/release.yml` to compile and distribute these native binaries automatically across multiple platforms.

#### To Trigger an Automated Cross-Platform Release:
1. Commit your changes and push a version tag (e.g. `v1.0.0`) to your repository:
```bash
git tag v1.0.0
git push origin v1.0.0
```

2. **GitHub Actions** will automatically spawn:
   - A **Linux** runner to build `PhotoUtils-Linux` (Otsu/OpenCV headless dependencies pre-installed).
   - A **Windows** runner to build `PhotoUtils-Windows.exe` (packages standalone assemblies).
   - A **macOS** runner to build and zip your native `PhotoUtils-macOS.app` bundle.

3. Once built successfully, it automatically creates a new **GitHub Release** and uploads all three native binaries as downloadable assets.

*(Note: You can also manually trigger builds at any time without creating a tag by clicking the **"Run workflow"** button in the Actions tab of your GitHub repository).*






### Command Line Arguments (scanner-clipper)

| Argument | Description | Default |
| :--- | :--- | :--- |
| `-i`, `--input` | Path to directory containing raw scans. | `input/` |
| `-o`, `--output` | Path to directory where extracted photos will be saved. | `output/` |
| `-q`, `--quality` | Output quality (0-100). | `90` |
| `-f`, `--format` | Output format (`webp`, `jpg`, `png`). | `webp` |
| `--shave` | Number of pixels to shave from all edges of the final crop (helps with rounded corners). | `10` |
| `--threshold` | Grayscale threshold for whitespace detection (0-255). Lower is more aggressive. | `240` |
| `--debug` | Save diagnostic images to the `debug/` folder. | `False` |

### Command Line Arguments (image-resizer)

| Argument | Description | Default |
| :--- | :--- | :--- |
| `-i`, `--input` | Path to directory containing images to downsize. | `output/` |
| `-o`, `--output` | Path to directory where downsized images will be saved. | `downsized/` |
| `-s`, `--scale` | Scaling factor (e.g. `0.5` for half size, `0.33` for one-third size). Mutually exclusive with `--max-dim`. | `0.5` |
| `--max-dim` | Scale down so the larger side is at most this many pixels. Mutually exclusive with `--scale`. | *None* |
| `-q`, `--quality` | Output JPEG quality (0-100). | `90` |
| `-f`, `--format` | Output format (`jpg`, `jpeg`, `webp`, `png`). | `jpg` |
| `--no-recursive` | Skip recursive traversal of the input directory. | *False (runs recursively)* |

### Command Line Arguments (exif-date-editor)

| Argument | Description | Default |
| :--- | :--- | :--- |
| `-i`, `--input` | Path to directory containing images, or path to a single image. | *Required* |
| `-o`, `--output` | Path to directory where modified images will be saved. | *Same as input (updates in-place)* |
| `-d`, `--date` | Date to apply (e.g. `1995-08-15`, `1995-08`, `1995`, `August 1995`). | *None (triggers interactive walk)* |
| `--interactive` | Force Interactive Walkthrough mode even if a date is specified. | `False` |
| `--no-recursive` | Do not traverse directories recursively. | `False` |
| `--increment` | Time increment in seconds between sequential photos. | `60` |
| `--random-time` | Randomize the starting time of day (between 9:00 AM and 5:00 PM). | `False` |
| `-q`, `--quality` | Saving quality (0-100) for JPEGs/WebPs. | `95` |
| `--dry-run` | Simulate operations without writing to disk. | `False` |
| `--verbose` | Print detailed logs for every updated file. | `False` |

## Optimized Examples

### For standard vintage photos with rounded corners:
```bash
python scanner_clipper.py -i input/ -o output/ --shave 15
```

### For downsizing images by 2/3 (making them 1/3 scale, i.e., 33%):
```bash
python image_resizer.py -i output/ -o downsized/ -s 0.33
```

### For downsizing images by a half (making them 50% scale):
```bash
python image_resizer.py -i output/ -o downsized/ -s 0.5
```

### For resizing images to fit a 1080p digital photo frame (max 1920px width/height):
```bash
python image_resizer.py -i output/ -o downsized/ --max-dim 1920
```

### For "messy" scans with dust or dark scanner beds:
```bash
python scanner_clipper.py -i input/ -o output/ --threshold 220
```

### To output high-quality JPEGs instead of WebP:
```bash
python scanner_clipper.py -f jpg -q 95
```

### Visual Troubleshooting:
If photos aren't being detected correctly, use the debug flag to see the masks being generated:
```bash
python scanner_clipper.py -i input/ -o output/ --debug
```

### For batch dating vintage scanned photos interactively:
```bash
python exif_date_editor.py -i output/ --random-time --increment 60
```

### For non-interactive dating of a single folder to a year/month:
```bash
python exif_date_editor.py -i output/album_1993/ -d "1993-06" --increment 30
```

## Testing

You can run the test suite locally to verify the script is working correctly:

```bash
uv run python3 -m unittest test_scanner_clipper.py
uv run python3 -m unittest test_image_resizer.py
uv run python3 -m unittest test_exif_date_editor.py
```

The test suite covers:
- Core coordinate ordering and image perspective transformation.
- Standalone image detection and extraction.
- Nested ZIP file scanning and processing.
- Image downscaling and file type conversion.
- EXIF metadata date manipulation, folder sequence increments, and robust date string parsing.
- End-to-end command line execution and interface arguments.

## Requirements

- Python 3.9+
- OpenCV (`opencv-python`)
- NumPy
- Pillow

