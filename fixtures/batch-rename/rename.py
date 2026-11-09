from pathlib import Path

for index, path in enumerate(sorted(Path.cwd().glob("IMG_*.txt")), start=1):
    path.rename(f"trip-{index:02d}.txt")

print("Renamed matching files; notes.txt was left alone.")
