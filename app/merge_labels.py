#!/usr/bin/env python3
"""
merge_labels.py — Основная логика объединения PDF.
Импортируется FastAPI-приложением.
"""

import re
import os
import fitz  # pymupdf


# ─── Шрифты ───────────────────────────────────────────────────────────────

_FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial.ttf",
]
_FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]

def _find_font(candidates):
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        f"Не найден TTF-шрифт. Проверьте пути: {candidates}"
    )

FONT_REGULAR = _find_font(_FONT_CANDIDATES_REGULAR)
FONT_BOLD    = _find_font(_FONT_CANDIDATES_BOLD)


# ─── Извлечение номера отправления ────────────────────────────────────────

def extract_shipment(page: fitz.Page) -> str | None:
    text = page.get_text()
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'^(\d+-\d{4}-\d{1,3})\d{4}$', line)
        if m:
            return m.group(1)
        m2 = re.match(r'^(\d+-\d{4}-\d{1,3})$', line)
        if m2:
            return m2.group(1)
    m = re.search(r'(\d{5,}-\d{4}-\d{1,3})(?:\d{4})?(?!\d)', text)
    return m.group(1) if m else None


# ─── Парсинг листа сборки ─────────────────────────────────────────────────

def parse_assembly_list(pdf_path: str) -> dict:
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    doc.close()

    items = {}
    lines = [l.strip() for l in full_text.splitlines()]

    i = 0
    while i < len(lines):
        line = lines[i]

        m = re.search(r'(\d{5,}-\d{4}-\d{1,3})$', line)
        if not m:
            m = re.search(r'\d{1,3}\s+(\d{5,}-\d{4}-\d{1,3})$', line)
        if not m:
            i += 1
            continue

        shipment = m.group(1)
        name_parts, article, qty = [], "", "1"

        j = i + 1
        while j < len(lines) and j < i + 10:
            nl = lines[j]
            if not nl:
                j += 1
                continue
            if re.match(r'^\d{1,2}$', nl):
                qty = nl
                j += 1
                break
            if re.match(r'^\d{4}$', nl):
                j += 1
                break
            if (re.match(r'^[A-Za-zА-Яа-яЁё0-9_\-\/]+$', nl)
                    and 2 <= len(nl) <= 40
                    and not re.match(r'^\d+$', nl)
                    and not article
                    and name_parts):
                article = nl
            else:
                name_parts.append(nl)
            j += 1

        name = " ".join(p for p in name_parts if p)
        if shipment not in items:
            items[shipment] = {
                "shipment": shipment,
                "name": name,
                "article": article,
                "qty": qty,
            }
        i = j

    return items


# ─── Страница с деталями ──────────────────────────────────────────────────

def make_detail_page(item: dict, w: float, h: float) -> fitz.Document:
    BLACK = (0, 0, 0)
    GRAY  = (0.5, 0.5, 0.5)

    doc  = fitz.open()
    page = doc.new_page(width=w, height=h)
    page.insert_font(fontname="reg",  fontfile=FONT_REGULAR)
    page.insert_font(fontname="bold", fontfile=FONT_BOLD)

    fs_small  = max(4.5, w * 0.030)
    fs_normal = max(6.0, w * 0.042)
    fs_large  = max(7.5, w * 0.052)
    margin    = max(5, w * 0.04)
    y = margin

    def lh(fs, gap=1.8):
        return fs + gap

    # Номер отправления
    shipment = item.get("shipment", "")
    page.insert_text((margin, y + fs_small), shipment,
                     fontsize=fs_small, fontname="reg", color=GRAY)
    y += lh(fs_small, 4)

    page.draw_line((margin, y), (w - margin, y), color=BLACK, width=0.5)
    y += 5

    # Наименование
    page.insert_text((margin, y + fs_small), "Наименование",
                     fontsize=fs_small, fontname="reg", color=GRAY)
    y += lh(fs_small, 2)

    name = item.get("name") or "—"
    words = name.split()
    cur_line, wrapped = [], []
    max_chars = max(1, int((w - margin * 2) / (fs_normal * 0.56)))
    for word in words:
        test = " ".join(cur_line + [word])
        if len(test) <= max_chars or not cur_line:
            cur_line.append(word)
        else:
            wrapped.append(" ".join(cur_line))
            cur_line = [word]
    if cur_line:
        wrapped.append(" ".join(cur_line))
    for ln in wrapped:
        page.insert_text((margin, y + fs_normal), ln,
                         fontsize=fs_normal, fontname="bold", color=BLACK)
        y += lh(fs_normal, 1.5)
    y += 4

    page.draw_line((margin, y), (w - margin, y), color=BLACK, width=0.3)
    y += 5

    # Артикул
    page.insert_text((margin, y + fs_small), "Артикул",
                     fontsize=fs_small, fontname="reg", color=GRAY)
    y += lh(fs_small, 2)
    page.insert_text((margin, y + fs_normal), item.get("article") or "—",
                     fontsize=fs_normal, fontname="reg", color=BLACK)
    y += lh(fs_normal, 4)

    # Количество
    page.insert_text((margin, y + fs_small), "Количество",
                     fontsize=fs_small, fontname="reg", color=GRAY)
    y += lh(fs_small, 2)
    page.insert_text((margin, y + fs_large), f"{item.get('qty', '1')} шт.",
                     fontsize=fs_large, fontname="bold", color=BLACK)

    return doc


# ─── Основная функция ─────────────────────────────────────────────────────

def merge_labels(barcodes_path: str, assembly_path: str, output_path: str) -> dict:
    """
    Возвращает {'matched': N, 'unmatched': N, 'total_pages': N}
    """
    items = parse_assembly_list(assembly_path)
    barcodes_doc = fitz.open(barcodes_path)
    output_doc = fitz.open()
    matched, unmatched = 0, 0

    for idx in range(barcodes_doc.page_count):
        src_page = barcodes_doc[idx]
        w, h = src_page.rect.width, src_page.rect.height

        output_doc.insert_pdf(barcodes_doc, from_page=idx, to_page=idx)

        shipment = extract_shipment(src_page)
        if shipment and shipment in items:
            detail_doc = make_detail_page(items[shipment], w, h)
            output_doc.insert_pdf(detail_doc)
            detail_doc.close()
            matched += 1
        else:
            fallback_doc = fitz.open()
            fp = fallback_doc.new_page(width=w, height=h)
            fp.insert_font(fontname="reg", fontfile=FONT_REGULAR)
            fp.insert_text((8, h / 2), "Данные не найдены",
                           fontsize=7, fontname="reg", color=(0.6, 0, 0))
            if shipment:
                fp.insert_text((8, h / 2 + 10), shipment,
                               fontsize=5.5, fontname="reg", color=(0.5, 0.5, 0.5))
            output_doc.insert_pdf(fallback_doc)
            fallback_doc.close()
            unmatched += 1

    barcodes_doc.close()
    output_doc.save(output_path, garbage=4, deflate=True)
    output_doc.close()

    return {
        "matched": matched,
        "unmatched": unmatched,
        "total_pages": (matched + unmatched) * 2,
    }
