import os
import io
import urllib.request
from PIL import Image, ImageDraw, ImageFont

def create_calendar_poster(output_path: str):
    # Dimensions
    W, H = 1200, 860
    img = Image.new("RGBA", (W, H), (13, 17, 23, 255))
    draw = ImageDraw.Draw(img)

    # 1. Subtle sleek gradient background
    for y in range(H):
        ratio = y / H
        if ratio < 0.5:
            r = int(11 + (18 - 11) * (ratio * 2))
            g = int(14 + (23 - 14) * (ratio * 2))
            b = int(20 + (30 - 20) * (ratio * 2))
        else:
            r = int(18 + (9 - 18) * ((ratio - 0.5) * 2))
            g = int(23 + (12 - 23) * ((ratio - 0.5) * 2))
            b = int(30 + (16 - 30) * ((ratio - 0.5) * 2))
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # Ambient neon cyber top glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([W//2 - 450, -180, W//2 + 450, 160], fill=(0, 180, 216, 28))
    glow_draw.ellipse([W//2 - 220, -100, W//2 + 220, 120], fill=(99, 102, 241, 24))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # Load Windows Segoe UI fonts
    font_path_bold = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "segoeuib.ttf")
    font_path_reg = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "segoeui.ttf")
    font_path_semi = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "seguisb.ttf")
    if not os.path.exists(font_path_bold):
        font_path_bold = "arial.ttf"
        font_path_reg = "arial.ttf"
        font_path_semi = font_path_bold

    font_badge = ImageFont.truetype(font_path_bold, 11)
    font_title = ImageFont.truetype(font_path_bold, 34)
    font_sub = ImageFont.truetype(font_path_semi if os.path.exists(font_path_semi) else font_path_reg, 15)
    font_card_title = ImageFont.truetype(font_path_bold, 18)
    font_card_sub = ImageFont.truetype(font_path_reg, 13)
    font_pill = ImageFont.truetype(font_path_bold, 11)
    font_tag = ImageFont.truetype(font_path_bold, 10)
    font_footer = ImageFont.truetype(font_path_reg, 12)

    # --- HEADER SECTION ---
    # Top pill badge
    badge_text = "STEAM RADAR  //  WEEK 45"
    b_w = 190
    b_h = 24
    bx = (W - b_w) // 2
    by = 22
    draw.rounded_rectangle([bx, by, bx + b_w, by + b_h], radius=12, fill=(30, 41, 59, 255), outline=(56, 189, 248, 200), width=1)
    draw.text((bx + 20, by + 4), badge_text, font=font_badge, fill=(56, 189, 248, 255))

    # Main Title
    title_text = "THIS WEEK'S STEAM RELEASES"
    t_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    draw.text(((W - (t_bbox[2] - t_bbox[0])) // 2, 54), title_text, font=font_title, fill=(255, 255, 255, 255))

    # Subtitle
    sub_text = "RELEASE WINDOW: NOV 04 - NOV 10, 2026   -   CURATED HIGHLIGHTS (PC & DLCS)"
    s_bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
    draw.text(((W - (s_bbox[2] - s_bbox[0])) // 2, 98), sub_text, font=font_sub, fill=(148, 163, 184, 255))

    # Header decorative separator
    draw.line([(40, 135), (W - 40, 135)], fill=(30, 41, 59, 220), width=1)

    # --- ITEMS DATA (Real Curated Steam Releases) ---
    items = [
        {
            "title": "Football Manager 27",
            "type": "BASE GAME",
            "type_color": (14, 165, 233),   # Cyan
            "date": "NOV 10, 2026",
            "genre": "Sports - Management - Strategy",
            "tag": "TOP WISHLIST",
            "tag_color": (56, 189, 248),
            "img_url": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/4530370/3d06aef381c925bb6c091f13be44dd294b205a72/capsule_231x87.jpg?t=1793774487"
        },
        {
            "title": "Euro Truck Sim 2 - Iceland",
            "type": "DLC / EXPANSION",
            "type_color": (217, 119, 6),   # Amber/Gold
            "date": "NOV 10, 2026",
            "genre": "Simulation - Map Expansion - Open World",
            "tag": "MAJOR EXPANSION",
            "tag_color": (251, 191, 36),
            "img_url": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/3796990/163aca1f29049f523c158ac0332710a123db2e0a/capsule_231x87.jpg?t=1793021069"
        },
        {
            "title": "DREADMOOR",
            "type": "BASE GAME",
            "type_color": (14, 165, 233),
            "date": "NOV 09, 2026",
            "genre": "Dark Fantasy - Action RPG - Roguelike",
            "tag": "HIGH ANTICIPATION",
            "tag_color": (248, 113, 113),
            "img_url": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/3629430/463d99fc377b03a3a20fc3b45915a8755ccabef4/capsule_231x87.jpg?t=1793299012"
        },
        {
            "title": "Monster Train 2: Punished",
            "type": "DLC / EXPANSION",
            "type_color": (168, 85, 247),   # Purple
            "date": "NOV 10, 2026",
            "genre": "Roguelike - Deckbuilder - Strategy",
            "tag": "CONTENT PACK",
            "tag_color": (192, 132, 252),
            "img_url": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/4739980/d91936de1b83e1b4457365acb0be975d5ed06390/capsule_231x87.jpg?t=1793737852"
        },
        {
            "title": "Find The Needle",
            "type": "BASE GAME",
            "type_color": (14, 165, 233),
            "date": "NOV 06, 2026",
            "genre": "Casual - Hidden Object - Relaxing",
            "tag": "INDIE SPOTLIGHT",
            "tag_color": (52, 211, 153),
            "img_url": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/5160800/3dec380fa3c66a40ffc1d36be2ac518cf9dcda05/capsule_231x87.jpg?t=1793692964"
        },
        {
            "title": "ROB RUN",
            "type": "BASE GAME",
            "type_color": (14, 165, 233),
            "date": "NOV 04, 2026",
            "genre": "Fast-Paced Action - Platformer - Precision",
            "tag": "LAUNCHING TODAY",
            "tag_color": (56, 189, 248),
            "img_url": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/4262460/0cef00dbfabf5f15adbf8b18e84cc8ef53dce963/capsule_231x87.jpg?t=1793787838"
        }
    ]

    # --- GRID LAYOUT ---
    cols = 3
    rows = 2
    card_w = 360
    card_h = 300
    gap_x = 20
    gap_y = 20
    start_x = 40
    start_y = 158

    for idx, item in enumerate(items):
        c = idx % cols
        r = idx // cols
        cx = start_x + c * (card_w + gap_x)
        cy = start_y + r * (card_h + gap_y)

        # Card Container Background
        draw.rounded_rectangle(
            [cx, cy, cx + card_w, cy + card_h],
            radius=12,
            fill=(22, 27, 34, 255),
            outline=(48, 54, 61, 230),
            width=1
        )

        # Download & paste capsule image
        img_w = card_w - 20
        img_h = 145
        capsule_x = cx + 10
        capsule_y = cy + 10

        try:
            req = urllib.request.Request(item["img_url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                cap_data = resp.read()
            cap_img = Image.open(io.BytesIO(cap_data)).convert("RGBA")
            cap_img = cap_img.resize((img_w, img_h), Image.Resampling.LANCZOS)
            
            # Mask rounded corners for image
            mask = Image.new("L", (img_w, img_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([0, 0, img_w, img_h], radius=8, fill=255)
            
            img.paste(cap_img, (capsule_x, capsule_y), mask)
        except Exception as ex:
            print(f"Error loading image for {item['title']}: {ex}")
            draw.rounded_rectangle([capsule_x, capsule_y, capsule_x + img_w, capsule_y + img_h], radius=8, fill=(33, 38, 45, 255))

        # --- BADGES OVER IMAGE ---
        # 1. Type Badge (Left)
        t_col = item["type_color"]
        type_w = draw.textbbox((0, 0), item["type"], font=font_pill)[2] + 16
        draw.rounded_rectangle(
            [capsule_x + 8, capsule_y + 8, capsule_x + 8 + type_w, capsule_y + 8 + 20],
            radius=6,
            fill=(t_col[0], t_col[1], t_col[2], 230)
        )
        draw.text((capsule_x + 16, capsule_y + 11), item["type"], font=font_pill, fill=(255, 255, 255, 255))

        # 2. Date Badge (Right)
        date_w = draw.textbbox((0, 0), item["date"], font=font_pill)[2] + 16
        date_x = capsule_x + img_w - date_w - 8
        draw.rounded_rectangle(
            [date_x, capsule_y + 8, date_x + date_w, capsule_y + 8 + 20],
            radius=6,
            fill=(13, 17, 23, 220),
            outline=(56, 189, 248, 160),
            width=1
        )
        draw.text((date_x + 8, capsule_y + 11), item["date"], font=font_pill, fill=(255, 255, 255, 255))

        # --- CARD BODY CONTENT ---
        text_y = capsule_y + img_h + 16
        
        # Title
        title_str = item["title"]
        if len(title_str) > 26:
            title_str = title_str[:25] + "…"
        draw.text((cx + 16, text_y), title_str, font=font_card_title, fill=(240, 246, 252, 255))

        # Genre / Category
        draw.text((cx + 16, text_y + 28), item["genre"], font=font_card_sub, fill=(139, 148, 158, 255))

        # Tag pill at bottom of card
        tag_text = item["tag"]
        tag_text_w = draw.textbbox((0, 0), tag_text, font=font_tag)[2]
        pill_w = tag_text_w + 30
        draw.rounded_rectangle(
            [cx + 16, cy + card_h - 38, cx + 16 + pill_w, cy + card_h - 16],
            radius=6,
            fill=(30, 41, 59, 255),
            outline=(56, 189, 248, 120),
            width=1
        )
        # Small colored indicator dot
        t_color = item["tag_color"]
        draw.ellipse([cx + 26, cy + card_h - 29, cx + 32, cy + card_h - 23], fill=t_color)
        draw.text((cx + 38, cy + card_h - 33), tag_text, font=font_tag, fill=t_color)

        # Steam link text on right
        draw.text((cx + card_w - 76, cy + card_h - 33), "STEAM >", font=font_pill, fill=(139, 148, 158, 255))

    # --- FOOTER SECTION ---
    draw.line([(40, start_y + 2 * (card_h + gap_y) + 15), (W - 40, start_y + 2 * (card_h + gap_y) + 15)], fill=(30, 41, 59, 220), width=1)
    
    footer_y = H - 34
    draw.text((40, footer_y), "AUTOMATED BY RELEASE MONITOR BOT  -  DELIVERED EVERY MONDAY 08:00 AM", font=font_footer, fill=(100, 116, 139, 255))
    draw.text((W - 390, footer_y), "KUALA LUMPUR TIME (GMT+8)   -   STORE PRICING IN MYR (RM)", font=font_footer, fill=(100, 116, 139, 255))

    # Save output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    print(f"Calendar poster successfully saved to {output_path}")

if __name__ == "__main__":
    out_dir = r"C:\Users\admin\.gemini\antigravity\brain\a0cc8cea-f20e-4c77-a6bb-331d3cdb0b36"
    target = os.path.join(out_dir, "steam_weekly_radar_example.png")
    create_calendar_poster(target)
