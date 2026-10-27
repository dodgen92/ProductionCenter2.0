from PIL import Image
from pathlib import Path

OUTPUT_FOLDER = Path(r"C:\Users\tyler\Downloads\PokemonCards")
INPUT_FOLDER = Path(r"C:\Users\tyler\Downloads\PokemonCards")

# Change these to match your sheets
COLUMNS = 4
ROWS = 4

OUTPUT_FOLDER.mkdir(exist_ok=True)

counter = 1

for image_path in sorted(INPUT_FOLDER.iterdir()):
    if image_path.suffix.lower() not in [".png", ".jpg", ".jpeg", ".webp"]:
        continue

    img = Image.open(image_path)
    width, height = img.size

    card_width = width // COLUMNS
    card_height = height // ROWS

    print(f"Processing {image_path.name} ({width}x{height})")

    for row in range(ROWS):
        for col in range(COLUMNS):
            left = col * card_width
            top = row * card_height
            right = left + card_width
            bottom = top + card_height

            card = img.crop((left, top, right, bottom))

            output_path = OUTPUT_FOLDER / f"{counter:03d}.png"
            card.save(output_path)

            counter += 1

print(f"\nDone! Created {counter - 1} cards.")