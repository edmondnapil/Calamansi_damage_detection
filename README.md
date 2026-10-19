# Web-Based Calamansi Leaf Damage Detection Using Image Classification

A web application that classifies a photo of a calamansi leaf as **Healthy** or **Damaged** using a
transfer-learning image classifier trained on this project's own calamansi leaf dataset.

* **Machine learning:** TensorFlow / Keras (MobileNetV2 and EfficientNetB0 compared; the better one on validation data is used)
* **Backend:** Python FastAPI (`backend/`)
* **Frontend:** React + Vite + TypeScript + Tailwind CSS (`frontend/`)
* **Database / storage:** Supabase PostgreSQL + Supabase Storage (a local SQLite fallback is used until Supabase is configured)

> **Scope.** This is *binary image classification*, not object detection. Every upload first goes through a
> **calamansi-leaf check**; images that are not recognised as a calamansi leaf (other plants and citrus,
> fruit, people, objects) are rejected with "Invalid Image: Please upload a photo of a calamansi leaf." and are
> not classified or saved. Accepted images get one of two labels, Healthy or Damaged. The system does
> **not** identify diseases or pests and does not draw bounding boxes. Both models can make mistakes;
> confidence is the model's estimate, not a professional diagnosis.

---

## Contents

1. [Project structure](#1-project-structure)
2. [The dataset](#2-the-dataset)
3. [Model and results](#3-model-and-results)
4. [Setup guide (Windows PowerShell)](#4-setup-guide-windows-powershell)
5. [API reference](#5-api-reference)
6. [Security notes](#6-security-notes)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Project structure

```text
Web-Based Calamansi Leaf Damage Detection Using Image Classification/
├── train/ valid/ test/          original Roboflow dataset export (left untouched)
│   ├── healthy/  damaged/
│   └── _classes.csv
├── backend/
│   ├── config.py                shared paths and constants (image size, class order)
│   ├── check_external_duplicates.py  finds dataset images copied from a public non-calamansi dataset
│   ├── dataset_exclusions.csv   the 150 copied images, left out of training/evaluation
│   ├── prepare_dataset.py       inspect + validate dataset, leakage-free 70/15/15 split
│   ├── train_model.py           train and select the Healthy/Damaged classifier
│   ├── evaluate_model.py        independent test-set evaluation of the classifier
│   ├── download_ood_data.py     downloads public "not calamansi" image sets (negatives)
│   ├── train_gate.py            trains + tests the calamansi-leaf check
│   ├── evaluate_gate.py         end-to-end test of the leaf check on held-out images
│   ├── download_inat.py         real citrus plant photos from iNaturalist (TEST only, with credits)
│   ├── calibrate_gate.py        blur and region settings of the leaf check, on validation data
│   ├── evaluate_species.py      species test: lemon/lime/orange vs calamansi, blur, your regression photo
│   ├── compare_species.py       before/after table of species tests on the same images
│   ├── diagnose_dataset.py      runs every dataset image through the app pipeline, explains each rejection
│   ├── predict.py               model loading + preprocessing + leaf check (used by the API) + CLI
│   ├── tests/test_api.py        automated API tests (python -m pytest)
│   ├── storage.py               Supabase / local SQLite persistence
│   ├── auth.py                  accounts, sessions, CSRF, lockout (Supabase Auth)
│   ├── admin.py                 administrator API
│   ├── create_admin.py          one-time default-administrator setup
│   ├── main.py                  FastAPI application
│   ├── requirements.txt         direct dependencies
│   ├── requirements-lock.txt    exact tested versions (used by setup.ps1)
│   ├── .env.example
│   ├── models/                  classifier (.keras), leaf check (leaf_gate*), metadata
│   ├── ood_data/                negative datasets (downloaded, git-ignored)
│   └── outputs/                 splits.csv, reports, metrics, plots
├── frontend/                    React + Vite + TypeScript app
├── supabase/schema.sql          database table, indexes, RLS, storage bucket
├── setup.bat / setup.ps1        one-time setup on a new computer
├── start.bat / start.ps1        start the app (http://localhost:8000)
├── pack_project.ps1             zip the project for another computer
└── README.md
```

## 2. The dataset

The dataset is the Roboflow export already in the project root (`train/`, `valid/`, `test/`, each with
`healthy/` and `damaged/` folders). `prepare_dataset.py` inspects it **without moving, copying or deleting
any file** and writes a split manifest, `backend/outputs/splits.csv`, plus a full report,
`backend/outputs/dataset_report.json`.

| Finding | Detail |
|---|---|
| Files | 1,238 JPGs, all 416×416, all readable; folder labels match `_classes.csv` |
| Roboflow augmented copies | 217 files in `train/healthy` end in `_aug` and are rotated/flipped copies of other training photos |
| **Not calamansi** | **All 150 white-background "damaged" images** (`b--NNN-_png…`, `NN-p_png…`) are pixel-identical copies of the public **Citrus Leaves** dataset (Rauf et al. 2019, Mendeley Data `3f83gxmv57`: orange/citrus leaves from Pakistan). They are listed in `backend/dataset_exclusions.csv` with the matching public file and are **excluded** (`check_external_duplicates.py` re-creates the list; `prepare_dataset.py --keep-excluded` restores the old behaviour) |
| Unique calamansi photos | **469 Damaged, 402 Healthy** (871 total, ratio 1.17 : 1), so the dataset is *not* 50/50 as the folders suggest |
| Exact duplicates | none |
| Near-duplicates | 484 pairs of burst shots of the same leaf, taken seconds apart |
| Leakage in the original split | 46 groups of near-duplicate photos are spread across the original train/valid/test folders, so test scores on that split would be inflated |
| Possible label issues | 1 Damaged photo is visually very close to neighbouring Healthy shots (listed in the report under `possible_mislabels_review`) |
| Background | After the exclusion, every photo shows one leaf on the same blue/purple sheet (the white-background shortcut came entirely from the copied citrus images) |

**How the split is made**

* Photos are grouped so a photo, its `_aug` copy and its burst-shot near-duplicates always land in the same split.
  Near-duplicates = camera timestamps (from the file name) ≤ 30 s apart with a similar leaf crop, or a
  near-identical whole image. (A plain image hash did not work: the uniform blue backdrop made unrelated leaves look identical.)
* Groups are assigned to **train / validation / test = 70 / 15 / 15**, stratified by class (seed 42).
* `_aug` copies are excluded by default so every image is a genuine photo and the class balance is honest.
  Augmentation is applied on the fly during training instead.

Result: **train 611 (329 Damaged / 282 Healthy), validation 130 (70 / 60), test 130 (70 / 60).**

Options: `python prepare_dataset.py --use-existing-split` keeps the original folders;
`--include-roboflow-aug` adds the `_aug` copies to the training split.

## 3. Model and results

**Why transfer learning with MobileNetV2 / EfficientNetB0.** With ~700 training photos, training a CNN from
scratch would overfit. Both backbones are pretrained on ImageNet, small (≈2.3 M and ≈4.0 M parameters), run
quickly on a CPU (no GPU was available) and give fast inference for a web API. `train_model.py` trains both
with the same recipe and activates the one with the lowest validation loss. The test set is never used for
the choice.

**Training recipe:** 224×224 input; augmentation on training images only (flips, ±90° rotation, zoom, shift,
brightness, contrast); balanced class weights; stage 1 trains a new sigmoid head on the frozen backbone
(Adam 1e-3), stage 2 fine-tunes the top 40 backbone layers (Adam 1e-5, BatchNorm frozen); early stopping on
validation loss, checkpointing and LR reduction on plateau.

**Preprocessing is identical in training and in the API:** `predict.load_image` (EXIF rotation → RGB →
bilinear resize to 224×224). Normalisation is built into the saved model.

**Calamansi-leaf check (`train_gate.py`).** The classifier was trained only on calamansi leaves, so its
single sigmoid output would label *any* image Healthy or Damaged. A separate check now runs first:

1. *Classifier:* logistic regression on frozen ImageNet MobileNetV2 features. Positives are calamansi
   training photos. Negatives are public datasets (`download_ood_data.py`): other citrus leaves and citrus
   fruit, crop leaves of many species (PlantVillage), flowers, everyday objects and animals (Imagenette,
   Caltech-101) and people (LFW).
2. *Novelty check:* the distance to the nearest calamansi training example must be small. This rejects unusual
   images that none of the negative datasets cover.

Because all calamansi photos share one backdrop, the leaf is also cut out and pasted onto other backgrounds
during training, so the check learns the leaf and not the photo sheet. Thresholds are set on validation data
(keep 99% of calamansi photos). Results, including a *leave-one-dataset-out* test (rejection of a kind of image
the check never saw), are in RESULTS.md and on the Settings page.

**Results:** see [RESULTS.md](RESULTS.md) for the actual numbers from the latest training and evaluation run,
and `backend/outputs/` for the raw files:

| File | Content |
|---|---|
| `outputs/dataset_report.json` | everything in section 2 |
| `outputs/training_log.txt`, `training_history.json`, `training_curves.png` | per-epoch loss/accuracy for each candidate |
| `outputs/evaluation_metrics.json` | test accuracy, precision, recall, F1, ROC AUC, confusion matrix, overfitting check, background subgroups |
| `outputs/classification_report.txt`, `confusion_matrix.png` | test-set report and plot |
| `outputs/misclassified_test.csv` | test images the model got wrong |
| `models/model_metadata.json` | active model, version, class mapping, threshold, validation scores |
| `outputs/gate_evaluation.json` | calamansi-leaf check: acceptance of calamansi test photos, rejection per negative category, leave-one-dataset-out |
| `models/previous_v1/` | the first model (trained with the 150 copied citrus images), kept for comparison |

**Confidence convention:** the model's sigmoid output is P(Healthy). The stored `confidence` is the
probability of the predicted class (0.5–1.0), e.g. `0.987` is shown as 98.7%. Both class probabilities are
stored too. Results under 70% confidence are flagged as low confidence in the UI.

---

## 4. Setup guide (Windows PowerShell)

All commands assume PowerShell opened in the project folder:

```powershell
cd "C:\xampp\htdocs\Web-Based Calamansi Leaf Damage Detection Using Image Classification"
```

### 4.1 Prerequisites

* **Python 3.12** (TensorFlow 2.19 supports Python 3.9–3.12; it does **not** support 3.14).
  Install it with `winget install --id Python.Python.3.12 -e --scope user` if needed.
* **Node.js 18+** (`node --version`).

### 4.2 Python virtual environment and dependencies

```powershell
cd backend
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If activation is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or skip activation and
call `.\.venv\Scripts\python.exe` directly in the commands below.

### 4.3 Prepare, train and evaluate

From the `backend` folder with the virtual environment active:

```powershell
python download_ood_data.py    # public negative image sets, ~1.6 GB (~15-30 min)
python check_external_duplicates.py  # -> dataset_exclusions.csv (already included in the project)
python prepare_dataset.py      # inspect + split  (~1 min)  -> outputs\splits.csv, outputs\dataset_report.json
python train_model.py          # train both candidates on CPU (~30-45 min) -> models\
python evaluate_model.py       # independent test set -> outputs\evaluation_metrics.json
python train_gate.py           # calamansi-leaf check (~60-90 min on CPU) -> models\leaf_gate*
python calibrate_gate.py       # blur + region settings (validation data) -> models\leaf_gate_config.json
python evaluate_gate.py        # end-to-end leaf check on held-out images -> outputs\gate_evaluation.json
python download_inat.py        # optional: real citrus photos for the species test (~20 min)
python evaluate_species.py --tag mine   # species test -> outputs\species_evaluation_mine.csv/.json
python diagnose_dataset.py     # every dataset image: accepted? stage scores, reason -> outputs\dataset_diagnostic.csv
python -m pytest -q            # automated API tests (temporary local database, never Supabase)
python predict.py "..\test\damaged\IMG_20220405_090709_jpg.rf.8e1c3603ad6853b07bca5ae2d1890a17.jpg"
```

Faster single-model training: `python train_model.py --arch mobilenetv2`.
To keep a copy of the console output: `python train_model.py *> outputs\training_log.txt`.

### 4.4 Create the Supabase project

1. Sign in at <https://supabase.com> → **New project**. Choose a name, a strong database password and a region close to you (e.g. Singapore).
2. Wait for the project to finish provisioning.
3. **Project Settings → API** (or **Project Settings → API Keys**). Copy:
   * **Project URL**, e.g. `https://abcdefghijkl.supabase.co`
   * the **`service_role`** key (newer dashboards call it the **secret** key, `sb_secret_...`).
     This key bypasses Row Level Security. It goes **only** in `backend/.env`; never put it in the frontend or commit it.
   * The `anon`/publishable key is **not** needed: the browser never talks to Supabase directly.

### 4.5 Run the SQL schema

1. In the Supabase dashboard open **SQL Editor → New query**.
2. Paste the entire contents of [`supabase/schema.sql`](supabase/schema.sql) and click **Run**.
3. This creates:
   * table `public.detection_logs` (`id`, `predicted_class` ∈ {Healthy, Damaged}, `confidence` 0–1, `prob_healthy`,
     `prob_damaged`, `image_path`, `original_filename`, `model_version`, `created_at`) with check constraints and indexes;
   * **Row Level Security enabled with no policies for `anon`/`authenticated`**, so the public key can neither read nor write it;
   * a **private** Storage bucket `leaf-images` (5 MB limit, JPEG/PNG/WEBP only).
4. Check **Table Editor** shows `detection_logs` (with an "RLS enabled" badge) and **Storage** shows `leaf-images` marked *Private*.

If the bucket insert fails on your plan, create it manually: **Storage → New bucket**, name `leaf-images`,
leave **Public bucket off**, set the file size limit to 5 MB and allowed MIME types to `image/jpeg, image/png, image/webp`.
No storage policies are needed: the backend uploads with the service-role key and gives the browser 1-hour signed URLs.

### 4.6 Configure environment files

```powershell
Copy-Item backend\.env.example backend\.env
notepad backend\.env
```

Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Other options: `KEEP_UPLOADED_IMAGES` (true/false),
`MAX_UPLOAD_MB`, `LOW_CONFIDENCE_THRESHOLD`, `APP_TIMEZONE`, `CORS_ORIGINS`, `DB_BACKEND` (`auto`/`supabase`/`local`).

If you leave the Supabase values empty or as the `YOUR-...` placeholders, the backend uses the **local SQLite fallback**
(`backend/data/`) and the Settings page shows "Local SQLite (fallback)". Use `DB_BACKEND=supabase` to make the
server refuse to start without Supabase.

The frontend needs no `.env` in development (`frontend/.env.example` documents `VITE_API_URL` for production builds).

### 4.7 Start the backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```

Open <http://localhost:8000/api/health>. Expect `"model": {"loaded": true, ...}` and
`"database": {"backend": "supabase", "connected": true}`. Interactive docs: <http://localhost:8000/docs>.

### 4.8 Install and start the frontend

In a second PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. During development Vite forwards `/api` requests to the backend on port 8000.

**Simplest way to use the app (one server):** build the frontend once, and the backend serves it too:

```powershell
cd frontend; npm run build; cd ..\backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --port 8000
```

Then open <http://localhost:8000>. Both ways (`npm run dev` on port 5173, or the built app on port 8000) work.
Re-run `npm run build` after changing frontend code if you use port 8000.

Production build: `npm run build` creates `frontend/dist/`. Serve it with any static server and set
`VITE_API_URL` (before building) and the backend's `CORS_ORIGINS` to the right addresses.

### 4.9 Test end to end

1. Go to **Detect Leaf**, upload `test\healthy\...jpg` and `test\damaged\...jpg` images (or take a photo).
2. The result card shows the class and confidence returned by the model.
3. In Supabase **Table Editor → detection_logs** a new row appears; in **Storage → leaf-images** the image appears under `YYYY/MM/`.
4. **Dashboard** totals, chart and recent logs, **Logs** (search, filters, pagination, details) and **Reports** reflect the new records.
5. Command-line check:

```powershell
curl.exe -F "file=@test\healthy\IMG20220404201520_jpg.rf.93d927b6cd4742e971f5fa1d94593a0d.jpg;type=image/jpeg" http://localhost:8000/api/predict
curl.exe "http://localhost:8000/api/stats?days=7"
```

---

### 4.10 Moving the project to another computer

The app runs on any Windows 10/11 computer with internet access; it keeps using the same Supabase
project, so the same records and images appear there.

**On this computer**

```powershell
powershell -ExecutionPolicy Bypass -File .\pack_project.ps1     # creates Calamansi-Leaf-Detection.zip on the Desktop (~90 MB)
```

The zip contains the code, dataset and trained models. It leaves out `backend\.venv`,
`frontend\node_modules` (both are computer-specific and re-created by setup), `backend\ood_data`
(1.6 GB, only needed to retrain the leaf check) and **`backend\.env`**, which holds the Supabase secret
key. Copy `backend\.env` separately by USB. Never upload it to GitHub, Google Drive links or chats.

**On the other computer**

1. Install **Python 3.12** (`winget install --id Python.Python.3.12 -e --scope user`) and **Node.js LTS**
   (`winget install OpenJS.NodeJS.LTS`). Python 3.13 or newer will not work with TensorFlow 2.19.
2. Extract the zip to a **short folder path**, ideally `C:\Calamansi-Leaf-Detection`. Windows limits path
   length, so very deep folders (e.g. inside `Downloads\...\...`) can break the install; setup checks this.
   Put the copied `.env` into `C:\Calamansi-Leaf-Detection\backend\`.
3. Double-click **`setup.bat`** (once; 5-15 minutes). It installs the exact package versions from
   `backend\requirements-lock.txt`, builds the web interface and checks that the models load.
4. Double-click **`start.bat`** whenever you want to use the app. It opens <http://localhost:8000>.
   Keep its window open while using the app.

Without the `.env` file the app still works, but saves results only on that computer (local SQLite).

If you use Git instead of the zip: `*.keras` model files and `.env` are git-ignored, so copy
`backend\models\` and `backend\.env` manually, or retrain (section 4.3).

---

### 4.11 Accounts, email codes and the landing page

The public landing page is at `/`. Everything under `/app` (dashboard, Detect, Logs, Reports, Settings,
Users) and every detection API requires a **signed-in account with a verified email**. Each user sees only
their own detections; administrators see all.

**How it works.** Supabase Auth stores the accounts, password hashes and the 6-digit email codes (hashed,
expiring, single-use, replaced when a new one is sent) and sends the emails through your SMTP server. The
FastAPI backend (`backend/auth.py`) adds password rules, duplicate checks, login lockout, code-attempt
limits, resend cooldowns, audit logging and HttpOnly session cookies with CSRF protection. No separate
OTP system and no PHP/PHPMailer are used, because the project has no PHP backend and Supabase Auth
already provides secure codes. The browser never receives a Supabase key or token.

**One-time setup**

1. **Database:** run `supabase/migrations/002_auth_profiles.sql` in the Supabase SQL Editor (after
   `schema.sql`). It adds `profiles`, `security_audit_logs` and `detection_logs.user_id`, with RLS.
2. **SMTP** (required to email anyone outside your Supabase team): Supabase → Authentication → Emails →
   SMTP Settings → enable Custom SMTP. Gmail example: host `smtp.gmail.com`, port `587`, username = your
   Gmail address, password = a Gmail **App Password** (Google Account → Security → 2-Step Verification →
   App passwords). The SMTP password is stored in Supabase only.
3. **Email templates** (Authentication → Emails → Templates) must show the code `{{ .Token }}`:
   * *Confirm signup*: `<h2>Verify your email</h2><p>Your verification code is:</p><h1>{{ .Token }}</h1><p>It expires in 5 minutes.</p>`
   * *Reset Password*: `<h2>Reset your password</h2><p>Your password reset code is:</p><h1>{{ .Token }}</h1><p>It expires in 5 minutes.</p>`
4. **Code settings** (Authentication → Sign In / Providers → Email): Email OTP Expiration `300`,
   Email OTP Length `6`, Confirm email **on**.
5. **First administrator:** see section 4.12 (`python create_admin.py`). Roles can only be changed on the
   server; users cannot promote themselves and public registration always creates ordinary users.

Optional settings (`backend/.env`, defaults shown in `.env.example`): `AUTH_COOKIE_SECURE=true` behind
HTTPS, `AUTH_SESSION_DAYS`, `OTP_RESEND_COOLDOWN_SECONDS`, `OTP_MAX_SENDS_PER_HOUR`, `OTP_MAX_ATTEMPTS`,
`LOGIN_MAX_FAILURES`, `LOGIN_LOCK_MINUTES`.

**Security rules enforced on the server**

| Rule | Value |
|---|---|
| Password | 8-72 characters with lowercase, uppercase, number and symbol; not containing the email name or username |
| Duplicate email / username | rejected at registration |
| Wrong codes | 5 per sent code, then a new code is required |
| Resend / reset code | 60 s cooldown, 5 per hour per email (identical for unknown emails) |
| Failed sign-ins | 5 per email in 15 min, or 30 per IP, then a 15 min lockout |
| Login and forgot-password messages | identical whether or not the account exists |
| Password reset | signs out all sessions of the account |
| Sessions | HttpOnly cookies (`SameSite=Lax/Strict`), CSRF token checked on every POST/PATCH |
| Suspended accounts | cannot sign in; existing sessions stop working |

### 4.12 Administrator dashboard and the default administrator

Administrators sign in on the normal login page and are sent to **`/admin`** (ordinary users go to `/app`).
The admin console has: **Overview** (live counts of users, active/suspended/unverified accounts, detections,
registrations and detections per day, recent registrations and security events), **Users** (search by name,
username or email, filter by status/role/verification, view details and detection history, edit name and
username, suspend/reactivate, delete with typed confirmation), **Activity** (the security audit log) and
**My account** (account details, change password, sign out). Ordinary users who open an `/admin` URL are
redirected, and every `/api/admin/*` endpoint returns 403 for them. Administrators cannot suspend or delete
themselves or other administrators, and nobody can change a role from the website.

**Create the default administrator** (one-time, on the server; there is no web endpoint for this):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python create_admin.py --email admin@your-school.edu.ph --name "System Administrator" --username admin
```

* The script uses Supabase Auth's admin API (same password hashing as every account) and marks the account
  **must change password**.
* If `ADMIN_INITIAL_PASSWORD` is not set (in the environment or `backend/.env`), a strong random temporary
  password is generated and **printed once** in that console. Copy it; it is not stored anywhere else.
  To choose it yourself: `$env:ADMIN_INITIAL_PASSWORD = "..."` before running the command (8+ characters with
  upper/lowercase, number and symbol). Optional variables: `ADMIN_EMAIL`, `ADMIN_FULL_NAME`, `ADMIN_USERNAME`.
* **Idempotent:** if an administrator already exists the script changes nothing (no new account, no
  password reset). An e-mail that already belongs to an ordinary account is refused unless you pass
  `--promote-existing` (that account keeps its password).

**First sign-in:** open <http://localhost:8000/login>, sign in with the e-mail and temporary password. You
are taken to **Choose a new password**; until then the API refuses every other request
(`password_change_required`). Afterwards you land on `/admin`. Change the password later under
*Admin → My account* (or *Settings* for ordinary users); other devices are signed out on every change.

Note: a suspended user sees the generic "Incorrect email or password" at sign-in, because Supabase checks
the suspension before the password and a specific message would reveal which accounts exist.

---

## 5. API reference

| Method & path | Purpose |
|---|---|
| `GET /api/auth/csrf` | Issues the CSRF cookie/token (sent back as `X-CSRF-Token` on every POST/PATCH) |
| `POST /api/auth/register` | `full_name, username, email, password`; sends the 6-digit verification code |
| `POST /api/auth/verify-email` | `email, code`; verifies the email and signs the user in |
| `POST /api/auth/resend-code` | `email`; new verification code (cooldown) |
| `POST /api/auth/login` / `refresh` / `logout` | Sign in (lockout after repeated failures), renew, sign out |
| `GET /api/auth/me` | The signed-in user (401 if not signed in, 403 if unverified or suspended) |
| `POST /api/auth/forgot-password` | `email`; always the same generic answer |
| `POST /api/auth/reset-password` | `email, code, password`; changes the password and signs out every session |
| `POST /api/auth/change-password` | `current_password, new_password`; signs out other devices, clears a temporary-password flag |
| `GET /api/admin/overview?days=14` | Administrators: live account/detection statistics, daily series, recent registrations and activity |
| `GET /api/admin/users?q=&status=&role=&verified=&page=` | Administrators: search and filter accounts |
| `GET/PATCH/DELETE /api/admin/users/{id}` | Administrators: details, edit name/username/status, delete account with its detections |
| `GET /api/admin/activity?event_type=&status=&page=` | Administrators: security audit log (no e-mails or IPs) |
| `GET /api/health` | Model readiness, database backend/connection, image retention, upload limit |
| `POST /api/predict` | `multipart/form-data` field `file` (JPG/PNG/WEBP, ≤ 5 MB). Validates, classifies with the trained model, stores image + record, returns the record (`201`) |
| `GET /api/detections` | Query: `search`, `predicted_class` (Healthy/Damaged), `date_from`, `date_to` (YYYY-MM-DD), `page`, `page_size` (≤ 100) |
| `GET /api/detections/{id}` | One record (`404` if not found, `422` for an invalid UUID) |
| `GET /api/stats?days=7` | All-time totals plus this period vs the previous period, and the latest detection |
| `GET /api/reports?date_from&date_to` | Totals, average confidence, low-confidence count, daily Healthy/Damaged series |
| `GET /api/reports/export` | CSV export for a date range |
| `GET /api/model` | Model metadata and offline evaluation metrics |

Error codes: `400` bad parameters / empty file, `413` file too large, `415` unsupported type, `422` unreadable
image **or not a calamansi leaf** (`{"detail": {"code": "not_calamansi_leaf", "message": "Invalid Image: Please upload a
photo of a calamansi leaf."}}`; nothing is saved), `502` record could not be saved, `503` model or database unavailable. The API never returns a made-up
prediction: if the model is not loaded, `/api/predict` returns `503`.

## 6. Security notes

* The Supabase **service-role key lives only in `backend/.env`** (git-ignored). The frontend never receives any Supabase key.
* `detection_logs` has RLS enabled with no anon/authenticated policies, and the bucket is private. All access goes through the backend.
* Records are created **only** from the server-side model output. The client sends an image, never a label or score.
* Uploads are checked on the server: MIME type, real image format, size limit, decompression-bomb pixel limit. Stored images are re-encoded to JPEG, which strips EXIF metadata such as GPS location.
* The API has no endpoints that modify or delete records.
* Accounts: see section 4.11. Every detection endpoint requires a verified, active account and returns only the caller's records (administrators: all). Serve the app over **HTTPS** in production and set `AUTH_COOKIE_SECURE=true`.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `No images found` in `prepare_dataset.py` | The dataset must be at `<DATASET_DIR>/<train\|valid\|test>/<healthy\|damaged>/` or `<DATASET_DIR>/<healthy\|damaged>/`. Folder names are case-insensitive. Set `DATASET_DIR` in `backend/.env` if it lives elsewhere |
| `ignoring unknown class folder` | Rename the folder to `healthy` or `damaged` |
| `No matching distribution found for tensorflow` | You are on an unsupported Python (e.g. 3.13/3.14). Create the venv with Python 3.12 (section 4.2) |
| `outputs/splits.csv not found` | Run `python prepare_dataset.py` before training |
| `/api/health` shows `model.loaded: false` / predict returns 503 | Train first (`python train_model.py`); check `backend/models/model_metadata.json` and the `.keras` file exist; restart uvicorn |
| Frontend says "Cannot reach the backend server" | Start uvicorn on port 8000; check nothing else uses the port (`netstat -ano \| findstr :8000`) |
| CORS error in the browser console | Add the frontend's origin to `CORS_ORIGINS` in `backend/.env` and restart |
| Database "unavailable" / `Invalid API key` | Check `SUPABASE_URL` and that you copied the **service_role/secret** key, not the anon key |
| `relation "public.detection_logs" does not exist` | Run `supabase/schema.sql` in the SQL Editor |
| `Bucket not found` / image upload fails | Create the `leaf-images` bucket (section 4.5) or set `SUPABASE_BUCKET`. The prediction is still saved without the image and the UI shows a warning |
| `413` / `415` on upload | Image larger than `MAX_UPLOAD_MB` or not JPG/PNG/WEBP (HEIC photos from iPhones must be converted) |
| Camera button missing / not working | Browsers allow the camera only on `localhost` or HTTPS, and you must grant permission. Uploading a photo always works |
| Poor predictions on your own photos | The training photos show a single leaf on a plain blue or white background. Photograph one leaf, flat, centred, in even light on a plain background. For better generalisation, add more varied labelled photos to the dataset and re-run steps 4.3 |
| "Invalid Image" for an image taken from `train/damaged`, `valid/damaged` or `test/damaged` | Check `outputs/dataset_diagnostic.csv` (`python diagnose_dataset.py`). The 150 white-background files (`b--NNN-_png…`, `NN-p_png…`) are copies of the public Citrus Leaves dataset (orange leaves, not calamansi), listed in `backend/dataset_exclusions.csv`; they are rejected on purpose. Every genuine calamansi photo in the dataset is accepted |
| "Invalid Image" for a photo that really is a calamansi leaf | The calamansi-leaf check was trained on single leaves photographed flat on a plain sheet. Photograph one leaf, flat, centred, filling a good part of the frame, in even light, on a plain background. Leaves still on the tree or in a pile may be rejected. To make it more tolerant, add such photos to the dataset and re-run `prepare_dataset.py`, `train_model.py` and `train_gate.py` |
| A non-calamansi image is accepted | Very similar leaves (especially other citrus) can occasionally pass. Add examples of what was wrongly accepted to a negative dataset folder and re-run `train_gate.py` |
| "Invalid Image" with the reason "too blurry to verify that it is a calamansi leaf" | Blur removes the details that tell calamansi from lemon or lime, so such photos are not guessed. Hold the camera steady, tap the leaf to focus, use good light |
| A lemon, lime or orange **plant** photo is accepted, or a real calamansi **plant** photo rejected | Known limitation (RESULTS.md section 8): photos of whole plants are much less reliable than single leaves. Photograph one leaf, flat, filling the frame |
| `/api/predict` returns 503 "calamansi-leaf validation model is missing" | Run `python download_ood_data.py` then `python train_gate.py`; the API refuses to classify without the check, so it never labels an unchecked image |
| A page is blank or only shows content after Ctrl+F5 | Fixed in this version (see RESULTS.md, "Page loading fixes"). Rebuild the frontend (`npm run build`) and restart the backend so the browser gets the new files; a normal refresh is enough afterwards. If a page still fails, it now shows the error message instead of a blank page; report that message |
| Training is slow | It runs on the CPU. Use `--arch mobilenetv2` to train only one candidate, or lower `--epochs-finetune` |
