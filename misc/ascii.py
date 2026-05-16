from __future__ import annotations

from textwrap import dedent
from typing import Sequence, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
import numpy as np
from rich.text import Text


_CODEMITRA_BANNER = dedent(
    r"""
     ______                 __          __       __ __   __
    /      \               |  \        |  \     /  \  \ |  \
   |  ▓▓▓▓▓▓\ ______   ____| ▓▓ ______ | ▓▓\   /  ▓▓\▓▓_| ▓▓_    ______   ______
   | ▓▓   \▓▓/      \ /      ▓▓/      \| ▓▓▓\ /  ▓▓▓  \   ▓▓ \  /      \ |      \
   | ▓▓     |  ▓▓▓▓▓▓\  ▓▓▓▓▓▓▓  ▓▓▓▓▓▓\ ▓▓▓▓\  ▓▓▓▓ ▓▓\▓▓▓▓▓▓ |  ▓▓▓▓▓▓\ \▓▓▓▓▓▓\
   | ▓▓   __| ▓▓  | ▓▓ ▓▓  | ▓▓ ▓▓    ▓▓ ▓▓\▓▓ ▓▓ ▓▓ ▓▓ | ▓▓ __| ▓▓   \▓▓/      ▓▓
   | ▓▓__/  \ ▓▓__/ ▓▓ ▓▓__| ▓▓ ▓▓▓▓▓▓▓▓ ▓▓ \▓▓▓| ▓▓ ▓▓ | ▓▓|  \ ▓▓     |  ▓▓▓▓▓▓▓
    \▓▓    ▓▓\▓▓    ▓▓\▓▓    ▓▓\▓▓     \ ▓▓  \▓ | ▓▓ ▓▓  \▓▓  ▓▓ ▓▓      \▓▓    ▓▓
     \▓▓▓▓▓▓  \▓▓▓▓▓▓  \▓▓▓▓▓▓▓ \▓▓▓▓▓▓▓\▓▓      \▓▓\▓▓   \▓▓▓▓ \▓▓       \▓▓▓▓▓▓▓
    """
).strip("\n")

_BLOCK_FONT_7X7: dict[str, list[str]] = {
	"A": ["0011100", "0100010", "1000001", "1111111", "1000001", "1000001", "1000001"],
	"C": ["0011111", "0100000", "1000000", "1000000", "1000000", "0100000", "0011111"],
	"D": ["1111100", "1000010", "1000001", "1000001", "1000001", "1000010", "1111100"],
	"E": ["1111111", "1000000", "1000000", "1111100", "1000000", "1000000", "1111111"],
	"I": ["1111111", "0001000", "0001000", "0001000", "0001000", "0001000", "1111111"],
	"M": ["1000001", "1100011", "1010101", "1001001", "1000001", "1000001", "1000001"],
	"O": ["0011100", "0100010", "1000001", "1000001", "1000001", "0100010", "0011100"],
	"R": ["1111100", "1000010", "1000010", "1111100", "1001000", "1000100", "1000010"],
	"T": ["1111111", "0001000", "0001000", "0001000", "0001000", "0001000", "0001000"],
	" ": ["0000", "0000", "0000", "0000", "0000", "0000", "0000"],
}


def generate_ascii_art(image_path: str, size: Tuple[int, int] = (40, 40), chars: Sequence[str] | None = None) -> str:
	"""Return an ASCII-art string generated from the image at `image_path`.

	Args:
		image_path: Path to the source image file.
		size: (width, height) tuple to resize the image to.
		chars: Sequence of characters from lightest to darkest.
	"""
	if chars is None:
		chars = [" ", "░", "▒", "▓", "█"]

	img = Image.open(image_path).convert("L").resize(size)
	pixels = np.array(img)

	# Map 0-255 to indices 0..len(chars)-1 safely
	max_index = len(chars) - 1
	lines = []
	for row in pixels:
		line_chars = []
		for p in row:
			idx = (int(p) * max_index) // 255
			line_chars.append(chars[idx])
		lines.append("".join(line_chars))

	return "\n".join(lines)


def generate_codemitra_banner_art() -> Text:
	"""Return the fixed CodeMitra startup banner supplied for the CLI."""
	return Text(_CODEMITRA_BANNER, style="bold #87ceeb", no_wrap=True)


def generate_color_block_art(
	image_path: str,
	size: Tuple[int, int] = (72, 36),
	bg_threshold: int = 40,
	light_bg: bool = False,
) -> Text:
	"""Return a Rich Text object of colored █ blocks from an image.

	Args:
		image_path: Path to the source image (any PIL-supported format, including GIF).
		size: (width, height) in character cells.
		bg_threshold: Brightness threshold for background detection.
		light_bg: If True, treat bright pixels as background (for white-bg images).
		           If False, treat dark/transparent pixels as background (for dark-bg images).
	"""
	img = Image.open(image_path)
	# For animated GIFs, use the first frame
	img.seek(0)
	img = img.convert("RGBA").resize(size, Image.LANCZOS)
	pixels = np.array(img)

	text = Text(no_wrap=True)
	for i, row in enumerate(pixels):
		if i > 0:
			text.append("\n")
		for r, g, b, a in row:
			brightness = int(r) + int(g) + int(b)
			if light_bg:
				is_bg = brightness > (765 - bg_threshold)
			else:
				is_bg = a < 64 or brightness < bg_threshold
			if is_bg:
				text.append(" ")
			else:
				text.append("█", style=f"rgb({r},{g},{b})")
	return text


def generate_halfblock_art(
	image_path: str,
	size: Tuple[int, int] = (80, 40),
	white_bg: bool = True,
	warm_tint: bool = True,
	contrast: float = 2.2,
	blur_radius: float = 0.9,
	bg_threshold: int = 210,
) -> Text:
	"""Double-resolution terminal art using ▀ half-block characters.

	Pipeline:
	  1. Load → grayscale (consistent single channel, no RGB noise)
	  2. Gentle Gaussian blur → smooths noise, fills small branch gaps
	  3. Contrast boost → crisp dark monkey on bright white background
	  4. Morphological opening (MaxFilter→MinFilter) → erases thin isolated
	     arm/finger artifacts (the "Hi" shapes) while preserving wider body
	  5. Map each grayscale value through a warm brown colormap
	  6. Render top/bottom pixel pairs as ▀ half-blocks (2× vertical resolution)
	"""
	img = Image.open(image_path)
	try:
		img.seek(0)  # first GIF frame
	except (AttributeError, EOFError):
		pass

	w, h = size
	pixel_h = h * 2

	# Alpha channel for transparency detection (GIFs without alpha = all 255)
	alpha_arr = np.array(img.convert("RGBA").resize((w, pixel_h), Image.LANCZOS))[:, :, 3]

	# --- Step 1-4: grayscale pipeline ---
	img_gray = img.convert("L").resize((w, pixel_h), Image.LANCZOS)

	# Step 2: blur — smooths noise AND fills gaps in the branch
	if blur_radius > 0:
		img_gray = img_gray.filter(ImageFilter.GaussianBlur(radius=blur_radius))

	# Step 3: contrast boost (darken monkey, push background to white)
	if contrast != 1.0:
		img_gray = ImageEnhance.Contrast(img_gray).enhance(contrast)

	# Step 4: morphological opening on dark-on-light image:
	#   MaxFilter = erode dark features (thin 1-2px "Hi" artifacts vanish)
	#   MinFilter = dilate dark back (wider monkey body restored)
	img_gray = img_gray.filter(ImageFilter.MaxFilter(3))
	img_gray = img_gray.filter(ImageFilter.MinFilter(3))

	gray = np.array(img_gray, dtype=np.int32)

	# --- Step 5: warm brown colormap ---
	def tint(v: int) -> tuple[int, int, int]:
		"""Grayscale 0-255 → warm monkey-brown. Dark=deep espresso, mid=warm tan."""
		r = min(255, int(v * 1.05))
		g = min(255, int(v * 0.60))
		b = min(255, int(v * 0.20))
		return r, g, b

	def is_bg(v: int, a: int) -> bool:
		if white_bg:
			return v > bg_threshold
		return a < 64 or v < 45

	# --- Step 6: render ▀ half-blocks ---
	text = Text(no_wrap=True)
	for row in range(h):
		if row > 0:
			text.append("\n")
		top_y = row * 2
		bot_y = top_y + 1

		for col in range(w):
			tv, ta = int(gray[top_y, col]), int(alpha_arr[top_y, col])
			bv, ba = int(gray[bot_y, col]), int(alpha_arr[bot_y, col])

			top_bg = is_bg(tv, ta)
			bot_bg = is_bg(bv, ba)

			if top_bg and bot_bg:
				text.append(" ")
			elif top_bg:
				br, bg_, bb = tint(bv) if warm_tint else (bv, bv, bv)
				text.append("▄", style=f"rgb({br},{bg_},{bb})")
			elif bot_bg:
				tr, tg, tb = tint(tv) if warm_tint else (tv, tv, tv)
				text.append("▀", style=f"rgb({tr},{tg},{tb})")
			else:
				tr, tg, tb = tint(tv) if warm_tint else (tv, tv, tv)
				br, bg_, bb = tint(bv) if warm_tint else (bv, bv, bv)
				text.append("▀", style=f"rgb({tr},{tg},{tb}) on rgb({br},{bg_},{bb})")

	return text


def generate_title_art(
	text: str = "CodeMitra",
	cols: int = 96,
	rows: int = 9,
	font_path: str = "C:/Windows/Fonts/consolab.ttf",
	font_size: int = 80,
) -> Text:
	"""Render `text` as a crisp block-wordmark with gradient and subtle shadow."""
	lines = [line.strip().upper() for line in text.splitlines() if line.strip()] or [text.upper()]

	def build_bitmap_line(line: str) -> np.ndarray:
		glyphs = [_BLOCK_FONT_7X7.get(ch, _BLOCK_FONT_7X7[" "]) for ch in line]
		row_bits: list[list[int]] = []
		for row_idx in range(7):
			parts: list[str] = []
			for glyph_idx, glyph in enumerate(glyphs):
				parts.append(glyph[row_idx])
				if glyph_idx < len(glyphs) - 1:
					parts.append("0")
			row_bits.append([1 if ch == "1" else 0 for ch in "".join(parts)])
		return np.array(row_bits, dtype=np.uint8)

	bitmap_lines = [build_bitmap_line(line) for line in lines]
	if not bitmap_lines:
		bitmap_lines = [np.zeros((1, 1), dtype=np.uint8)]

	line_height = bitmap_lines[0].shape[0]
	line_gap = 1 if len(bitmap_lines) > 1 else 0
	source_height = line_height * len(bitmap_lines) + line_gap * (len(bitmap_lines) - 1)
	source_width = max(line.shape[1] for line in bitmap_lines)

	source = np.zeros((source_height, source_width), dtype=np.uint8)
	cursor_y = 0
	for line in bitmap_lines:
		offset_x = max((source_width - line.shape[1]) // 2, 0)
		source[cursor_y:cursor_y + line.shape[0], offset_x:offset_x + line.shape[1]] = line
		cursor_y += line.shape[0] + line_gap

	scale = min(cols / max(source_width, 1), rows / max(source_height, 1), 2.0)
	target_width = max(1, int(round(source_width * scale)))
	target_height = max(1, int(round(source_height * scale)))
	if (target_width, target_height) != (source_width, source_height):
		mask = Image.fromarray(source * 255, mode="L").resize((target_width, target_height), Image.NEAREST)
		source = (np.array(mask, dtype=np.uint8) >= 127).astype(np.uint8)

	alpha = np.zeros((rows, cols), dtype=np.uint8)
	pad_x = max((cols - source.shape[1]) // 2, 0)
	pad_y = max((rows - source.shape[0]) // 2, 0)
	alpha[pad_y:pad_y + source.shape[0], pad_x:pad_x + source.shape[1]] = source * 255

	shadow = np.zeros_like(alpha)
	shadow_dx = 1
	shadow_dy = 1
	if rows > shadow_dy and cols > shadow_dx:
		shadow[shadow_dy:, shadow_dx:] = alpha[:-shadow_dy, :-shadow_dx]
		shadow = np.where(alpha > 0, 0, shadow)

	out = Text(no_wrap=True)

	def gradient_rgb(col: int) -> tuple[int, int, int]:
		t = col / max(cols - 1, 1)
		if t < 0.5:
			u = t * 2
			r = int(255 * (1 - u) + 255 * u)
			g = int(214 * (1 - u) + 124 * u)
			b = int(102 * (1 - u) + 67 * u)
		else:
			u = (t - 0.5) * 2
			r = int(255 * (1 - u) + 196 * u)
			g = int(124 * (1 - u) + 90 * u)
			b = int(67 * (1 - u) + 255 * u)
		return r, g, b

	for row in range(rows):
		if row > 0:
			out.append("\n")
		for col in range(cols):
			if alpha[row, col] >= 127:
				r, g, b = gradient_rgb(col)
				out.append("█", style=f"bold rgb({r},{g},{b})")
			elif shadow[row, col] >= 127:
				out.append("▓", style="rgb(42,18,62)")
			else:
				out.append(" ")
	return out


def generate_robot_art(size: Tuple[int, int] = (56, 32)) -> Text:
	"""Draw a premium cute robot as ▀ half-block terminal art.

	Fully procedural — no external image. Drawn at 5× scale then downscaled
	for smooth circles, gradients and specular highlights.
	"""
	w, h = size
	pw, ph = w, h * 2          # pixel canvas: 56 × 64
	scale = 5
	cw, ch = pw * scale, ph * scale

	# ── Palette ──────────────────────────────────────────────────────────────
	BG        = (8,   10,  20)
	B_MID     = (72,  108, 170)   # main steel-blue
	B_LT      = (105, 148, 205)   # highlight blue
	B_XLT     = (138, 182, 230)   # bright specular band
	B_DK      = (44,   68, 128)   # shadow blue
	B_XDK     = (28,   44,  95)   # deep shadow / panel rim
	CHROME    = (210, 220, 235)
	CHROME_DK = (155, 168, 190)
	EYE_RIM   = (50,   80, 140)   # dark socket ring
	EYE_W     = (228, 242, 255)   # sclera
	IRIS_RIM  = (0,   165, 225)   # outer iris ring
	IRIS      = (15,  210, 255)   # cyan iris fill
	IRIS_LT   = (120, 235, 255)   # iris bright spot
	PUPIL     = (6,    8,  22)
	GLEAM     = (255, 255, 255)
	GLEAM2    = (195, 235, 255)   # secondary soft gleam
	PANEL_BG  = (16,  28,  62)
	SCREEN    = (55,  185, 250)
	SCREEN_LT = (130, 220, 255)
	LED_R     = (235,  52,  52)
	LED_Y     = (238, 200,  32)
	LED_G     = (48,  228,  88)
	SMILE     = (30,   52, 112)
	BLUSH     = (160, 100, 175)
	NECK_C    = (52,   78, 138)

	img = Image.new("RGB", (cw, ch), BG)
	d = ImageDraw.Draw(img)

	def s(v: float) -> int:
		return max(0, int(round(v * scale)))

	def rr(x1: float, y1: float, x2: float, y2: float, rad: float, fill: tuple) -> None:
		d.rounded_rectangle([s(x1), s(y1), s(x2), s(y2)], radius=s(rad), fill=fill)

	def el(cx_: float, cy_: float, rx: float, ry: float, fill: tuple) -> None:
		d.ellipse([s(cx_ - rx), s(cy_ - ry), s(cx_ + rx), s(cy_ + ry)], fill=fill)

	def shaded_rect(x1: float, y1: float, x2: float, y2: float, rad: float) -> None:
		"""Rounded rect with 3-tone shading: shadow border → mid body → top highlight."""
		# Guard against degenerate rects (e.g. very short feet at canvas bottom)
		if x2 - x1 < rad * 2 + 1 or y2 - y1 < rad * 2 + 1:
			rr(x1, y1, x2, y2, min(rad, (min(x2-x1, y2-y1)) / 2 - 0.5), B_MID)
			return
		rr(x1,     y1,     x2,     y2,     rad,       B_XDK)   # shadow rim
		rr(x1+0.8, y1+0.8, x2-0.8, y2-0.8, rad-0.4,  B_DK)    # dark body
		rr(x1+1.5, y1+1.5, x2-1.5, y2-1.5, rad-0.8,  B_MID)   # mid body
		# top specular band (top 30%)
		band_h = (y2 - y1) * 0.30
		rr(x1+2.5, y1+2,   x2-2.5, y1+band_h, rad*0.4, B_LT)
		# left specular strip
		d.line([(s(x1+2.5), s(y1+rad+2)), (s(x1+2.5), s(y2-rad-2))], fill=B_LT, width=max(1, s(0.6)))

	cx = pw / 2  # 28.0

	# ── Antenna ──────────────────────────────────────────────────────────────
	# Stem
	d.line([(s(cx), s(3.5)), (s(cx), s(9.5))], fill=NECK_C, width=s(1.0))
	# Cross shape
	d.line([(s(cx-2.8), s(2.5)), (s(cx+2.8), s(2.5))], fill=IRIS,    width=s(1.2))
	d.line([(s(cx),     s(0.3)), (s(cx),     s(4.7))], fill=IRIS,    width=s(1.2))
	# Center glowing ball
	el(cx, 2.5, 1.8, 1.8, IRIS)
	el(cx, 2.5, 1.0, 1.0, IRIS_LT)
	el(cx+0.4, 1.8, 0.5, 0.5, GLEAM)   # gleam

	# ── Head ─────────────────────────────────────────────────────────────────
	hx1, hy1, hx2, hy2 = cx-14, 9.5, cx+14, 25
	shaded_rect(hx1, hy1, hx2, hy2, 4.0)
	# Extra bright specular in top-left corner
	el(hx1+5, hy1+3.5, 3.5, 1.5, B_XLT)

	# ── Eyes ─────────────────────────────────────────────────────────────────
	for ex in [cx - 7.5, cx + 7.5]:
		ey = 16.5
		# dark recessed socket
		el(ex, ey, 5.5, 5.5, EYE_RIM)
		# sclera white
		el(ex, ey, 4.8, 4.8, EYE_W)
		# outer iris ring (darker cyan border)
		el(ex, ey, 3.5, 3.5, IRIS_RIM)
		# main iris fill
		el(ex, ey, 2.8, 2.8, IRIS)
		# inner iris bright spot (off-center top)
		el(ex, ey-0.8, 1.6, 1.6, IRIS_LT)
		# pupil
		el(ex, ey, 1.2, 1.2, PUPIL)
		# primary gleam (top-right)
		el(ex+1.3, ey-2.8, 1.0, 0.8, GLEAM)
		# secondary soft gleam (bottom-left)
		el(ex-2.0, ey+1.8, 0.8, 0.6, GLEAM2)

	# ── Cheek blush ──────────────────────────────────────────────────────────
	el(cx-11.5, 22.0, 2.8, 1.1, BLUSH)
	el(cx+11.5, 22.0, 2.8, 1.1, BLUSH)

	# ── Smile ────────────────────────────────────────────────────────────────
	d.arc(
		[s(cx-4.5), s(21.5), s(cx+4.5), s(26.0)],
		start=10, end=170, fill=SMILE, width=max(2, s(0.9)),
	)

	# ── Neck ─────────────────────────────────────────────────────────────────
	rr(cx-2.5, hy2, cx+2.5, hy2+3.5, 1.0, B_XDK)
	rr(cx-1.8, hy2, cx+1.8, hy2+3.5, 0.8, NECK_C)

	# ── Body ─────────────────────────────────────────────────────────────────
	bx1, by1, bx2, by2 = cx-15.5, hy2+3.5, cx+15.5, hy2+26
	shaded_rect(bx1, by1, bx2, by2, 4.5)
	# Extra specular on body top-left
	el(bx1+6, by1+4, 4.0, 2.0, B_XLT)

	# ── Chest panel ──────────────────────────────────────────────────────────
	cpx1, cpy1, cpx2, cpy2 = cx-9.5, by1+4.5, cx+9.5, by1+20.5
	rr(cpx1,     cpy1,     cpx2,     cpy2,     2.5, B_XDK)   # panel rim
	rr(cpx1+0.8, cpy1+0.8, cpx2-0.8, cpy2-0.8, 2.0, PANEL_BG)
	# Screen
	scr_y2 = cpy1 + 8.0
	rr(cpx1+1.5, cpy1+1.5, cpx2-1.5, scr_y2, 1.5, SCREEN)
	# Screen highlight stripe
	rr(cpx1+2.0, cpy1+2.0, cpx2-4.0, cpy1+4.0, 0.8, SCREEN_LT)
	# LEDs
	led_y = cpy2 - 4.5
	spacing = (cpx2 - cpx1 - 5.0) / 3
	for i, (col, glow) in enumerate([
		(LED_R, (255, 160, 160)),
		(LED_Y, (255, 242, 160)),
		(LED_G, (160, 255, 180)),
	]):
		lx = cpx1 + 2.5 + spacing * (i + 0.5)
		el(lx, led_y, 2.4, 2.4, col)          # LED body
		el(lx, led_y, 2.4, 2.4, col)
		d.ellipse([s(lx-2.4), s(led_y-2.4), s(lx+2.4), s(led_y+2.4)],
				  outline=(*col[:2], max(0, col[2]-60)), width=max(1, s(0.4)))
		el(lx+0.6, led_y-1.4, 0.7, 0.5, GLEAM)  # LED gleam

	# ── Arms ─────────────────────────────────────────────────────────────────
	arm_top = by1 + 2.5
	arm_bot = by2 - 4.0
	shaded_rect(bx1-7.5, arm_top, bx1+0.5, arm_bot, 2.5)
	shaded_rect(bx2-0.5, arm_top, bx2+7.5, arm_bot, 2.5)

	# ── Hands ────────────────────────────────────────────────────────────────
	for hx in [bx1-3.5, bx2+3.5]:
		hy = arm_bot + 3.5
		el(hx, hy, 4.0, 4.0, CHROME_DK)   # shadow
		el(hx, hy, 3.3, 3.3, CHROME)       # chrome ball
		el(hx+0.8, hy-2.0, 1.3, 0.9, GLEAM)  # specular

	# ── Legs ─────────────────────────────────────────────────────────────────
	ll_x, rl_x = cx-10.0, cx+2.0
	leg_y1, leg_y2 = by2, by2+12
	for lx in [ll_x, rl_x]:
		shaded_rect(lx, leg_y1, lx+8.0, leg_y2, 2.5)

	# ── Feet ─────────────────────────────────────────────────────────────────
	fy2 = min(leg_y2 + 5.5, ph - 0.5)
	for lx in [ll_x, rl_x]:
		shaded_rect(lx-2.5, leg_y2, lx+10.5, fy2, 2.8)
		# foot specular
		rr(lx-1.0, leg_y2+0.8, lx+6.0, leg_y2+2.2, 1.0, B_LT)

	# ── Downscale & render ───────────────────────────────────────────────────
	img = img.resize((pw, ph), Image.LANCZOS)
	arr = np.array(img, dtype=np.int32)

	text = Text(no_wrap=True)
	for row in range(h):
		if row > 0:
			text.append("\n")
		ty, by_ = row * 2, row * 2 + 1
		for col in range(w):
			tr, tg, tb = int(arr[ty, col, 0]), int(arr[ty, col, 1]), int(arr[ty, col, 2])
			br, bg_, bb = int(arr[by_, col, 0]), int(arr[by_, col, 1]), int(arr[by_, col, 2])
			t_bg = tr + tg + tb < 55
			b_bg = br + bg_ + bb < 55
			if t_bg and b_bg:
				text.append(" ")
			elif t_bg:
				text.append("▄", style=f"rgb({br},{bg_},{bb})")
			elif b_bg:
				text.append("▀", style=f"rgb({tr},{tg},{tb})")
			else:
				text.append("▀", style=f"rgb({tr},{tg},{tb}) on rgb({br},{bg_},{bb})")

	return text


if __name__ == "__main__":
	# quick CLI usage when run directly
	import pathlib
	default = pathlib.Path(__file__).with_name("monkey2.webp")
	if not default.exists():
		default = pathlib.Path(__file__).with_name("monkey.jpg")
	print(generate_ascii_art(str(default), size=(40, 40)))
