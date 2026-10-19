"""Download real-world citrus photos from iNaturalist for TESTING the calamansi-leaf check.

These photos are never used for training. They show whole plants, branches, leaves and fruit
photographed by many people in many places, so they measure how the check behaves on real
photos and on citrus species it was never trained on (e.g. lime).

Species labels: iNaturalist does not give "research grade" to cultivated plants, so an
observation is used only when at least one other person agreed with its species
identification (num_identification_agreements >= 1) and its community taxon is that species.
One photo per observation (the first). Licences: CC0, CC BY, CC BY-SA, CC BY-NC (no ND).
Every photo's observation URL, photographer and licence are written to attributions.csv.

Output: backend/ood_data/inat/<species>/<observation id>.jpg
Usage:  python download_inat.py [--per-species 300]
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request

from config import BACKEND_DIR

OUT = BACKEND_DIR / "ood_data" / "inat"
TAXA = {  # folder -> iNaturalist taxon id
    "calamansi": 708697,      # Citrus x microcarpa (calamondin, calamansi)
    "lemon": 331124,          # Citrus x limon
    "key_lime": 331121,       # Citrus x aurantiifolia
    "persian_lime": 415524,   # Citrus x latifolia
    "makrut_lime": 123741,    # Citrus hystrix
    "orange": 331122,         # Citrus x aurantium (sweet and bitter orange)
}
LICENSES = {"cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa"}
API = "https://api.inaturalist.org/v1/observations"
HEADERS = {"User-Agent": "calamansi-leaf-check-evaluation (academic project)"}


def get_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as r:
        return json.load(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-species", type=int, default=300)
    args = ap.parse_args()
    rows = []
    for name, taxon in TAXA.items():
        folder = OUT / name
        folder.mkdir(parents=True, exist_ok=True)
        got, id_above = 0, 0
        while got < args.per_species:
            page = get_json(f"{API}?taxon_id={taxon}&quality_grade=casual,research&photos=true&photo_licensed=true"
                            f"&per_page=200&order_by=id&order=asc&id_above={id_above}")
            results = page["results"]
            if not results:
                break
            id_above = results[-1]["id"]
            for o in results:
                photo = (o.get("photos") or [{}])[0]
                lic = photo.get("license_code")
                community = (o.get("community_taxon_id") or (o.get("taxon") or {}).get("id"))
                if o.get("num_identification_agreements", 0) < 1 or community != taxon or lic not in LICENSES:
                    continue
                url = photo["url"].replace("/square.", "/medium.")
                dest = folder / f"{o['id']}.jpg"
                if not dest.exists():
                    try:
                        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as r:
                            dest.write_bytes(r.read())
                    except Exception as e:  # noqa: BLE001 - skip unreachable photos
                        print(f"  skip {o['id']}: {e}")
                        continue
                    time.sleep(0.3)
                rows.append({"species": name, "file": f"{name}/{dest.name}", "observation": o["uri"],
                             "photographer": (o.get("user") or {}).get("login", ""), "license": lic})
                got += 1
                if got >= args.per_species:
                    break
            time.sleep(1.0)  # API etiquette: about one request per second
        print(f"{name}: {got} photos", flush=True)
    with open(OUT / "attributions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["species", "file", "observation", "photographer", "license"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {OUT / 'attributions.csv'} ({len(rows)} photos)")


if __name__ == "__main__":
    main()
