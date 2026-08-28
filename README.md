# Ethiopia Malaria Early Warning System (MEWS)

Climate-driven malaria risk monitoring for Ethiopia, built entirely on **Ethiopia-specific, real,
freely-accessible data** — no pan-African or global datasets standing in for national ones.

## What's in this repo

| File | Purpose |
|---|---|
| `Ethiopia_MEWS_Colab.ipynb` | Full pipeline — fetch data, engineer features, train the risk model, export dashboard JSON. Run in Google Colab (needs open internet; this sandbox cannot fetch these APIs itself). |
| `Ethiopia_MEWS_Dashboard.html` | Single-file dashboard. No build step. Reads `data/dashboard/*.json`; falls back to labeled seed data if missing. |
| `scripts/fetch_ethiopia_data.py` | Headless equivalent of the notebook, for CI. |
| `requirements.txt` | Python deps for the script above. |
| `update-ews-data.yml` | GitHub Actions workflow — **move this to `.github/workflows/`** in your repo. |

## Data sources (Ethiopia-only)

- **Climate** — NASA POWER API, queried per Ethiopian region (temperature, rainfall, humidity). Free, no key.
- **National malaria burden** — WHO GHO OData API, `SpatialDim = ETH`. Free, no key.
- **ENSO phase** — NOAA Niño 3.4 index (East African rainfall teleconnection).
- **Regional 2024 case/death share** — WHO Disease Outbreak News, Ethiopia, 31 Oct 2024 (cited in the notebook).

**Known limitation, stated plainly:** Ethiopia's real sub-national monthly case counts live in EPHI's
PHEM/HMIS system, which has no public API. The regional-monthly series here apportions the real
national WHO trend by published regional shares + Ethiopia's kiremt/belg seasonality — it is a
documented approximation, not raw surveillance data. Swap in EPHI/PHEM or DHS figures once you have
institutional access (Cell 6 of the notebook / the equivalent block in the script) for a validated result.

## Deploy the dashboard on GitHub Pages

1. Push this folder structure to a GitHub repo.
2. Move `update-ews-data.yml` into `.github/workflows/update-ews-data.yml`.
3. Settings → Pages → deploy from the branch containing `Ethiopia_MEWS_Dashboard.html` (rename it
   to `index.html`, or set it as the Pages entry file).
4. Populate real data either by:
   - running `Ethiopia_MEWS_Colab.ipynb` in Colab and using its Cell 13 to push `data/dashboard/*.json`, or
   - letting the GitHub Actions workflow do it on schedule (edit the cron line to taste, or trigger
     it manually from the Actions tab).
5. Open the Pages URL — the dashboard fetches the JSON at runtime, no rebuild needed.

## Regions covered

Oromia, Amhara, South West Ethiopia Peoples, South Ethiopia, Gambela, Benishangul-Gumuz, Sidama,
SNNP, Tigray, Somali, Afar, Harari, Dire Dawa, Addis Ababa — Ethiopia's current (post-2023)
regional states and chartered city administrations.
