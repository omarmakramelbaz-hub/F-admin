#!/usr/bin/env python3
"""Package the approved GO PNG as existing Android and iOS app/launch icons."""

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

from PIL import Image


BACKGROUND = (9, 19, 32)
DENSITIES = {"mdpi": Decimal("1"), "hdpi": Decimal("1.5"), "xhdpi": Decimal("2"), "xxhdpi": Decimal("3"), "xxxhdpi": Decimal("4")}
APP_ICONS = PurePosixPath("ios/Runner/Assets.xcassets/AppIcon.appiconset")
LAUNCH_IMAGES = PurePosixPath("ios/Runner/Assets.xcassets/LaunchImage.imageset")
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._@-]*\.png$", re.IGNORECASE)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(root, relative):
    relative = PurePosixPath(relative)
    require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe icon output path")
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        if current.exists() or current.is_symlink():
            info = current.lstat()
            require(not stat.S_ISLNK(info.st_mode), "Icon output must not traverse a symlink: " + str(relative))
            if index < len(relative.parts) - 1:
                require(stat.S_ISDIR(info.st_mode), "Icon parent is not a directory: " + str(relative))
            else:
                require(stat.S_ISREG(info.st_mode), "Icon output is not a regular file: " + str(relative))
    return current


def read_contents(root, directory, required=True):
    path = safe_path(root, directory / "Contents.json")
    if not path.exists() and not required:
        return None
    require(path.is_file(), "Missing existing Apple icon catalog: " + str(path))
    require(path.stat().st_size <= 256 * 1024, "Apple icon catalog is unexpectedly large")
    contents = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(contents, dict) and isinstance(contents.get("images"), list), "Invalid Apple icon catalog")
    require(1 <= len(contents["images"]) <= 128, "Unexpected Apple icon image count")
    return contents


def scale_of(entry):
    value = entry.get("scale", "1x")
    require(value in ("1x", "2x", "3x"), "Unsupported Apple icon scale")
    return int(value[0])


def icon_pixels(entry):
    require(isinstance(entry.get("size"), str), "Apple app icon size is missing")
    try:
        values = [Decimal(value) for value in entry["size"].split("x")]
        require(len(values) == 2 and all(value.is_finite() for value in values), "Invalid Apple icon size")
        require(values[0] == values[1] and 0 < values[0] <= 1024, "Apple app icons must be square")
        pixels = values[0] * scale_of(entry)
        require(pixels == pixels.to_integral_value() and pixels <= 3072, "Apple icon pixel size is not integral")
        return int(pixels)
    except (InvalidOperation, IndexError) as error:
        raise ValueError("Invalid Apple icon dimensions") from error


def filename_of(entry, fallback):
    filename = entry.get("filename")
    if filename is None:
        filename = fallback
        entry["filename"] = filename
    require(isinstance(filename, str) and SAFE_FILENAME.fullmatch(filename), "Unsafe Apple icon filename")
    require("/" not in filename and "\\" not in filename, "Unsafe Apple icon filename")
    return filename


def atomic_bytes(root, relative, data):
    destination = safe_path(root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = safe_path(root, relative)
    descriptor, temporary = tempfile.mkstemp(prefix=".app-icon-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def render(source, canvas_size, content_size):
    result = Image.new("RGB", (canvas_size, canvas_size), BACKGROUND)
    image = source.resize((content_size, content_size), Image.Resampling.LANCZOS)
    offset = (canvas_size - content_size) // 2
    result.paste(image, (offset, offset), image)
    return result


def generate(root, source_path):
    root = Path(root).resolve()
    source_path = Path(source_path)
    if not source_path.is_absolute():
        source_path = root / source_path
    require(source_path.is_file() and not source_path.is_symlink(), "Missing root-approved GO PNG: " + str(source_path))
    source_bytes = source_path.read_bytes()
    with Image.open(source_path) as original:
        require(original.format == "PNG", "The root-approved GO source must be a PNG")
        require(original.width == original.height and 512 <= original.width <= 8192, "GO source must be a square PNG between 512 and 8192 pixels")
        original.load()
        source = original.convert("RGBA")

    catalogs = {}
    plan = {}

    def add(relative, canvas_size, content_size):
        relative = PurePosixPath(relative)
        destination = safe_path(root, relative)
        require(destination.resolve() != source_path.resolve(), "The source PNG must not be overwritten")
        specification = (canvas_size, content_size)
        require(relative not in plan or plan[relative] == specification, "An icon filename has conflicting dimensions")
        plan[relative] = specification

    for density, multiplier in DENSITIES.items():
        launcher = int(Decimal(48) * multiplier)
        add("android/app/src/main/res/mipmap-" + density + "/ic_launcher.png", launcher, launcher)
        canvas = int(Decimal(288) * multiplier)
        content = int(Decimal(192) * multiplier)
        for variant in ("drawable-", "drawable-night-"):
            add("android/app/src/main/res/" + variant + density + "/android12splash.png", canvas, content)

    app_catalog = read_contents(root, APP_ICONS)
    for entry in app_catalog["images"]:
        require(isinstance(entry, dict), "Invalid Apple app icon entry")
        pixels = icon_pixels(entry)
        filename = filename_of(entry, "AppIcon-" + str(pixels) + ".png")
        add(APP_ICONS / filename, pixels, pixels)
    catalogs[APP_ICONS / "Contents.json"] = app_catalog

    launch_catalog = read_contents(root, LAUNCH_IMAGES, required=False)
    if launch_catalog is not None:
        for entry in launch_catalog["images"]:
            require(isinstance(entry, dict), "Invalid Apple launch image entry")
            scale = scale_of(entry)
            filename = filename_of(entry, "LaunchImage-" + str(scale) + "x.png")
            add(LAUNCH_IMAGES / filename, 390 * scale, 160 * scale)
        catalogs[LAUNCH_IMAGES / "Contents.json"] = launch_catalog

    # Validate every output before writing any resources or changing catalog metadata.
    for relative in catalogs:
        require(safe_path(root, relative).resolve() != source_path.resolve(), "The source PNG must not be overwritten")

    import io
    for relative, (canvas_size, content_size) in plan.items():
        output = io.BytesIO()
        render(source, canvas_size, content_size).save(output, format="PNG", compress_level=9, optimize=False)
        atomic_bytes(root, relative, output.getvalue())
    for relative, contents in catalogs.items():
        atomic_bytes(root, relative, (json.dumps(contents, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    require(source_path.read_bytes() == source_bytes, "The source PNG unexpectedly changed")
    return {
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "generated": [str(relative) for relative in list(plan) + list(catalogs)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source", type=Path, default=Path("assets/dashboard-icon.png"))
    args = parser.parse_args()
    try:
        print(json.dumps(generate(args.root, args.source), indent=2, ensure_ascii=False))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, "App icon generation failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
