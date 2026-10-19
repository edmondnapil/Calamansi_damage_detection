"""Synthetic training scenes built from the verified calamansi leaf photos.

Every calamansi photo in the dataset shows one leaf on the same blue/purple
sheet. Real uploads show leaves on tables, in hands, on branches, together
with fruit. These helpers cut each leaf out of its sheet (the backdrop is
uniform, so a colour-distance mask is enough) and re-use it in new scenes:

  composite()     one leaf on a different background
  leaf_cluster()  several calamansi leaves of the SAME label arranged like a
                  branch, optionally in front of foliage or fruit photos

Only real calamansi leaves are used, so the label of every synthetic scene is
known (Healthy or Damaged leaves, or "calamansi leaves present" for the gate).
Shared by train_gate.py and train_model.py.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from config import IMG_SIZE
from predict import InvalidImageError, load_image


def leaf_mask(arr: np.ndarray) -> np.ndarray | None:
    """Alpha mask (0..1) of the leaf on the blue/purple photo sheet, or None.

    Uses colour, not distance from the border colour: the sheet is lit
    unevenly (shadows, dark corners), which a border-distance rule mistakes for
    leaf. The sheet is blue-dominant; leaves are green, yellow or brown (and
    white highlights are not blue-dominant either). The largest remaining
    region is the leaf, so stray objects at the photo edge are dropped.
    """
    from scipy import ndimage

    a = arr.astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    sheet = (b > r + 12) & (b > g - 5)
    leaf = ndimage.binary_opening(~sheet, iterations=2)
    labels, n = ndimage.label(leaf)
    if n == 0:
        return None
    sizes = ndimage.sum(leaf, labels, range(1, n + 1))
    leaf = ndimage.binary_fill_holes(labels == (int(np.argmax(sizes)) + 1))
    if not 0.01 < leaf.mean() < 0.7:
        return None
    soft = Image.fromarray(leaf.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(1))
    return np.asarray(soft, dtype=np.float32) / 255


def plain_leaf_mask(arr: np.ndarray) -> np.ndarray | None:
    """Alpha mask of a leaf photographed on plain paper (white/grey) or cut out onto black,
    as in the public lemon and orange leaf datasets. Paper is bright and almost colourless,
    a removed background is near black; the largest remaining region is the leaf."""
    from scipy import ndimage

    a = arr.astype(np.float32) / 255
    mx, mn = a.max(-1), a.min(-1)
    sat = (mx - mn) / (mx + 1e-6)
    r, g, bl = a[..., 0], a[..., 1], a[..., 2]
    # paper: bright and colourless, or bright and at least as blue as green (bluish-white paper);
    # leaves are green, yellow or brown, i.e. greener than blue
    background = ((mx > 0.45) & ((sat < 0.16) | (bl >= g - 0.01))) | (mx < 0.12)
    leaf = ndimage.binary_opening(~background, iterations=2)
    labels, n = ndimage.label(leaf)
    if n == 0:
        return None
    sizes = ndimage.sum(leaf, labels, range(1, n + 1))
    leaf = ndimage.binary_fill_holes(labels == (int(np.argmax(sizes)) + 1))
    if not 0.02 < leaf.mean() < 0.85:
        return None
    soft = Image.fromarray(leaf.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(1))
    return np.asarray(soft, dtype=np.float32) / 255


def region_crop(img: Image.Image, rng: random.Random) -> Image.Image:
    """A square window of 50-70% of the short side, like the app's region analysis looks at."""
    side = int(min(img.size) * rng.uniform(0.5, 0.7))
    x, y = rng.randint(0, img.width - side), rng.randint(0, img.height - side)
    return img.crop((x, y, x + side, y + side)).resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)


def cutout(arr: np.ndarray, mask_fn=None) -> Image.Image | None:
    """The leaf as an RGBA image cropped to its outline, or None."""
    alpha = (mask_fn or leaf_mask)(arr)
    if alpha is None:
        return None
    leaf = Image.fromarray(arr).convert("RGBA")
    leaf.putalpha(Image.fromarray((alpha * 255).astype(np.uint8)))
    return leaf.crop(leaf.getbbox())


def random_background(rng: random.Random, bg_pool: list[Path], size: int = IMG_SIZE) -> Image.Image:
    kind = rng.random()
    if kind < 0.45 and bg_pool:
        try:
            img = Image.fromarray(load_image(rng.choice(bg_pool), size))
            return img.filter(ImageFilter.GaussianBlur(rng.uniform(0, 2)))
        except InvalidImageError:
            pass
    if kind < 0.6:  # white / near-white studio or paper background (common in real photos)
        v = rng.randint(225, 255)
        arr = np.full((size, size, 3), v, dtype=np.float32) + np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, 2, (size, size, 3))
    elif kind < 0.85:  # solid / two-tone surface (table, paper, cloth)
        c1 = tuple(rng.randint(0, 255) for _ in range(3))
        c2 = tuple(min(255, max(0, v + rng.randint(-40, 40))) for v in c1)
        grad = np.linspace(0, 1, size)[None, :, None] if rng.random() < 0.5 else np.linspace(0, 1, size)[:, None, None]
        arr = np.array(c1)[None, None] * (1 - grad) + np.array(c2)[None, None] * grad
        arr = np.broadcast_to(arr, (size, size, 3))
    else:  # noisy texture (soil, wood grain-ish)
        base = np.array([rng.randint(40, 200) for _ in range(3)], dtype=np.float32)
        arr = base + np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, 25, (size, size, 3))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def augment(img: Image.Image, rng: random.Random) -> Image.Image:
    if rng.random() < 0.5:
        img = ImageOps.mirror(img)
    img = img.rotate(rng.choice([0, 90, 180, 270]) + rng.uniform(-20, 20), resample=Image.Resampling.BILINEAR,
                     fillcolor=tuple(int(v) for v in np.asarray(img)[0, 0]))
    s = rng.uniform(0.75, 1.0)
    w = int(IMG_SIZE * s)
    x, y = rng.randint(0, IMG_SIZE - w), rng.randint(0, IMG_SIZE - w)
    img = img.crop((x, y, x + w, y + w)).resize((IMG_SIZE, IMG_SIZE))
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.7, 1.3))
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.75, 1.25))
    return ImageEnhance.Color(img).enhance(rng.uniform(0.8, 1.2))


def composite(arr: np.ndarray, rng: random.Random, bg_pool: list[Path], mask_fn=None) -> Image.Image | None:
    """Cut the leaf out of its backdrop and paste it on a different background."""
    leaf = cutout(arr, mask_fn)
    if leaf is None:
        return None
    scale = rng.uniform(0.7, 1.5)
    leaf = leaf.resize((max(8, int(leaf.width * scale)), max(8, int(leaf.height * scale))))
    leaf = leaf.rotate(rng.uniform(0, 360), expand=True, resample=Image.Resampling.BILINEAR)
    if leaf.width > IMG_SIZE or leaf.height > IMG_SIZE:
        leaf.thumbnail((IMG_SIZE, IMG_SIZE))
    bg = random_background(rng, bg_pool).convert("RGBA")
    bg.alpha_composite(leaf, (rng.randint(0, IMG_SIZE - leaf.width), rng.randint(0, IMG_SIZE - leaf.height)))
    return ImageEnhance.Brightness(bg.convert("RGB")).enhance(rng.uniform(0.8, 1.2))


def leaf_cluster(arrs: list[np.ndarray], rng: random.Random, bg_pool: list[Path]) -> Image.Image | None:
    """Several calamansi leaves (same label) arranged along a stem, like a branch photo.

    Leaves are attached at points along a curved stem, overlap each other and
    point outwards, as on a real calamansi twig. Backgrounds include white,
    plain surfaces and real photos (foliage, flowers, objects, citrus fruit), so
    fruit or greenery next to calamansi leaves does not count against them.
    """
    leaves = [c for c in (cutout(a) for a in arrs) if c is not None]
    if len(leaves) < 2:
        return None
    canvas_size = IMG_SIZE * 2  # draw large, then downscale (smoother edges)
    bg = random_background(rng, bg_pool, canvas_size).convert("RGBA")
    draw = ImageDraw.Draw(bg)
    # curved stem across the frame
    x0, y0 = rng.uniform(0.15, 0.85) * canvas_size, canvas_size * rng.uniform(0.85, 1.05)
    x1, y1 = rng.uniform(0.2, 0.8) * canvas_size, canvas_size * rng.uniform(-0.05, 0.2)
    bend = rng.uniform(-0.25, 0.25) * canvas_size
    pts = [(x0 + (x1 - x0) * t + bend * 4 * t * (1 - t), y0 + (y1 - y0) * t) for t in np.linspace(0, 1, 30)]
    stem_colour = (rng.randint(70, 120), rng.randint(110, 160), rng.randint(40, 80), 255)
    draw.line(pts, fill=stem_colour, width=max(3, int(canvas_size * rng.uniform(0.008, 0.016))))
    order = list(range(len(leaves)))
    rng.shuffle(order)
    for k, i in enumerate(order):
        leaf = leaves[i]
        target = canvas_size * rng.uniform(0.28, 0.48)  # leaf length relative to the frame
        scale = target / max(leaf.size)
        leaf = leaf.resize((max(8, int(leaf.width * scale)), max(8, int(leaf.height * scale))))
        t = (k + rng.uniform(0.2, 0.8)) / len(leaves)
        px, py = pts[min(len(pts) - 1, int(t * (len(pts) - 1)))]
        angle = rng.choice([-1, 1]) * rng.uniform(25, 80) + rng.uniform(-15, 15)
        leaf = leaf.rotate(angle, expand=True, resample=Image.Resampling.BILINEAR)
        ox = int(px - leaf.width / 2 + rng.uniform(-0.25, 0.25) * leaf.width)
        oy = int(py - leaf.height / 2 + rng.uniform(-0.25, 0.25) * leaf.height)
        layer = Image.new("RGBA", bg.size)
        layer.paste(leaf, (ox, oy), leaf)
        bg = Image.alpha_composite(bg, layer)
    img = bg.convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.Resampling.LANCZOS)
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.8, 1.2))
    return ImageEnhance.Color(img).enhance(rng.uniform(0.85, 1.15))
