"""Contact sheets: the drawing under the visual lenses (lens.py) and review_grid.py (dedupe.py --pairs still draws its
own pairs). Read only, offline.

A sheet is a JPG small enough for an AI agent to read in one go (the Read tool shows it as an image) and for the owner
to open. Every card on it carries a number; the same number leads the line of `index.tsv` (the text: key, titles,
links) and of `summary.json` (the same, machine-readable). An agent looks at the sheet, names the numbers it doubts,
then reads their lines: the picture finds, the index proves.

Two layouts:
- grid: one photo per product, 10 to a line, 60 to a sheet (a section, a price ladder, a brand list);
- rows: one line per product, its label on the left and several photos after it, lines of one group under one
  banner (duplicates, held products, products side by side).

Labels use Apple SD Gothic Neo when present (Korean and Latin), else Arial, else Pillow's default (Latin only).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

FONTS = ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
         "/System/Library/Fonts/Supplemental/Arial.ttf")
MARKS = {"flag": (220, 30, 30), "ok": (30, 140, 60), "info": (30, 80, 200), None: (110, 110, 110)}


@dataclass
class Card:
    """One product on a sheet. `n` is its number everywhere (sheet, index.tsv, summary.json); `photos` are local paths
    (missing files draw "no photo"); `lines` are short labels (price, brand, reason); `mark` colours the number:
    "flag" (red: look at it), "ok" (green), "info" (blue), None (grey); `group` puts rows under one banner."""
    n: int
    key: str
    photos: list[str | None] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    mark: str | None = None
    group: str | None = None
    data: dict[str, Any] = field(default_factory=dict)          # anything else for index.tsv / summary.json


def _font(size: int):
    from PIL import ImageFont
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _paste(sheet, pen, font, path: str | None, x: int, y: int, thumb: int) -> None:
    from PIL import Image
    if path:
        try:
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((thumb - 4, thumb - 4))
                sheet.paste(im, (x + 2 + (thumb - 4 - im.width) // 2, y + 2 + (thumb - 4 - im.height) // 2))
                return
        except OSError:
            pass
    pen.rectangle((x + 2, y + 2, x + thumb - 3, y + thumb - 3), outline=(200, 200, 200))
    pen.text((x + 8, y + thumb // 2 - 6), "no photo", fill=(150, 150, 150), font=font)


def _clip(pen, font, text: str, width: int) -> str:
    """The text cut to fit `width` pixels, with an ellipsis."""
    if pen.textlength(text, font=font) <= width:
        return text
    while text and pen.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def _wrap(pen, font, lines: list[str], width: int, most: int) -> list[str]:
    """The lines wrapped at spaces to `width` pixels, at most `most` lines in all, the last one clipped: a title's
    tail ("... or Single Wedge", "1 pcs") is what shows a misfit, so it gets lines rather than an ellipsis."""
    out: list[str] = []
    for text in lines:
        words, line = str(text).split(), ""
        for w in words:
            trial = f"{line} {w}".strip()
            if pen.textlength(trial, font=font) <= width or not line:
                line = trial
            else:
                out.append(line)
                line = w
        out.append(line)
    if len(out) > most:
        out = out[:most - 1] + [" ".join(out[most - 1:])]
    return [_clip(pen, font, x, width) for x in out[:most]]


def grid(cards: list[Card], out: str, prefix: str = "sheet", per_sheet: int = 60, columns: int = 10,
         thumb: int = 150, label_lines: int = 2) -> list[str]:
    """Sheets of one photo per card: the number (coloured by mark) and `label_lines` of its lines under it."""
    from PIL import Image, ImageDraw
    os.makedirs(out, exist_ok=True)
    font = _font(12)
    cell_h = thumb + 4 + 15 * (1 + label_lines)
    paths = []
    for start in range(0, max(len(cards), 1), per_sheet):
        chunk = cards[start:start + per_sheet]
        if not chunk:
            break
        lines = (len(chunk) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * thumb, lines * cell_h), "white")
        pen = ImageDraw.Draw(sheet)
        for i, card in enumerate(chunk):
            x, y = (i % columns) * thumb, (i // columns) * cell_h
            _paste(sheet, pen, font, card.photos[0] if card.photos else None, x, y, thumb)
            pen.text((x + 3, y + thumb + 1), str(card.n), fill=MARKS.get(card.mark, MARKS[None]), font=font)
            for j, text in enumerate(_wrap(pen, font, card.lines, thumb - 6, label_lines) if label_lines else []):
                pen.text((x + 3, y + thumb + 16 + 15 * j), text, fill="black", font=font)
        path = os.path.join(out, f"{prefix}{start // per_sheet + 1}.jpg")
        sheet.save(path, quality=72)
        paths.append(path)
    return paths


def rows(cards: list[Card], out: str, prefix: str = "sheet", per_sheet: int = 12, photos: int = 4,
         thumb: int = 130, label_width: int = 200) -> list[str]:
    """Sheets of one line per card: a label column (number, then its lines, wrapped) and up to `photos` photos; a new
    `group` starts with a banner line. A group that fits on one sheet is never split; a longer one goes on from the
    current sheet. The label column takes the room the page's photos leave (at least `label_width`)."""
    from PIL import Image, ImageDraw
    os.makedirs(out, exist_ok=True)
    font, bold = _font(12), _font(14)
    banner = 22
    pages: list[list[Card]] = [[]]
    for group in _groups(cards):
        if pages[-1] and len(group) <= per_sheet and len(pages[-1]) + len(group) > per_sheet:
            pages.append([])
        for card in group:
            if len(pages[-1]) >= per_sheet:
                pages.append([])
            pages[-1].append(card)
    paths = []
    for p, page in enumerate(page for page in pages if page):
        banners = sum(1 for i, c in enumerate(page) if c.group is not None and (i == 0 or page[i - 1].group != c.group))
        height = len(page) * (thumb + 4) + banners * banner
        used = max((min(len(c.photos), photos) for c in page), default=0) or 1
        width = label_width + photos * thumb
        label = width - used * thumb                    # the photos the page draws, the rest for the labels
        sheet = Image.new("RGB", (width, height), "white")
        pen = ImageDraw.Draw(sheet)
        y = 0
        for i, card in enumerate(page):
            if card.group is not None and (i == 0 or page[i - 1].group != card.group):
                pen.rectangle((0, y, sheet.width, y + banner - 2), fill=(235, 235, 245))
                pen.text((4, y + 3), _clip(pen, bold, card.group, sheet.width - 8), fill="black", font=bold)
                y += banner
            pen.text((4, y + 2), str(card.n), fill=MARKS.get(card.mark, MARKS[None]), font=bold)
            for j, text in enumerate(_wrap(pen, font, card.lines, label - 8, (thumb - 20) // 15)):
                pen.text((4, y + 20 + 15 * j), text, fill="black", font=font)
            for k in range(min(len(card.photos), photos)):
                _paste(sheet, pen, font, card.photos[k], label + k * thumb, y, thumb)
            pen.line((0, y + thumb + 2, sheet.width, y + thumb + 2), fill=(225, 225, 225))
            y += thumb + 4
        path = os.path.join(out, f"{prefix}{p + 1}.jpg")
        sheet.save(path, quality=72)
        paths.append(path)
    return paths


def _groups(cards: list[Card]) -> Iterable[list[Card]]:
    run: list[Card] = []
    for card in cards:
        if run and card.group != run[-1].group:
            yield run
            run = []
        run.append(card)
    if run:
        yield run


def _cell(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        value = ", ".join(str(v) for v in value)
    return " ".join(str("" if value is None else value).split())


def write_index(cards: list[Card], out: str, columns: list[str], meta: dict[str, Any] | None = None) -> tuple[str, str]:
    """index.tsv (n, key, group, mark, then `columns` from each card's data) and summary.json ({meta, cards: [{n,
    key, group, mark, lines, **data}]}) into `out`. -> both paths."""
    os.makedirs(out, exist_ok=True)
    tsv, js = os.path.join(out, "index.tsv"), os.path.join(out, "summary.json")
    with open(tsv, "w", encoding="utf-8") as f:
        f.write("\t".join(["n", "key", "group", "mark", *columns]) + "\n")
        for c in cards:
            f.write("\t".join([str(c.n), c.key, _cell(c.group), _cell(c.mark),
                               *(_cell(c.data.get(col)) for col in columns)]) + "\n")
    with open(js, "w", encoding="utf-8") as f:
        json.dump({"meta": meta or {}, "cards": [{"n": c.n, "key": c.key, "group": c.group, "mark": c.mark,
                                                  "lines": c.lines, **c.data} for c in cards]},
                  f, ensure_ascii=False, indent=1)
    return tsv, js
