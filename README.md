# powerpoint_to_images

Converts a PowerPoint `.pptx` file into one PNG image per slide,
including hidden slides. Images are saved next to the PowerPoint file,
in a folder with the same name (without the extension):

```text
pptxs/
  Infographs.pptx
  Infographs/
    slide001.png
    slide002.png
    ...
```

## Requirements

- Python 3.9 or later.
- LibreOffice Impress and Poppler (`pdftoppm`) available on PATH.

On Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install libreoffice-impress poppler-utils
```

No additional Python packages are required: the existing `requirements*.txt`
files relate to other exercises and are not needed for this script.
Password-protected PowerPoint files must first be saved without password protection.

## Usage

From the project folder:

```bash
python3 powerpoint_to_images.py
```

The default input file is `pptxs/Infographs.pptx`. To convert a different file,
including one with spaces in its path:

```bash
python3 powerpoint_to_images.py "pptxs/My presentation.pptx"
```

The default resolution is 150 DPI. To increase it and replace any
previously generated images:

```bash
python3 powerpoint_to_images.py pptxs/Infographs.pptx --dpi 200 --overwrite
```

Without `--overwrite`, the script refuses to replace existing slide PNG files.
With `--overwrite`, it removes previous `slideNNN.png` files (including those
no longer needed) only after rendering has completed. Other files
in the folder are preserved. The original PowerPoint file is not modified,
and intermediate PDFs are deleted automatically.

LibreOffice must be able to read the document and have access to the fonts used
in the presentation: missing fonts or PowerPoint-specific features may
cause visual differences. Animations and transitions are not reproduced in PNGs.
If an error occurs, the script prints a message to stderr and exits with code 1.

## Tests

The automated tests do not require LibreOffice or Poppler:

```bash
python3 -m unittest discover -s tests -v
```
