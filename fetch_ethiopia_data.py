"""
Ethiopia Malaria EWS — headless data refresh script.

Mirrors Ethiopia_MEWS_Colab.ipynb (Cells 2-12) without any notebook/Colab
dependency, so it can run in GitHub Actions on a schedule. Writes the same
four JSON files the dashboard reads:
    data/dashboard/national_trend.json
    data/dashboard/regional_risk.json
    data/dashboard/climate_latest.json
    data/dashboard/meta.json

Usage:
    pip install -r requirements.txt
    python scripts/fetch_ethiopia_data.py
"""
import json
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

OUT_DIR = Path("data/dashboard")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ETHIOPIA_REGIONS = {
    "Oromia":                        (8.5400, 39.2700, "Adama",        44.0),
    "Amhara":                        (11.5936, 37.3908, "Bahir Dar",   18.0),
    "South West Ethiopia Peoples":   (7.2667, 36.2333, "Bonga",        12.0),
    "South Ethiopia":                (6.0333, 37.5500, "Arba Minch",    7.0),
    "Gambela":                       (8.2500, 34.5833, "Gambela",       6.0),
    "Benishangul-Gumuz":             (10.0667, 34.5333, "Assosa",       4.0),
    "Sidama":                        (7.0500, 38.4667, "Hawassa",       3.0),
    "SNNP":                          (6.8500, 37.7667, "Wolaita Sodo",  2.5),
    "Tigray":                        (13.4967, 39.4753, "Mekelle",      2.0),
    "Somali":                        (9.3500, 42.8000, "Jijiga",        0.8),
    "Afar":                          (11.7952, 41.0117, "Semera",       0.4),
    "Harari":                        (9.3132, 42.1181, "Harar",         0.2),
    "Dire Dawa":                     (9.5931, 41.8661, "Dire Dawa",     0.1),
    "Addis Ababa":                   (9.0300, 38.7400, "Addis Ababa",   0.0),
}

SEASONAL_WEIGHTS = {
    1: 0.055, 2: 0.05, 3: 0.06, 4: 0.07, 5: 0.075, 6: 0.06,
    7: 0.055, 8: 0.06, 9: 0.11, 10: 0.15, 11: 0.135, 12: 0.10,
}

POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
GHO_BASE = "https://ghoapi.azureedge.net/api"
START_YEAR = 2010


def fetch_power_monthly(lat, lon, start_year=START_YEAR, end_year=None):
    end_year = end_year or date.today().year
    r = requests.get(POWER_URL, params={
        "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M",
        "community": "AG", "longitude": lon, "latitude": lat,
        "start": start_year, "end": end_year, "format": "JSON",
    }, timeout=30)
    r.raise_for_status()
    payload = r.json()["properties"]["parameter"]
    rows = []
    for param, series in payload.items():
        for yyyymm, val in series.items():
            if yyyymm.endswith("13"):
                continue
            rows.append({"yyyymm": yyyymm, "param": param, "value": val})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["yyyymm"], format="%Y%m")
    return df.pivot_table(index="date", columns="param", values="value").reset_index()


def fetch_who_ethiopia_malaria():
    ind = requests.get(f"{GHO_BASE}/Indicator",
                        params={"$filter": "contains(IndicatorName,'Malaria')"}, timeout=30).json()["value"]
    frames = []
    for row in ind:
        code_, name = row["IndicatorCode"], row["IndicatorName"]
        r = requests.get(f"{GHO_BASE}/{code_}", params={"$filter": "SpatialDim eq 'ETH'"}, timeout=30)
        vals = r.json().get("value", [])
        if not vals:
            continue
        df = pd.DataFrame(vals)[["TimeDim", "NumericValue"]].rename(
            columns={"TimeDim": "year", "NumericValue": "value"})
        df["IndicatorName"] = name
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["year", "value", "IndicatorName"])


def fetch_enso():
    resp = requests.get("https://psl.noaa.gov/data/correlation/nina34.data", timeout=20)
    records = []
    for line in resp.text.strip().split("\n"):
        parts = line.split()
        if len(parts) == 13:
            try:
                year = int(parts[0])
                for m, v in enumerate(parts[1:], start=1):
                    val = float(v)
                    if abs(val) < 90:
                        records.append({"year": year, "month": m, "enso_nino34": val})
            except ValueError:
                pass
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
    return df.sort_values("date").reset_index(drop=True)


def temp_suitability(t):
    if t < 16 or t > 34:
        return 0.0
    return max(0.0, 1 - abs(t - 25) / 9)


def risk_level(s):
    if s >= 70:
        return "Alert"
    if s >= 50:
        return "Warning"
    if s >= 30:
        return "Watch"
    return "Low"


def main():
    print("Fetching NASA POWER climate for", len(ETHIOPIA_REGIONS), "Ethiopian regions...")
    climate_frames = []
    for region, (lat, lon, town, share) in ETHIOPIA_REGIONS.items():
        try:
            wide = fetch_power_monthly(lat, lon)
            wide.insert(0, "region", region)
            climate_frames.append(wide)
            time.sleep(0.3)
        except Exception as e:
            print(f"  WARNING: {region} failed: {e}")
    climate_df = pd.concat(climate_frames, ignore_index=True).rename(columns={
        "T2M": "temp_mean_c", "T2M_MAX": "temp_max_c", "T2M_MIN": "temp_min_c",
        "PRECTOTCORR": "rainfall_mm_day", "RH2M": "humidity_pct",
    })
    climate_df["rainfall_mm_month"] = climate_df["rainfall_mm_day"] * climate_df["date"].dt.days_in_month

    print("Fetching WHO GHO Ethiopia malaria indicators...")
    who_df = fetch_who_ethiopia_malaria()
    national_cases = who_df[who_df["IndicatorName"].str.contains("cases", case=False, na=False)]
    national_cases = national_cases.dropna(subset=["value"]).groupby("year", as_index=False)["value"].max()
    national_cases = national_cases.rename(columns={"value": "national_est_cases"})

    print("Fetching NOAA ENSO...")
    enso_df = fetch_enso()

    print("Apportioning national trend to regions and computing risk scores...")
    monthly_national = []
    for _, row in national_cases.iterrows():
        for m, w in SEASONAL_WEIGHTS.items():
            monthly_national.append({"date": pd.Timestamp(int(row["year"]), m, 1),
                                      "national_est_cases_month": row["national_est_cases"] * w})
    monthly_national_df = pd.DataFrame(monthly_national)

    regional_monthly = []
    for region, (lat, lon, town, share_pct) in ETHIOPIA_REGIONS.items():
        tmp = monthly_national_df.copy()
        tmp["region"] = region
        tmp["case_share_pct"] = share_pct
        tmp["est_cases"] = tmp["national_est_cases_month"] * (share_pct / 100.0)
        regional_monthly.append(tmp)
    regional_malaria_df = pd.concat(regional_monthly, ignore_index=True)

    panel = climate_df.merge(regional_malaria_df[["date", "region", "est_cases", "case_share_pct"]],
                              on=["date", "region"], how="left")
    panel = panel.merge(enso_df[["date", "enso_nino34"]], on="date", how="left")
    panel = panel.sort_values(["region", "date"])

    for lag in (1,):
        panel[f"temp_lag{lag}"] = panel.groupby("region")["temp_mean_c"].shift(lag)
    clim_mean = panel.groupby("region")["rainfall_mm_month"].transform("mean")
    clim_std = panel.groupby("region")["rainfall_mm_month"].transform("std")
    panel["rainfall_anomaly_z"] = (panel["rainfall_mm_month"] - clim_mean) / clim_std

    panel["temp_suitability"] = panel["temp_lag1"].apply(lambda t: temp_suitability(t) if pd.notna(t) else 0)
    panel["rain_score"] = panel["rainfall_anomaly_z"].clip(-2, 2).add(2).div(4)
    panel["enso_score"] = panel["enso_nino34"].clip(-2, 2).add(2).div(4)
    panel["endemicity_score"] = panel["case_share_pct"].fillna(0) / panel["case_share_pct"].max()
    panel["risk_score"] = (0.35 * panel["rain_score"] + 0.30 * panel["temp_suitability"] +
                            0.15 * panel["enso_score"].fillna(0.5) + 0.20 * panel["endemicity_score"]) * 100
    panel["risk_level"] = panel["risk_score"].apply(risk_level)

    latest_date = panel["date"].max()
    latest = panel[panel["date"] == latest_date].sort_values("risk_score", ascending=False)

    national_trend_json = [{"year": int(r.year), "cases": float(r.national_est_cases)}
                            for r in national_cases.itertuples()]
    regional_risk_json = [{
        "region": r["region"], "town": ETHIOPIA_REGIONS[r["region"]][2],
        "lat": ETHIOPIA_REGIONS[r["region"]][0], "lon": ETHIOPIA_REGIONS[r["region"]][1],
        "risk_score": round(float(r["risk_score"]), 1), "risk_level": r["risk_level"],
        "rainfall_anomaly_z": round(float(r["rainfall_anomaly_z"]), 2) if pd.notna(r["rainfall_anomaly_z"]) else 0,
        "temp_c": round(float(r["temp_lag1"]), 1) if pd.notna(r["temp_lag1"]) else None,
        "case_share_pct": float(r["case_share_pct"]) if pd.notna(r["case_share_pct"]) else None,
    } for _, r in latest.iterrows()]

    recent = panel[panel["date"] >= latest_date - pd.DateOffset(months=12)]
    climate_latest_json = [{
        "region": r["region"], "date": r["date"].strftime("%Y-%m-%d"),
        "rainfall_mm": round(float(r["rainfall_mm_month"]), 1),
        "temp_c": round(float(r["temp_mean_c"]), 1),
        "enso": round(float(r["enso_nino34"]), 2) if pd.notna(r["enso_nino34"]) else None,
    } for _, r in recent.iterrows()]

    meta_json = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "latest_data_month": latest_date.strftime("%Y-%m"),
        "sources": ["NASA POWER (climate)", "WHO GHO OData API (national malaria)",
                    "NOAA Nino 3.4 (ENSO)", "WHO Disease Outbreak News 31-Oct-2024 (regional shares)"],
        "note": "Regional-monthly malaria series apportions the national WHO trend by published "
                "regional case-share; it is not raw EPHI PHEM/HMIS data.",
    }

    (OUT_DIR / "national_trend.json").write_text(json.dumps(national_trend_json, indent=2))
    (OUT_DIR / "regional_risk.json").write_text(json.dumps(regional_risk_json, indent=2))
    (OUT_DIR / "climate_latest.json").write_text(json.dumps(climate_latest_json, indent=2))
    (OUT_DIR / "meta.json").write_text(json.dumps(meta_json, indent=2))
    print(f"Done. Wrote 4 JSON files to {OUT_DIR}/ (latest data month: {meta_json['latest_data_month']})")


if __name__ == "__main__":
    main()
