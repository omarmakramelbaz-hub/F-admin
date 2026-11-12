import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate_app_icons.py"
SPEC = importlib.util.spec_from_file_location("generate_app_icons", SCRIPT)
ICONS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ICONS)


class GenerateAppIconsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="app-icon-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "assets/dashboard-icon.png"
        self.source.parent.mkdir()
        Image.new("RGBA", (512, 512), (0, 220, 255, 180)).save(self.source)
        self.original = self.source.read_bytes()
        self.catalog_path = self.root / ICONS.APP_ICONS / "Contents.json"
        self.catalog_path.parent.mkdir(parents=True)
        self.catalog = {
            "images": [
                {"filename": "120 1.png", "idiom": "universal", "size": "40x40", "scale": "3x"},
                {"filename": "Icon-196.png", "idiom": "universal", "size": "64x64", "scale": "3x"},
                {"idiom": "universal", "size": "83.5x83.5", "scale": "2x"},
                {"filename": "1024.png", "idiom": "universal", "size": "1024x1024"},
            ],
            "info": {"author": "xcode", "version": 1},
        }
        self.catalog_path.write_text(json.dumps(self.catalog))
        launch_path = self.root / ICONS.LAUNCH_IMAGES / "Contents.json"
        launch_path.parent.mkdir(parents=True)
        launch_path.write_text(json.dumps({
            "images": [{"idiom": "universal", "scale": str(scale) + "x", "filename": "LaunchImage" + str(scale) + ".png"} for scale in (1, 2, 3)],
            "info": {"author": "xcode", "version": 1},
        }))
        self.unrelated = self.root / "unrelated.txt"
        self.unrelated.write_bytes(b"do not change")

    def test_outputs_use_metadata_sizes_and_are_deterministic_and_opaque(self):
        first = ICONS.generate(self.root, Path("assets/dashboard-icon.png"))
        before = {relative: (self.root / relative).read_bytes() for relative in first["generated"]}
        second = ICONS.generate(self.root, self.source)
        self.assertEqual(first, second)
        self.assertEqual(before, {relative: (self.root / relative).read_bytes() for relative in second["generated"]})
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.unrelated.read_bytes(), b"do not change")
        for density, size in [("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)]:
            with Image.open(self.root / ("android/app/src/main/res/mipmap-" + density + "/ic_launcher.png")) as image:
                self.assertEqual(image.size, (size, size))
                self.assertEqual(image.mode, "RGB")
        for filename, size in [("120 1.png", 120), ("Icon-196.png", 192), ("AppIcon-167.png", 167), ("1024.png", 1024)]:
            with Image.open(self.root / ICONS.APP_ICONS / filename) as image:
                self.assertEqual(image.size, (size, size))
                self.assertEqual(image.mode, "RGB")
        with Image.open(self.root / "android/app/src/main/res/drawable-xxxhdpi/android12splash.png") as image:
            self.assertEqual(image.size, (1152, 1152))
            self.assertEqual(image.getpixel((0, 0)), ICONS.BACKGROUND)
        with Image.open(self.root / ICONS.LAUNCH_IMAGES / "LaunchImage3.png") as image:
            self.assertEqual(image.size, (1170, 1170))
            self.assertEqual(image.getpixel((0, 0)), ICONS.BACKGROUND)
        catalog = json.loads(self.catalog_path.read_text())
        self.assertEqual(catalog["info"], self.catalog["info"])
        self.assertEqual([entry["size"] for entry in catalog["images"]], [entry["size"] for entry in self.catalog["images"]])

    def test_unsafe_catalog_filename_is_rejected_before_any_output(self):
        self.catalog["images"][0]["filename"] = "../../outside.png"
        self.catalog_path.write_text(json.dumps(self.catalog))
        with self.assertRaisesRegex(ValueError, "filename"):
            ICONS.generate(self.root, self.source)
        self.assertFalse((self.root / "android").exists())
        self.assertFalse((self.root / "outside.png").exists())

    def test_symlinked_icon_parent_is_rejected_without_following_it(self):
        outside = self.root / "outside"
        outside.mkdir()
        parent = self.root / "android/app/src/main/res"
        parent.mkdir(parents=True)
        (parent / "mipmap-mdpi").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            ICONS.generate(self.root, self.source)
        self.assertEqual(list(outside.iterdir()), [])

    def test_missing_or_non_square_source_fails_clearly(self):
        self.source.unlink()
        with self.assertRaisesRegex(ValueError, "root-approved"):
            ICONS.generate(self.root, self.source)
        Image.new("RGB", (512, 513), "white").save(self.source)
        with self.assertRaisesRegex(ValueError, "square PNG"):
            ICONS.generate(self.root, self.source)
        self.assertFalse((self.root / "android").exists())


if __name__ == "__main__":
    unittest.main()
