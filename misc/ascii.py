from __future__ import annotations

from typing import Sequence, Tuple

from PIL import Image
import numpy as np


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


if __name__ == "__main__":
	# quick CLI usage when run directly
	import pathlib
	default = pathlib.Path(__file__).with_name("monkey2.webp")
	if not default.exists():
		default = pathlib.Path(__file__).with_name("monkey.jpg")
	print(generate_ascii_art(str(default), size=(40, 40)))
