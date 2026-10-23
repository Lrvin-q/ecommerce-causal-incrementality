from PIL import Image
import pathlib
for p in sorted(pathlib.Path("outputs/figures/paper").glob("*.png")):
    try:
        im = Image.open(p); im.load()
        print(p.name, im.size, "OK")
    except Exception as e:
        print(p.name, "FAIL", e)
