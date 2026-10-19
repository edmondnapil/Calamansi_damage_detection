# Training and Evaluation Results

**Web-Based Calamansi Leaf Damage Detection Using Image Classification**

Actual results of the runs on 2026-10-14/15 (CPU only, Python 3.12, TensorFlow 2.19). Raw files are in
`backend/outputs/` and `backend/models/`. Re-running the scripts reproduces the splits exactly (seed 42);
training on another machine may change the scores slightly.

## 1. Dataset correction

All **150 white-background "damaged" images** (`b--NNN-_png…`, `NN-p_png…`) are pixel-identical copies of
the public **Citrus Leaves** dataset (Rauf et al. 2019, Mendeley Data `3f83gxmv57`), which shows
orange/citrus leaves from Pakistan, not calamansi. Every one of the 150 matched a public file with
similarity ≥ 0.9999 (e.g. `b--266-_png…jpg` = `Citrus/Leaves/Black spot/b (266).png`). They are listed in
`backend/dataset_exclusions.csv` and excluded; no file was deleted.

Consequences of the old data: other citrus leaves were labelled "calamansi Damaged" (so they could never be
rejected), and "white background ⇒ Damaged" was a shortcut the model could exploit. The first model and its
metrics are kept in `backend/models/previous_v1/`.

| Split | Damaged | Healthy | Total |
|---|---|---|---|
| Train | 329 | 282 | 611 |
| Validation | 70 | 60 | 130 |
| Test (independent) | 70 | 60 | 130 |

871 genuine calamansi photos; stratified 70/15/15 group split (burst-shot near-duplicates kept together).

## 2. Healthy / Damaged classifier (MobileNetV2, retrained on the corrected data)

Model `mobilenetv2-20261014-1508`; 24 epochs (early stopping), 10.2 min. MobileNetV2 was chosen in the
earlier comparison with EfficientNetB0 (same validation accuracy, lower loss, smaller, faster), so only
MobileNetV2 was retrained this time.

**Independent test set (130 images):**

| Class | Precision | Recall | F1-score | Support |
|---|---|---|---|---|
| Damaged | 95.71% | 95.71% | 95.71% | 70 |
| Healthy | 95.00% | 95.00% | 95.00% | 60 |
| **Accuracy** | | | **95.38%** | 130 |

ROC AUC 0.9824. Confusion matrix (rows actual, columns predicted): Damaged → 67 / 3, Healthy → 3 / 57.

| | Accuracy |
|---|---|
| Train (no augmentation) | 94.44% |
| Validation | 95.38% |
| Test | 95.38% |

No overfitting gap. The previous model reached 93.46% on a test set that included the copied citrus images
(and 91.87% on its blue-background photos), so the corrected model is both cleaner and more accurate on
genuine calamansi photos.

`outputs/label_review_train.csv` lists 10 photos where the model strongly disagrees with the label (e.g.
`test/healthy/20220405_111616…jpg`, a "Healthy" leaf with visible dark spots). These should be checked by
someone who knows calamansi leaves.

## 3. Calamansi-leaf check (rejecting non-calamansi images)

**Root cause of the old behaviour:** the classifier has one sigmoid output, P(Healthy), and was trained only
on calamansi leaves, so every image, including faces and screenshots, was forced into Healthy or Damaged.
(The live Supabase log still contains two such records from before the fix: `OIP.webp` and
`Screenshot 2026-10-01 220655.png`, both labelled Damaged.)

**Method (`train_gate.py`):** an image is accepted only if all checks pass:
1. logistic regression on frozen ImageNet MobileNetV2 features (calamansi vs. negatives);
2. novelty check: distance to the nearest calamansi training example;
3. a MobileNetV2 fine-tuned end to end on calamansi vs. negatives (other-citrus images weighted ×3).

Negatives (public datasets, `download_ood_data.py`): Citrus Leaves (leaves and fruit), PlantVillage
(37 crop-leaf classes + orange/citrus leaves + background), TF Flowers, Imagenette, Caltech-101, LFW faces.
Calamansi leaves are also cut out and pasted on new backgrounds so the check learns the leaf, not the blue
sheet. Thresholds were set on validation data to keep ≥ 98% of calamansi validation images.

**Held-out test images (never used for training or threshold selection):**

| Images | Result | Stage 1 alone |
|---|---|---|
| Calamansi test photos | **100% accepted** (130/130; 70 Damaged, 60 Healthy) | |
| Calamansi leaves pasted on new backgrounds | 97.7% accepted (260) | |
| Other citrus leaves (Citrus Leaves dataset) | **98.9% rejected** (87) | 79.3% |
| Other citrus leaves (PlantVillage orange) | 100% rejected (73) | 95.9% |
| Citrus fruits | 100% rejected (19) | 100% |
| Other plant leaves (PlantVillage) | 99.6% rejected (463) | 98.5% |
| Flowers | 100% rejected (97) | 86.6% |
| Everyday objects & animals (Imagenette) | 99.3% rejected (141) | 89.4% |
| Objects (Caltech-101) | 100% rejected (174) | 95.4% |
| People (LFW) | 100% rejected (118) | 100% |

**Generalisation to kinds of images never seen in training:** the whole check was retrained without flowers,
everyday objects and people, then tested on them: flowers 100%, everyday objects 99.3%, people 100%
rejected, with 100% of calamansi test photos still accepted (`outputs/gate_unseen_experiment.json`).

**Limitations (honest):**
* About 1 in 90 other-citrus leaves still passes. Calamansi and other citrus leaves are genuinely similar.
* All calamansi photos in the dataset show one leaf on a blue/purple sheet. Acceptance of real calamansi
  photos taken elsewhere (on the tree, on a table, other phones) has only been estimated with synthetic
  re-backgrounded images (97.7%), not measured on real field photos. Such photos may be rejected; the UI
  then advises how to retake the photo.
* No check can guarantee rejection of every possible image.

## 4. Page loading fixes (pages needing a hard refresh)

| Root cause | Effect | Fix |
|---|---|---|
| `useEffect(() => window.scrollTo(0, 0), …)` in `Layout.tsx`. Newer Chrome returns a Promise from `scrollTo`; React treated it as a cleanup function and crashed (`destroy is not a function`) | Production: the whole app went blank after the first navigation; dev: blank from the start. A hard refresh loaded the page fresh, so it "worked" until the next click | Effect body in braces (same fix for an effect in `Logs.tsx`) |
| Supabase client shared one HTTP/2 connection across FastAPI worker threads | 2–3 of every 12 concurrent requests failed with 500 (`RemoteProtocolError: Server disconnected`), so dashboard cards/charts stayed empty | HTTP/1.1 connection pool + retry on dropped connections; inserts made idempotent (client-generated id + upsert) so a retry cannot duplicate a record. 160/160 concurrent requests now succeed |
| `/api/stats` made 10 sequential Supabase round trips (3.5 s) | Dashboard numbers showed "–" for seconds | 4 parallel queries, identical results, ~0.8 s |
| Missing built file answered with `index.html`; `index.html` cacheable | After a rebuild the browser ran HTML as JavaScript, blank page | 404 for missing files, `no-cache` for `index.html`, long cache for hashed assets |
| Render-blocking Google Fonts stylesheet | Blank page until the font server answered (slow/filtered networks) | Font bundled locally |
| No error boundary | Any render error blanked the entire app | Error boundary shows the error with "Try again", sidebar stays usable |

Browser verification: 14 navigation checks (sidebar clicks, back/forward, reload, direct URL, in-page
links) pass on both the dev server and the production build; the old build failed after the first click.

## 5. Automated tests

`python -m pytest -q` (backend): **12 passed**. Covers calamansi classification and saving, rejection
(without saving) of citrus leaves, citrus fruit, other plant leaves, faces, objects, random noise and an
empty backdrop, upload validation, queries, and frontend caching/404 behaviour. Uses a temporary local
database, never Supabase.

## 6. Update 2026-10-18: branches, fruit and blank images

**Problem.** A photo of a calamansi branch with fruit was rejected: the leaf check had only seen single
leaves on the blue sheet as calamansi, while citrus fruit and citrus leaves on white were negatives. Also,
non-square photos were squashed, and the classifier misjudged leaves on other backgrounds.

**Changes.** Non-square photos are padded instead of squashed; a fixed colour-based leaf cut-out (the old
mask included pieces of the sheet) re-uses the verified calamansi leaves on new backgrounds and in
branch-like clusters, with fruit or foliage behind them; blank sheets (leaf painted out), synthetic surfaces
and noise were added as negatives; photos that are not accepted as a whole are examined in regions of at least
224 px. The classifier was retrained with the same background variety (`mobilenetv2-20261015-0651`).

**Classifier (130 held-out test photos):** accuracy **96.9%** (was 95.4%), ROC AUC 0.986. Same test leaves
on new backgrounds: **89.6%** (was 69.2%, Healthy recall 36.7% -> 90.8%); branch-like clusters **99.0%**
(was 76.5%).

**Complete pipeline, held-out test images** (`evaluate_gate.py`, `outputs/gate_evaluation.json`):

| Images | Result |
|---|---|
| Calamansi test photos | 100% accepted, 96.9% accepted and correctly classified |
| Branch-like clusters / leaves on new backgrounds | 99.5% / 91.2% accepted |
| Other citrus leaves (2 datasets) / citrus fruit | 98.9%, 100% / 100% rejected |
| Other plant leaves / flowers | 99.6% / 100% rejected |
| Objects (Imagenette / Caltech-101) / people | 95.7% / 98.9% / 99.2% rejected |
| Blank backgrounds and noise | 99.6% rejected |

Region analysis produced no false accepts in any category. Real photos (`backend/realworld_test/`,
`evaluate_realworld.py`): 6/6 correct, including the stock photo of a calamansi branch with fruit (accepted,
Healthy 99.5%) and fruit-only crops (rejected). These are only six images; a larger set of verified real
photos is still needed to measure field performance. The earlier "never seen" experiment (section 3)
was run on the previous version of the check and has not been repeated.

## 7. Update 2026-10-18: dataset images rejected as "not calamansi"

**Report.** Some images taken directly from `train/Damaged` were rejected by the app.

**Diagnosis** (`diagnose_dataset.py`: all 1,238 dataset files through the exact app pipeline, with the
whole-photo score of each check; `outputs/dataset_diagnostic.csv`):

| Folder files | n | Accepted before fix | Accepted after fix |
|---|---|---|---|
| Genuine calamansi photos, Damaged (all folders) | 469 | 468 | **469** |
| Genuine calamansi photos, Healthy (all folders) | 402 | 402 | 402 |
| Roboflow `_aug` copies (train/healthy, not used) | 217 | 217 | 217 |
| Public Citrus Leaves copies (`b--NNN-_png…`, `NN-p_png…`; 130 train, 13 valid, 7 test) | 150 | 0 | 0 |

1. **150 of the 151 rejections are not calamansi photos.** They are pixel-identical copies of the public
   Citrus Leaves dataset (orange leaves from Pakistan, section 1). They were never used as calamansi
   training images; the original dataset is a negative category. Rejecting them is correct. Median whole-photo
   scores: linear 0.02 (calamansi 0.99), CNN 0.00 (calamansi 1.00).
2. **One genuine photo was wrongly rejected:** `train/damaged/IMG_20220405_091357_jpg.rf.378b61cc…jpg`, a
   severely mined leaf. It *was* loaded in training (train split; novelty 0.0, i.e. it is in the positive bank),
   but the CNN check scored it 0.038 (threshold 0.051). Removing the red object in the photo did not help;
   the leaf itself caused it.

**Root cause (component: CNN stage of the calamansi-leaf check, `train_gate.py`).** All low CNN scores of
genuine photos were Damaged leaves (8 Damaged below 0.5, no Healthy below 0.79). The negatives contain many
diseased leaves (citrus canker / black spot, PlantVillage diseases) and other citrus was weighted x3, while
damaged calamansi leaves had no matching weight. The check partly learned "visible damage = not calamansi".
Its threshold was calibrated on all validation images pooled, so nothing guaranteed damaged photos were kept.

**Fix (gate retrained, classifier unchanged).** Damaged training photos weighted x3 plus two augmented copies
each; the CNN threshold must now keep >= 98% of validation photos of *each* class (calibrated on validation,
not lowered by hand; it actually rose from 0.051 to 0.081). Lowest CNN score of a genuine Damaged photo:
0.038 -> **0.71**; no genuine photo below 0.5. Previous gate kept in `backend/models/previous_gate_v2/`.

**Held-out test images, complete pipeline (`evaluate_gate.py`), before -> after:**

| Images | Before | After |
|---|---|---|
| Calamansi test photos accepted (Damaged / Healthy) | 100% / 100% | 100% / 100% |
| Accepted and correctly classified | 96.9% | 96.9% |
| Leaves on new backgrounds / branch-like clusters | 91.2% / 99.5% | 91.5% / 99.5% |
| Other citrus leaves (2 datasets) / citrus fruit rejected | 98.9%, 100% / 100% | 98.9%, 100% / 100% |
| Other plant leaves / flowers rejected | 99.6% / 100% | 98.5% / 97.9% |
| Objects (Imagenette / Caltech) / people rejected | 95.7% / 98.9% / 99.2% | 98.6% / 97.7% / 99.2% |
| Blank backgrounds and noise rejected | 99.6% | 98.9% |

Trade-off: over all 1,442 held-out negatives, wrongly accepted images rose from 13 (0.9%) to 20 (1.4%), mostly
non-citrus plant leaves, flowers and objects; other-citrus rejection is unchanged. Real photos: still 6/6.
Backend tests: 28 passed.

## 8. Update 2026-10-19: lemon leaf accepted as a calamansi leaf

**Report.** A stock photo of a lemon leaf on white (`backend/regression_cases/lemon_leaf_user_upload.jpg`)
was classified "Healthy Leaf, 99.2%".

**Root cause.** The app already separates species from health: the calamansi-leaf check runs first and the
Healthy/Damaged classifier only on accepted images, so the 99.2% (health confidence) played no part. The
check passed the photo on all three stages, narrowly (stage-1 0.95 / threshold 0.11, novelty 0.54 / 0.63,
CNN 0.45 / 0.08), because it had never seen a lemon or lime leaf: its "other citrus" examples were mostly
diseased orange leaves, while calamansi leaves pasted on white were calamansi examples.

**New data (all CC BY 4.0, species-labelled, near-duplicates grouped so no leaf is in two splits):**
1,031 lemon leaves (BDLemonLeaf doi:10.17632/643f5bbc2t.6, raw images; Comprehensive Lemon Leaf Disease
Dataset doi:10.17632/44nrn4593f.1, original images; healthy and diseased balanced) and 453 orange leaves
(Orange Leaves HLB, Mexico, doi:10.17632/jgkh2jxbwt.1). For testing only: 1,746 iNaturalist photos of
calamansi, lemon, Key lime, Persian lime, makrut lime and orange (species confirmed by at least one other
person, CC0/CC BY/CC BY-SA/CC BY-NC, credits in `backend/ood_data/inat/attributions.csv`); the 300 calamansi
photos were reviewed by eye: 140 show leaves clearly (`calamansi_labels.csv`).

**Fix.** (1) Species check retrained with the lemon and orange leaves as hard negatives (damaged calamansi
still weighted so damage is not mistaken for "other species"; per-class 98% rule kept). (2) The app accepts an
image only if this species check AND the previous general check accept it (`predict.CombinedGate`): the
retrained check alone rejected fewer objects (86.5% vs 98.6%). (3) Region analysis also needs at least 20% of
the regions to pass (chosen on validation data, `calibrate_gate.py`): the lemon photo was let back in by 2 of
17 zoomed windows. (4) Photos too blurry to verify the species are rejected with their own reason (sharpness
< 8.16, a quarter of the 1st percentile of validation calamansi photos). Healthy/Damaged classifier unchanged.

**Held-out results** (`evaluate_species.py`, `evaluate_gate.py`; same images in every column, `compare_species.py`):

| Images | Old check | New |
|---|---|---|
| The lemon photo (regression test) | accepted | **rejected** |
| Calamansi test photos, Healthy / Damaged (accepted) | 100% / 100% | 100% / 100% (96.9% correctly classified) |
| Lemon leaves (124) / orange leaves (66) wrongly accepted | 25.8% / 68.2% | **2.4% / 3.0%** |
| Blurred lemon / orange leaves accepted | 95% / 95% | 0% / 0% (too blurry) |
| Blurred calamansi photos | accepted (87.5% correct class) | rejected as too blurry (not guessed) |
| Other citrus (2 datasets) / citrus fruit / other plants rejected | 98.9%, 100% / 100% / 98.5% | 98.9%, 100% / 100% / 98.7% |
| Flowers / objects (Imagenette, Caltech) / people / blank images rejected | 97.9 / 98.6, 97.7 / 99.2 / 98.9% | 97.9 / 98.6, 97.7 / 99.2 / 98.9% |
| Real-world photos (branch with fruit, fruit only, screenshot, leaf) | 6/6 | 6/6 |
| **Real** lemon / Key lime / Persian lime / makrut lime / orange **plants** wrongly accepted | 26 / 31 / 30 / 41 / 13% | 22 / 25 / 25 / 37 / 9% |
| **Real calamansi plants** with clear leaves accepted (47) | 40.4% | 38.3% |
| Calamansi leaves on new backgrounds accepted | 91.5% | 86.9% |

**Tried and not used (round 2, `experiments/species_round2_patch.py`, models in `models/species_round2/`):**
adding the 75 real calamansi plant photos and real lemon/lime/orange photos to training, cut-outs and close-ups
of lemon leaves, category-balanced weights. To keep 98% of the real calamansi validation photos the threshold
collapsed (CNN 0.007), and rejection fell to 54% for real other-citrus plants and 80% for objects.

**Limitations (honest).** The check is reliable for what the app asks users to upload, one leaf filling the
frame: lemon and orange leaves are now rejected 97-98% of the time. It is **not** reliable for photos of whole
plants or branches of other citrus (about 1 in 4 still passes, more for makrut lime) and it rejects most real
calamansi plant photos. Calamansi (a mandarin x kumquat hybrid) and mandarin were not compared at all. Only 140
verified real-world calamansi photos were available; reliable species recognition on real plant photos needs
several hundred verified calamansi photos taken in the field (different trees, places, phones, light), plus
verified photos of the citrus grown nearby. No lime single-leaf dataset was found, so limes were tested only
on plant photos.
