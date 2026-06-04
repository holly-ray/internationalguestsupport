import os
import io
import zipfile
from PIL import Image, ImageDraw, ImageFont

# Card dimensions
CARD_W = 800
CARD_PAD = 40
CARD_BODY_W = CARD_W - CARD_PAD * 2
TOP_BAR_H = 56
FOOTER_H = 32

# Colors
BLUE = "#2563eb"
WHITE = "#ffffff"
GRAY_BG = "#f9fafb"
GRAY_BORDER = "#e5e7eb"
GRAY_TEXT = "#9ca3af"
BODY_TEXT = "#374151"

_FONT = None


def _font(size, bold=False):
    global _FONT
    if _FONT is None:
        font_path = os.path.join(os.path.dirname(__file__), "static", "fonts", "NotoSansSC-Regular.ttf")
        if os.path.exists(font_path):
            _FONT = font_path
        else:
            return ImageFont.load_default()
    return ImageFont.truetype(_FONT, size)


def _wrap_lines(text, font, max_width):
    """Wrap text to fit within max_width using font metrics. Splits on word boundaries for Latin, character boundaries for CJK."""
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            trial = current + char
            bbox = font.getbbox(trial)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(current.strip())
                current = char
            else:
                current = trial
        if current.strip():
            lines.append(current.strip())
    return lines


def _text_height(text, font, max_width):
    lines = _wrap_lines(text, font, max_width)
    line_h = font.getbbox("Ag")[3] - font.getbbox("Ag")[1] + 6
    return max(len(lines), 1) * line_h


def _draw_text_block(draw, x, y, text, font, color, max_width):
    lines = _wrap_lines(text, font, max_width)
    line_h = font.getbbox("Ag")[3] - font.getbbox("Ag")[1] + 6
    for line in lines:
        draw.text((x, y), line, fill=color, font=font)
        y += line_h
    return y


def generate_card_image(text, lang, material_type, lang_label):
    """Render a single translation card as PNG. Returns BytesIO."""
    f_body = _font(20)
    f_header = _font(18, bold=True)
    f_badge = _font(14)
    f_footer = _font(12)
    f_title = _font(24, bold=True)

    body_text_height = _text_height(text, f_body, CARD_BODY_W)
    card_h = TOP_BAR_H + 24 + 20 + body_text_height + 24 + FOOTER_H

    img = Image.new("RGB", (CARD_W, int(card_h)), WHITE)
    draw = ImageDraw.Draw(img)

    # Top bar
    draw.rectangle([(0, 0), (CARD_W, TOP_BAR_H)], fill=BLUE)
    draw.text((CARD_PAD, (TOP_BAR_H - f_header.getbbox("Ag")[3]) / 2 - 2), material_type, fill=WHITE, font=f_header)

    # Language badge
    badge_text = lang_label
    badge_bbox = f_badge.getbbox(badge_text)
    badge_w = badge_bbox[2] - badge_bbox[0] + 24
    badge_h = badge_bbox[3] - badge_bbox[1] + 12
    badge_x = CARD_W - CARD_PAD - badge_w
    badge_y = TOP_BAR_H + 12
    draw.rounded_rectangle([(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)], radius=4, fill=BLUE)
    draw.text((badge_x + 12, badge_y + 6), badge_text, fill=WHITE, font=f_badge)

    # Body area
    body_y_start = TOP_BAR_H + 24 + 12
    body_y = body_y_start
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            body_y += f_body.getbbox("Ag")[3] - f_body.getbbox("Ag")[1] + 2
            continue
        body_y = _draw_text_block(draw, CARD_PAD, body_y, paragraph, f_body, BODY_TEXT, CARD_BODY_W) + 4

    # Footer
    footer_y = card_h - FOOTER_H
    draw.rectangle([(0, footer_y), (CARD_W, card_h)], fill=GRAY_BG)
    draw.line([(0, footer_y), (CARD_W, footer_y)], fill=GRAY_BORDER, width=1)
    ftext = "国际宾客支持 · 多语种物料生成"
    fb = f_footer.getbbox(ftext)
    draw.text(((CARD_W - fb[2] + fb[0]) / 2, footer_y + (FOOTER_H - fb[3] + fb[1]) / 2 - 1), ftext, fill=GRAY_TEXT, font=f_footer)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def generate_zip_of_cards(results, material_type, lang_label_map):
    """Generate a ZIP file containing one PNG per translation result. Returns BytesIO."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in results:
            if r.get("loading"):
                continue
            lang_label = lang_label_map.get(r["lang"], r["lang"])
            img_buf = generate_card_image(r["text"], r["lang"], material_type, lang_label)
            zf.writestr(f"{r['lang']}.png", img_buf.read())
    zip_buf.seek(0)
    return zip_buf
