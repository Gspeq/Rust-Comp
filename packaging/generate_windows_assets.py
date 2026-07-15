from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    values: list[int] = []
    for segment in version.split("."):
        digits = "".join(
            character
            for character in segment
            if character.isdigit()
        )
        values.append(int(digits or 0))
    return tuple((values + [0, 0, 0, 0])[:4])


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path(r"C:\Windows\Fonts\seguisb.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def create_icon(output: Path) -> None:
    canvas = Image.new(
        "RGBA",
        (256, 256),
        (10, 17, 28, 255),
    )
    draw = ImageDraw.Draw(canvas)

    for inset, color in (
        (0, (15, 23, 42, 255)),
        (12, (22, 32, 50, 255)),
        (24, (30, 41, 59, 255)),
    ):
        draw.rounded_rectangle(
            (
                inset,
                inset,
                255 - inset,
                255 - inset,
            ),
            radius=42,
            fill=color,
        )

    draw.rounded_rectangle(
        (26, 26, 230, 230),
        radius=35,
        outline=(249, 115, 22, 255),
        width=9,
    )

    font = _font(86)
    text = "R+"
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(
        (
            (256 - width) / 2,
            (256 - height) / 2 - 8,
        ),
        text,
        font=font,
        fill=(255, 247, 237, 255),
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(
        output,
        format="ICO",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )


def create_version_file(
    output: Path,
    version: str,
) -> None:
    major, minor, patch, build = _version_tuple(version)
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build}),
    prodvers=({major}, {minor}, {patch}, {build}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'Taylor Marshall'),
          StringStruct('FileDescription', 'Rust Companion+'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', 'RustCompanionPlus'),
          StringStruct('LegalCopyright', 'Copyright Taylor Marshall'),
          StringStruct('OriginalFilename', 'RustCompanionPlus.exe'),
          StringStruct('ProductName', 'Rust Companion+'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([
      VarStruct('Translation', [1033, 1200])
    ])
  ]
)
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        content,
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--icon", required=True)
    parser.add_argument("--version-file", required=True)
    args = parser.parse_args()

    create_icon(Path(args.icon))
    create_version_file(
        Path(args.version_file),
        args.version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
