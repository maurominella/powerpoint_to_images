"""Convert a PowerPoint presentation into one PNG per slide."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def run_command(command: list[str]) -> None:
    try:
        subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=180
        )
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() or exc.stdout.strip()
        raise RuntimeError(
            f"Conversion failed ({Path(command[0]).name}): {details}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Timeout of 180 seconds exceeded: {Path(command[0]).name}"
        ) from exc


def convert_powerpoint(
    source: Path, dpi: int = 150, overwrite: bool = False
) -> list[Path]:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"File not found: {source}")
    if source.suffix.lower() != ".pptx":
        raise ValueError("The file must have a .pptx extension.")
    if dpi <= 0:
        raise ValueError("The DPI resolution must be greater than zero.")

    output_dir = source.with_suffix("")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"The destination path is not a directory: {output_dir}")
    existing = [
        path
        for path in output_dir.glob("slide*.png")
        if re.fullmatch(r"slide[0-9]{3,}\.png", path.name)
    ]
    if existing and not overwrite:
        raise ValueError(
            f"Images already exist in {output_dir}. "
            "Use --overwrite to replace them."
        )
    if any(not path.is_file() for path in existing):
        raise ValueError("A slide path in the destination is not a file.")

    office = shutil.which("libreoffice") or shutil.which("soffice")
    renderer = shutil.which("pdftoppm")
    if office is None or renderer is None:
        raise RuntimeError(
            "LibreOffice Impress and Poppler (pdftoppm) are required. On Ubuntu/Debian: "
            "sudo apt-get install libreoffice-impress poppler-utils"
        )

    with tempfile.TemporaryDirectory(prefix="powerpoint-to-images-") as temporary:
        work_dir = Path(temporary)
        # A separate profile avoids interfering with an open LibreOffice session.
        profile = (work_dir / "profile").as_uri()
        run_command(
            [
                office,
                f"-env:UserInstallation={profile}",
                "--headless",
                "--convert-to",
                'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}',
                "--outdir",
                str(work_dir),
                str(source),
            ]
        )
        pdf = work_dir / f"{source.stem}.pdf"
        if not pdf.is_file():
            raise RuntimeError(
                "LibreOffice did not produce the PDF. Check that the PowerPoint "
                "file is valid and not password-protected."
            )
        run_command(
            [renderer, "-png", "-r", str(dpi), str(pdf), str(work_dir / "slide")]
        )
        images = sorted(
            work_dir.glob("slide-*.png"),
            key=lambda path: int(path.stem.rsplit("-", 1)[1]),
        )
        if not images:
            raise RuntimeError("The conversion did not produce any images.")

        # Replace old slides only after the complete rendering has succeeded.
        output_dir.mkdir(exist_ok=True)
        for path in existing:
            path.unlink()
        result = []
        for number, image in enumerate(images, start=1):
            destination = output_dir / f"slide{number:03d}.png"
            shutil.move(str(image), str(destination))
            result.append(destination)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert all slides in a PowerPoint presentation to separate PNG files."
    )
    parser.add_argument(
        "powerpoint",
        nargs="?",
        type=Path,
        default=Path("pptxs/Infographs.pptx"),
        help=".pptx file (default: pptxs/Infographs.pptx).",
    )
    parser.add_argument(
        "--dpi", type=int, default=150, help="PNG resolution in DPI (default: 150)."
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing slide PNG files."
    )
    args = parser.parse_args()
    try:
        images = convert_powerpoint(args.powerpoint, args.dpi, args.overwrite)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Conversion completed: {len(images)} slides in {images[0].parent}")
    for image in images:
        print(image)
    return 0


if __name__ == "__main__":
    sys.exit(main())
