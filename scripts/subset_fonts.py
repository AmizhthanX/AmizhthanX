#!/usr/bin/env python3
"""One-off: trim the source fonts to the characters the SVG cards can use.

SVGs shown through <img> can't fetch web fonts, so each card embeds its fonts
as base64. Full families are 70-140 KB; trimmed to ASCII they are a few KB.
The output is committed, so the daily workflow needs neither fonttools nor
brotli. Re-run only when changing typefaces:

    pip install fonttools brotli
    python3 scripts/subset_fonts.py InstrumentSerif-Regular.ttf IBMPlexMono-Regular.ttf
"""
import sys
from pathlib import Path

from fontTools import subset

OUT = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# Printable ASCII covers names, numbers, and month and language names, plus
# the few typographic marks the cards use.
TEXT = "".join(chr(c) for c in range(0x20, 0x7F)) + "·—–’…×"
# The OFL bars modified versions from using a Reserved Font Name, and trimming
# is a modification, so the subsets carry neutral family names instead.
RENAME = {"InstrumentSerif-Regular": "Card Serif", "IBMPlexMono-Regular": "Card Mono"}


def main(paths):
    OUT.mkdir(parents=True, exist_ok=True)
    for p in map(Path, paths):
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["kern", "liga", "lnum", "tnum"]
        opts.name_IDs = [0, 1, 2, 4, 6, 13, 14]  # keep copyright and licence records
        font = subset.load_font(str(p), opts)
        sub = subset.Subsetter(opts)
        sub.populate(text=TEXT)
        sub.subset(font)
        family = RENAME[p.stem]
        for rec in font["name"].names:
            if rec.nameID in (1, 4):
                rec.string = family
            elif rec.nameID == 6:
                rec.string = family.replace(" ", "")
        dest = OUT / f"{family.replace(' ', '')}.woff2"
        subset.save_font(font, str(dest), opts)
        print(f"{p.name}: {p.stat().st_size:,} -> {dest.name} {dest.stat().st_size:,} bytes")


if __name__ == "__main__":
    main(sys.argv[1:])
