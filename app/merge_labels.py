#!/usr/bin/env python3
"""
merge_labels.py — Основная логика объединения PDF.
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
    raise FileNotFoundError(f"Не найден TTF-шрифт. Проверьте пути: {candidates}")

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


# ─── Номер этикетки ───────────────────────────────────────────────────────

def get_label_number(shipment: str) -> str:
    """Последние 4 цифры первого блока: 86604694-0239-1 -> 4694"""
    m = re.match(r'^\d*(\d{4})-\d{4}-\d+$', shipment)
    return m.group(1) if m else ""


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
                "name":     name,
                "article":  article,
                "qty":      qty,
            }
        i = j

    return items


# ─── Страница с деталями товара ───────────────────────────────────────────

def make_detail_page(item: dict, w: float, h: float) -> fitz.Document:
    """
    Создаёт одностраничный PDF с деталями товара.
    Номер этикетки — компактно в правом верхнем углу.
    Остальное — слева сверху вниз.
    """
    BLACK = (0, 0, 0)
    GRAY  = (0.55, 0.55, 0.55)
    WHITE = (1, 1, 1)

    doc  = fitz.open()
    page = doc.new_page(width=w, height=h)
    page.insert_font(fontname="reg",  fontfile=FONT_REGULAR)
    page.insert_font(fontname="bold", fontfile=FONT_BOLD)

    margin    = max(8, w * 0.055)
    fs_label  = max(4.5, w * 0.028)
    fs_normal = max(6.0, w * 0.040)
    fs_large  = max(7.5, w * 0.050)

    shipment  = item.get("shipment", "")
    label_num = get_label_number(shipment)

    # ── Номер этикетки — правый верхний угол ──────────────────────────────
    if label_num:
        fs_tag   = max(9, w * 0.065)        # чуть крупнее основного текста
        tag_pad  = 3
        tag_w    = len(label_num) * fs_tag * 0.60 + tag_pad * 2
        tag_h    = fs_tag + tag_pad * 2
        tag_x    = w - margin - tag_w
        tag_y    = margin - tag_pad

        # # Подпись над рамкой
        # lbl_text = "этикетка"
        # page.insert_text(
        #     (tag_x, tag_y - 1),
        #     lbl_text,
        #     fontsize=fs_label, fontname="reg", color=GRAY,
        # )
        # Чёрная рамка
        box = fitz.Rect(tag_x, tag_y + fs_label + 1,
                        tag_x + tag_w, tag_y + fs_label + 1 + tag_h)
        page.draw_rect(box, color=BLACK, fill=BLACK)
        # Цифры белым
        page.insert_text(
            (tag_x + tag_pad, box.y1 - tag_pad),
            label_num,
            fontsize=fs_tag, fontname="bold", color=WHITE,
        )

    # ── Левая колонка: основные данные ────────────────────────────────────
    # Ограничиваем правую границу текста чтобы не залезать на номер этикетки
    right_limit = (w - margin - max(9, w * 0.065) * 2.8) if label_num else (w - margin)
    max_chars = max(1, int((right_limit - margin) / (fs_normal * 0.56)))

    y = margin

    # Номер отправления
    page.insert_text(
        (margin, y + fs_label),
        shipment,
        fontsize=fs_label, fontname="reg", color=GRAY,
    )
    y += fs_label + 5

    y += 6

    # Наименование
    page.insert_text(
        (margin, y + fs_label),
        "Наименование",
        fontsize=fs_label, fontname="reg", color=GRAY,
    )
    y += fs_label + 3

    name = item.get("name") or "—"
    words = name.split()
    cur_line, wrapped = [], []
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
        page.insert_text(
            (margin, y + fs_normal),
            ln,
            fontsize=fs_normal, fontname="bold", color=BLACK,
        )
        y += fs_normal + 2
    y += 5

    # Разделитель
    page.draw_line((margin, y), (w - margin, y), color=BLACK, width=0.3)
    y += 6

    # Артикул и Количество
    col2_x = w * 0.52
    page.insert_text((margin,  y + fs_label), "Артикул",
                     fontsize=fs_label, fontname="reg", color=GRAY)
    page.insert_text((col2_x, y + fs_label), "Количество",
                     fontsize=fs_label, fontname="reg", color=GRAY)
    y += fs_label + 3

    page.insert_text(
        (margin, y + fs_normal),
        item.get("article") or "—",
        fontsize=fs_normal, fontname="reg", color=BLACK,
    )
    page.insert_text(
        (col2_x, y + fs_large),
        f"{item.get('qty', '1')} шт.",
        fontsize=fs_large, fontname="bold", color=BLACK,
    )

    return doc


# ─── Основная функция ─────────────────────────────────────────────────────

def merge_labels(barcodes_path: str, assembly_path: str, output_path: str) -> dict:
    items        = parse_assembly_list(assembly_path)
    barcodes_doc = fitz.open(barcodes_path)
    output_doc   = fitz.open()
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
        "matched":     matched,
        "unmatched":   unmatched,
        "total_pages": (matched + unmatched) * 2,
    }
