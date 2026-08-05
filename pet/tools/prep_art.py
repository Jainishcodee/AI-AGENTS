"""Turn a generated image into a usable pet sprite.

    python tools/prep_art.py "path\\to\\image.png" [--name happy] [--probe]

Image generators can't emit real transparency, so they hand you the character
on some background. This cuts that background away, trims the padding, and
writes a PNG the pet can draw.

Method: flood fill inward from the border. A global colour threshold would
either eat the character's dark edges or leave the glow halo behind as a
visible rectangle — filling from the outside only removes background that is
actually *connected* to the border, so a purple glow touching the cat stays
attached to the cat.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ART = Path(__file__).resolve().parent.parent / "art"


def probe(path: Path) -> None:
    im = Image.open(path)
    print(f"file : {path.name}")
    print(f"size : {im.size}   mode: {im.mode}")
    a = np.asarray(im.convert("RGB")).astype(int)
    h, w, _ = a.shape
    spots = [("top-left", a[5, 5]), ("top-right", a[5, w - 6]),
             ("bottom-left", a[h - 6, 5]), ("bottom-right", a[h - 6, w - 6]),
             ("left-mid", a[h // 2, 5]), ("right-mid", a[h // 2, w - 6])]
    for name, px in spots:
        print(f"  {name:<13} {tuple(int(v) for v in px)}")
    border = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3),
                             a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
    print(f"  border median {tuple(np.median(border, 0).astype(int))}  "
          f"spread {tuple(border.std(0).astype(int))}")


def cut_background(im: Image.Image, tol: float = 60.0,
                   feather: float = 1.0) -> Image.Image:
    """Remove the background, keeping only what's connected to the border.

    Two conditions, and both are needed:

    * **Colour** — within `tol` of the background colour, measured against one
      global estimate taken from the border. Comparing each pixel to its
      *neighbour* instead looks appealing for gradient backgrounds, but lets
      the fill drift without limit in small steps: it walks down the
      anti-aliased edge into the character and eats it. That is exactly what
      happened on the first attempt here.
    * **Connectivity** — reachable from the image border. Without this, dark
      background-coloured patches *inside* the character get punched out.

    Connectivity is also what saves the glow halo: it's far from the background
    colour, so it fails the colour test and stays attached to the character
    rather than being left behind as a visible rectangle.
    """
    from scipy import ndimage

    rgb = np.asarray(im.convert("RGB")).astype(np.float32)
    h, w, _ = rgb.shape

    border = np.concatenate([rgb[:8].reshape(-1, 3), rgb[-8:].reshape(-1, 3),
                             rgb[:, :8].reshape(-1, 3), rgb[:, -8:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    near_bg = np.linalg.norm(rgb - bg, axis=2) <= tol

    labels, n = ndimage.label(near_bg)
    if n:
        edge = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
        touching = set(int(v) for v in np.unique(edge) if v)
        is_bg = np.isin(labels, list(touching)) if touching else np.zeros_like(near_bg)
    else:
        is_bg = np.zeros_like(near_bg)

    out = im.convert("RGBA")
    mask = Image.fromarray(np.where(is_bg, 0, 255).astype(np.uint8), mode="L")
    if feather > 0:
        # Softens the staircase left on diagonal edges. More than a pixel or so
        # and the character grows a halo of its own.
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    out.putalpha(mask)
    return out


def trim(im: Image.Image, keep_alpha_above: int = 8) -> Image.Image:
    a = np.asarray(im)[:, :, 3]
    ys, xs = np.where(a > keep_alpha_above)
    if not len(ys):
        raise SystemExit("nothing left after cutting — try a lower --tol")
    return im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--name", default="idle", help="saved as art/pet_<name>.png")
    ap.add_argument("--tol", type=float, default=60.0)
    ap.add_argument("--max-size", type=int, default=512)
    ap.add_argument("--probe", action="store_true", help="inspect and exit")
    args = ap.parse_args()

    src = Path(args.image)
    if not src.is_file():
        raise SystemExit(f"no such file: {src}")

    if args.probe:
        probe(src)
        return 0

    im = Image.open(src)
    print(f"in   : {im.size[0]}x{im.size[1]}")
    cut = trim(cut_background(im, tol=args.tol))
    print(f"trim : {cut.size[0]}x{cut.size[1]}")

    if max(cut.size) > args.max_size:
        scale = args.max_size / max(cut.size)
        cut = cut.resize((round(cut.width * scale), round(cut.height * scale)),
                         Image.LANCZOS)
        print(f"scale: {cut.size[0]}x{cut.size[1]}")

    ART.mkdir(exist_ok=True)
    out = ART / f"pet_{args.name}.png"
    cut.save(out)
    opaque = (np.asarray(cut)[:, :, 3] > 128).mean()
    print(f"out  : {out}  ({opaque:.0%} of the box is solid)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
