"""Generate build-time static assets before Django collectstatic runs."""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

import csscompressor

BASE_DIR = Path(__file__).resolve().parent.parent
FONT_DIR = BASE_DIR / "portfolio" / "static" / "assets" / "fonts"
CSS_DIR = BASE_DIR / "portfolio" / "static" / "css"
GOOGLE_FONTS_COMMIT = "48133440178622e215912d34d386c5ee1682c677"
FONT_URLS = {
    "Montserrat.ttf": (
        "https://raw.githubusercontent.com/google/fonts/"
        f"{GOOGLE_FONTS_COMMIT}/ofl/montserrat/Montserrat%5Bwght%5D.ttf"
    ),
    "Lato.ttf": (
        "https://raw.githubusercontent.com/google/fonts/"
        f"{GOOGLE_FONTS_COMMIT}/ofl/lato/Lato-Regular.ttf"
    ),
}


def download_file(url: str, output_path: Path) -> None:
    """Download an external asset and fail if the response is not font-like."""
    with urlopen(url, timeout=60) as response:
        content = response.read()

    if output_path.suffix == ".ttf" and not content.startswith(b"\x00\x01\x00\x00"):
        raise RuntimeError(f"Downloaded file is not a TrueType font: {url}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)


def download_fonts() -> None:
    """Download self-hosted fonts used by portfolio/static/css/fonts.css."""
    for filename, url in FONT_URLS.items():
        download_file(url, FONT_DIR / filename)


def minify_css() -> None:
    """Create styles.min.css from styles.css for template static references."""
    source_path = CSS_DIR / "styles.css"
    output_path = CSS_DIR / "styles.min.css"
    output_path.write_text(
        csscompressor.compress(source_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )


def main() -> None:
    """Generate every non-tracked static input required by collectstatic."""
    download_fonts()
    minify_css()


if __name__ == "__main__":
    main()
