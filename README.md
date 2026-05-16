# Scanner Clipper 📸

A robust Python utility to automatically detect, extract, and clean individual photos from flatbed scanner batch scans. It identifies photo boundaries, handles rounded corners, and aggressively trims whitespace to deliver high-quality, borderless images.

## Features

- **Automatic Detection**: Finds multiple photos in a single high-resolution scan.
- **Whitespace Trimming**: Uses morphological noise reduction to remove scanner bed artifacts and "dust" before cropping.
- **Rounded Corner Support**: Adjustable "shaving" logic to eliminate the white slivers left behind by vintage physical prints.
- **Configurable Thresholding**: Tune the sensitivity of whitespace detection for different scanner beds.
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

You can run the script directly using the installed command:

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

### Visual Troubleshooting:
If photos aren't being detected correctly, use the debug flag to see the masks being generated:
```bash
python scanner_clipper.py -i input/ -o output/ --debug
```

## Requirements

- Python 3.8+
- OpenCV (`opencv-python`)
- NumPy
