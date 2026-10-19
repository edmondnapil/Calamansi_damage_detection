"""Round 2 of the species fix in train_gate.py (see the comments it inserts)."""
import sys

p = sys.argv[1]
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:90])
    s = s.replace(a, b)


# ---------------------------------------------------------------- imports, splits, iNat sources
rep('''from composites import augment, composite, leaf_cluster, leaf_mask, random_background''',
    '''from composites import augment, composite, leaf_cluster, leaf_mask, plain_leaf_mask, random_background, region_crop''')
rep('''from predict import GATE_EXTRACTOR_PATH, GATE_PATH, InvalidImageError, load_image''',
    '''from predict import GATE_EXTRACTOR_PATH, GATE_PATH, InvalidImageError, load_image, open_image, sharpness''')
rep('''def split_of(key: str) -> str:
    """Deterministic 70/15/15 split from a stable hash of the file path."""
    h = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100
    return "train" if h < 70 else "val" if h < 85 else "test"''',
    '''def split_of(key: str) -> str:
    """Deterministic 70/15/15 split from a stable hash of the file path / group.

    Real iNaturalist photos ("inat_..." keys, one group per observation) are split 50/15/35,
    so a larger share of these scarce real-world photos stays held out for testing."""
    h = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100
    if key.startswith("inat_"):
        return "train" if h < 50 else "val" if h < 65 else "test"
    return "train" if h < 70 else "val" if h < 85 else "test"


INAT_DIR = OOD_DIR / "inat"
INAT_OTHER_CITRUS = ("lemon", "key_lime", "persian_lime", "makrut_lime", "orange")


def inat_calamansi() -> list[tuple[Path, str]]:
    """Real calamansi photos from iNaturalist whose leaves are clearly visible (manual review,
    ood_data/inat/calamansi_labels.csv) -> [(path, split)]. Photos without clear leaves are
    not used: fruit or flowers alone must not teach the check that they are calamansi leaves."""
    lab = INAT_DIR / "calamansi_labels.csv"
    if not lab.exists():
        return []
    rows = list(csv.DictReader(open(lab, encoding="utf-8")))
    return [(INAT_DIR / r["file"], split_of(f"inat_calamansi/{Path(r['file']).stem}"))
            for r in rows if r["leaves"] == "yes" and (INAT_DIR / r["file"]).exists()]''')
rep('''    take("orange_leaves_hlb", [(p, groups[p]) for p in orange_h[:500] + orange_d[:500]], 1000)
    return out''', '''    take("orange_leaves_hlb", [(p, groups[p]) for p in orange_h[:500] + orange_d[:500]], 1000)
    # Real photos of other citrus plants (lemon, limes, orange) from iNaturalist, one per observation.
    # The category name starts with "inat_" so these use the 50/15/35 split (see split_of).
    inat = [(p, f"{sp}/{p.stem}") for sp in INAT_OTHER_CITRUS for p in sorted((INAT_DIR / sp).glob("*.jpg"))]
    take("inat_other_citrus", inat, 2000)
    return out''')

# ---------------------------------------------------------------- positives: real calamansi photos
rep('''    train_var, val_var, test_var = feats(train_var_img), feats(val_var_img), feats(test_var_img)
''', '''    train_var, val_var, test_var = feats(train_var_img), feats(val_var_img), feats(test_var_img)

    # Real calamansi plant photos (iNaturalist, leaves clearly visible): the dataset only has single
    # leaves on a sheet, so without these the check rejects most real photos of calamansi plants.
    inat_pos = {s: [p for p, sp in inat_calamansi() if sp == s] for s in ("train", "val", "test")}
    print("iNaturalist calamansi photos (train/val/test):", {s: len(v) for s, v in inat_pos.items()}, flush=True)
    r_inat = random.Random(SEED + 40)
    inat_train_img = load_all(inat_pos["train"])
    inat_var_img = np.stack([np.asarray(augment(Image.fromarray(a), r_inat)) for a in inat_train_img for _ in range(4)] +
                            [np.asarray(region_crop(open_image(p), r_inat)) for p in inat_pos["train"] for _ in range(2)])
    inat_val_img = load_all(inat_pos["val"])
    inat_train_feat, inat_val_feat = feats(np.concatenate([inat_train_img, inat_var_img])), feats(inat_val_img)

    # Region-analysis-like crops of the calamansi photos (the app also classifies crops).
    r_crop = random.Random(SEED + 41)
    pos_crop_img = np.stack([np.asarray(region_crop(open_image(p), r_crop)) for p in pos["train"]])
    pos_crop_feat = feats(pos_crop_img)

    # The same treatment for the most similar negatives: lemon/orange leaves cut out and pasted on
    # new backgrounds (incl. plain white, like stock photos), and zoomed-in crops of them, so neither
    # the background nor a close-up can make another citrus leaf look like calamansi.
    def citrus_variants(split: str, seed: int) -> np.ndarray:
        r = random.Random(seed)
        out = []
        for c in ("lemon_leaves", "orange_leaves_hlb", "inat_other_citrus"):
            for path in neg_split.get(c, {}).get(split, []):
                try:
                    img = open_image(path)
                except Exception:  # noqa: BLE001 - unreadable file
                    continue
                out.append(np.asarray(region_crop(img, r)))
                if c != "inat_other_citrus":
                    comp = composite(load_image(path), r, bg_pool, plain_leaf_mask)
                    if comp is not None:
                        out.append(np.asarray(augment(comp, r)))
        return np.stack(out) if out else np.zeros((0, IMG_SIZE, IMG_SIZE, 3), np.uint8)

    print("Building cut-out / close-up variants of other citrus leaves...", flush=True)
    citrus_var = {s: citrus_variants(s, SEED + 50 + i) for i, s in enumerate(("train", "val", "test"))}
''')
rep('''    N["empty_backgrounds"] = {split: feats(imgs) for split, imgs in empty.items()}
    train_pos = np.concatenate([P["train"], train_var])
    val_pos_all = np.concatenate([P["val"], val_var])''', '''    N["empty_backgrounds"] = {split: feats(imgs) for split, imgs in empty.items()}
    N["citrus_leaf_variants"] = {split: feats(imgs) for split, imgs in citrus_var.items()}
    train_pos = np.concatenate([P["train"], train_var, pos_crop_feat, inat_train_feat])
    val_pos_all = np.concatenate([P["val"], val_var, inat_val_feat])''')

# ---------------------------------------------------------------- CNN data and category-balanced weights
rep('''    pos_w = np.r_[[3.0 if lab == "Damaged" else 1.5 for lab in pos_labels["train"]],
                  np.full(len(damaged_aug), 2.0), np.ones(2800)].astype(np.float32)''', '''    pos_w = np.r_[[3.0 if lab == "Damaged" else 1.5 for lab in pos_labels["train"]],
                  np.full(len(damaged_aug), 2.0), np.ones(2800)].astype(np.float32)
    # region crops of the photos, and the real calamansi plant photos (scarce, so weighted up)
    cnn_pos_train = np.concatenate([cnn_pos_train, pos_crop_img, inat_train_img, inat_var_img])
    pos_w = np.r_[pos_w, np.ones(len(pos_crop_img)), np.full(len(inat_train_img), 4.0),
                  np.full(len(inat_var_img), 2.0)].astype(np.float32)''')
rep('''    hard = ("other_citrus_leaves", "other_citrus_leaves_plantvillage", "citrus_fruits", "lemon_leaves", "orange_leaves_hlb")
    neg_paths, neg_w = [], []
    for c in trained_on:
        ps = neg_split[c]["train"]
        ps = ps if c in hard else rng.sample(ps, min(len(ps), 450))
        neg_paths += ps
        neg_w += [3.0 if c in hard else 1.0] * len(ps)
    cnn_neg_train = np.concatenate([load_all(neg_paths), empty["train"]])
    neg_w += [2.0] * len(empty["train"])''', '''    hard = ("other_citrus_leaves", "other_citrus_leaves_plantvillage", "citrus_fruits", "lemon_leaves",
            "orange_leaves_hlb", "inat_other_citrus")
    # Category-balanced weights: every category has the same total weight (hard ones twice that),
    # however many images it has, so adding many citrus images does not crowd out objects/flowers.
    neg_imgs, neg_w = [], []

    def add_neg(imgs: np.ndarray, units: float) -> None:
        if len(imgs):
            neg_imgs.append(imgs)
            neg_w.extend([units * 450.0 / len(imgs)] * len(imgs))

    for c in trained_on:
        ps = neg_split[c]["train"]
        ps = ps if c in hard else rng.sample(ps, min(len(ps), 450))
        add_neg(load_all(ps), 2.0 if c in hard else 1.0)
    add_neg(empty["train"], 1.5)
    add_neg(citrus_var["train"], 2.0)
    cnn_neg_train = np.concatenate(neg_imgs)''')
rep('''    cnn = train_cnn(cnn_pos_train, pos_w, cnn_neg_train, np.array(neg_w, np.float32),
                    np.concatenate([load_all(pos["val"]), val_var_img]),
                    np.concatenate([load_all(neg_val_paths), empty["val"]]),''', '''    cnn = train_cnn(cnn_pos_train, pos_w, cnn_neg_train, np.array(neg_w, np.float32),
                    np.concatenate([load_all(pos["val"]), val_var_img, inat_val_img]),
                    np.concatenate([load_all(neg_val_paths), empty["val"], citrus_var["val"]]),''')

# ---------------------------------------------------------------- calibration incl. real photos, sharpness
rep('''    S_var = {"val": cnn_scores(cnn, val_var_img), "test": cnn_scores(cnn, test_var_img)}''',
    '''    S_var = {"val": cnn_scores(cnn, np.concatenate([val_var_img, inat_val_img])), "test": cnn_scores(cnn, test_var_img)}''')
rep('''    S_neg["empty_backgrounds"] = {s: cnn_scores(cnn, empty[s]) for s in ("val", "test")}''',
    '''    S_neg["empty_backgrounds"] = {s: cnn_scores(cnn, empty[s]) for s in ("val", "test")}
    S_neg["citrus_leaf_variants"] = {s: cnn_scores(cnn, citrus_var[s]) for s in ("val", "test")}''')
rep('''        np.savez_compressed(GATE_PATH, **arrays, t_cnn=np.float32(t_cnn))''', '''        # Sharpness: photos too blurry to verify the species are rejected. Threshold = a quarter of
        # the 1st percentile of the validation calamansi photos (dataset + real photos), so every
        # sharp validation photo passes with a wide margin; 2-4 px blurred copies score <= 4.
        val_sharp = [sharpness(open_image(p_)) for p_ in pos["val"] + inat_pos["val"]]
        t_sharp = 0.25 * float(np.percentile(val_sharp, 1))
        print(f"Sharpness threshold: {t_sharp:.2f} (validation photos: 1st percentile {np.percentile(val_sharp, 1):.1f})", flush=True)
        np.savez_compressed(GATE_PATH, **arrays, t_cnn=np.float32(t_cnn), t_sharp=np.float32(t_sharp))''')
open(p, "w", encoding="utf-8").write(s)
print("patched")
