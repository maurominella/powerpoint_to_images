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

## Query the ISTAT knowledge base

`query_kb.py` queries `knowledgebase-istat` on
`https://aifoundry-6956-search.search.windows.net` (Italy North), using subscription
`5d476556-6599-4792-a97f-4066de1fa86c`. It requires Azure CLI and no extra Python
packages.

Authenticate with an account that can read the knowledge base and knowledge source
definitions and query the Search service:

```bash
az login
python3 query_kb.py "Quale piattaforma di streaming era la piu usata nel 2023?"
```

The script explicitly passes the subscription when obtaining a Search access token;
it does not change the default Azure CLI subscription or modify Azure resources.
The account needs appropriate Search data-plane roles (for example, Search Service
Contributor to read definitions and Search Index Data Reader to retrieve content).
Additional network and document-level access restrictions still apply.

The script discovers the knowledge sources attached to the KB and their types,
then sets `includeReferences` and `includeReferenceSourceData` to `true` for each.
It prints the response and the complete references, preserving reference IDs,
document keys, and `sourceData`, where the source document URL can be inspected.
It reports missing source data explicitly rather than inventing a file path.
An image URL identifies the indexed image, not automatically its original
PowerPoint presentation and slide number.

To save the complete JSON response, including the activity log:

```bash
python3 query_kb.py "Confronta il 2025 con il 2026" --output /tmp/istat-response.json
```

The output file is overwritten if it exists and can contain private SharePoint
content: keep it out of source control. The default REST API version is
`2026-08-01-preview`; `--api-version` can override it when testing another compatible
version. HTTP errors, partial responses, and authentication failures produce an
error message and exit code 1. With a KB configured for extraction instead of
answer synthesis, the response section contains grounding data rather than a
natural-language answer.
