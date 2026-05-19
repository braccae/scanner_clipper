# Scanner Clipper 📸

A robust Python utility to automatically detect, extract, and clean individual photos from flatbed scanner batch scans. It identifies photo boundaries, handles rounded corners, and aggressively trims whitespace to deliver high-quality, borderless images.

## Features

- **Automatic Detection**: Finds multiple photos in a single high-resolution scan.
- **Whitespace Trimming**: Uses morphological noise reduction to remove scanner bed artifacts and "dust" before cropping.
- **Rounded Corner Support**: Adjustable "shaving" logic to eliminate the white slivers left behind by vintage physical prints.
- **Configurable Thresholding**: Tune the sensitivity of whitespace detection for different scanner beds.
- **WebP by Default**: Optimized for the web with configurable quality (defaults to WebP 90).
- **Debug Mode**: Generates intermediate masks and contour overlays to help optimize parameters.

## Installation

This project uses `uv` for fast dependency management, but standard `pip` works as well.

### 1. Clone and Setup Environment

```bash
# Create a virtual environment and install in editable mode
uv venv
uv pip install -e .
```

## Usage

You can run the script using `uv run` (recommended):

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

### Command Line Arguments

| Argument | Description | Default |
| :--- | :--- | :--- |
| `-i`, `--input` | Path to directory containing raw scans. | `input/` |
| `-o`, `--output` | Path to directory where extracted photos will be saved. | `output/` |
| `-q`, `--quality` | Output quality (0-100). | `90` |
| `-f`, `--format` | Output format (`webp`, `jpg`, `png`). | `webp` |
| `--shave` | Number of pixels to shave from all edges of the final crop (helps with rounded corners). | `10` |
| `--threshold` | Grayscale threshold for whitespace detection (0-255). Lower is more aggressive. | `240` |
| `--debug` | Save diagnostic images to the `debug/` folder. | `False` |

## Optimized Examples

### For standard vintage photos with rounded corners:
```bash
python scanner_clipper.py -i input/ -o output/ --shave 15
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

## Testing

You can run the test suite locally to verify the script is working correctly:

```bash
uv run python3 -m unittest test_scanner_clipper.py
```

The test suite covers:
- Core coordinate ordering and image perspective transformation.
- Standalone image detection and extraction.
- Nested ZIP file scanning and processing.
- End-to-end command line execution and interface arguments.

## Requirements

- Python 3.9+
- OpenCV (`opencv-python`)
- NumPy
