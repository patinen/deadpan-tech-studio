from pathlib import Path

from PIL import Image, ImageDraw

for index in range(1, 13):
    image = Image.new("RGB", (160, 100), (18 + index * 5, 35, 52))
    ImageDraw.Draw(image).text((15, 38), f"DEMO {index:02d}", fill=(201, 244, 87))
    image.save(Path.cwd() / f"IMG_{4800 + index}.jpg", quality=85)

print("Generated 12 harmless JPEG fixtures.")
