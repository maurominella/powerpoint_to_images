from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from powerpoint_to_images import convert_powerpoint, main


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "My slides.pptx"
        self.source.write_bytes(b"presentation")
        self.output = self.source.with_suffix("")

    def render(self, command, **kwargs):
        if "--convert-to" in command:
            directory = Path(command[command.index("--outdir") + 1])
            (directory / f"{self.source.stem}.pdf").write_bytes(b"pdf")
        else:
            prefix = command[-1]
            for number in range(12, 0, -1):
                Path(f"{prefix}-{number}.png").write_bytes(f"png{number}".encode())
        return subprocess.CompletedProcess(command, 0, "", "")

    @patch("powerpoint_to_images.shutil.which", side_effect=lambda name: name)
    def test_sequential_names_and_numeric_order(self, which):
        with patch("powerpoint_to_images.subprocess.run", side_effect=self.render) as run:
            images = convert_powerpoint(self.source, dpi=200)
        self.assertEqual(
            [image.name for image in images],
            [f"slide{number:03d}.png" for number in range(1, 13)],
        )
        self.assertTrue(all(image.parent == self.output for image in images))
        self.assertEqual(images[1].read_bytes(), b"png2")
        self.assertEqual(images[9].read_bytes(), b"png10")
        self.assertIn("200", run.call_args_list[1].args[0])
        self.assertFalse((self.source.parent / f"{self.source.stem}.pdf").exists())
        self.assertEqual(self.source.read_bytes(), b"presentation")

    def test_invalid_input(self):
        with self.assertRaisesRegex(ValueError, "File not found"):
            convert_powerpoint(self.source.parent / "missing.pptx")
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            convert_powerpoint(self.source, dpi=0)
        wrong_extension = self.source.with_suffix(".txt")
        wrong_extension.touch()
        with self.assertRaisesRegex(ValueError, "extension"):
            convert_powerpoint(wrong_extension)

    @patch("powerpoint_to_images.shutil.which", return_value=None)
    def test_missing_dependencies(self, which):
        with self.assertRaisesRegex(RuntimeError, "libreoffice-impress poppler-utils"):
            convert_powerpoint(self.source)
        self.assertFalse(self.output.exists())

    def test_existing_images_are_protected(self):
        self.output.mkdir()
        image = self.output / "slide001.png"
        image.write_bytes(b"old")
        with self.assertRaisesRegex(ValueError, "--overwrite"):
            convert_powerpoint(self.source)
        self.assertEqual(image.read_bytes(), b"old")

    @patch("powerpoint_to_images.shutil.which", side_effect=lambda name: name)
    def test_overwrite_removes_stale_slides_but_keeps_other_files(self, which):
        self.output.mkdir()
        (self.output / "slide099.png").write_bytes(b"old")
        other = self.output / "notes.txt"
        other.write_text("keep")
        with patch("powerpoint_to_images.subprocess.run", side_effect=self.render):
            images = convert_powerpoint(self.source, overwrite=True)
        self.assertEqual(len(images), 12)
        self.assertFalse((self.output / "slide099.png").exists())
        self.assertEqual(other.read_text(), "keep")

    @patch("powerpoint_to_images.shutil.which", side_effect=lambda name: name)
    def test_failed_conversion_preserves_previous_images(self, which):
        self.output.mkdir()
        image = self.output / "slide001.png"
        image.write_bytes(b"old")
        error = subprocess.CalledProcessError(1, ["libreoffice"], stderr="invalid file")
        with patch("powerpoint_to_images.subprocess.run", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "invalid file"):
                convert_powerpoint(self.source, overwrite=True)
        self.assertEqual(image.read_bytes(), b"old")

    @patch("powerpoint_to_images.shutil.which", side_effect=lambda name: name)
    def test_missing_pdf_is_reported(self, which):
        with patch("powerpoint_to_images.subprocess.run"):
            with self.assertRaisesRegex(RuntimeError, "did not produce the PDF"):
                convert_powerpoint(self.source)
        self.assertFalse(self.output.exists())

    @patch("powerpoint_to_images.shutil.which", side_effect=lambda name: name)
    def test_missing_images_is_reported(self, which):
        def pdf_only(command, **kwargs):
            if "--convert-to" in command:
                return self.render(command, **kwargs)
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("powerpoint_to_images.subprocess.run", side_effect=pdf_only):
            with self.assertRaisesRegex(RuntimeError, "did not produce any images"):
                convert_powerpoint(self.source)
        self.assertFalse(self.output.exists())

    @patch("powerpoint_to_images.shutil.which", side_effect=lambda name: name)
    def test_timeout_is_reported(self, which):
        with patch(
            "powerpoint_to_images.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["libreoffice"], 180),
        ):
            with self.assertRaisesRegex(RuntimeError, "180 seconds"):
                convert_powerpoint(self.source)

    def test_cli_reports_error(self):
        with patch("sys.argv", ["powerpoint_to_images.py", "missing.pptx"]):
            with patch("sys.stderr") as stderr:
                self.assertEqual(main(), 1)
        self.assertIn("File not found", stderr.write.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
