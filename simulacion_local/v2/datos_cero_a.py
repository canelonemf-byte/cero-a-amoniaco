#!/usr/bin/env python3
"""CERO-A v2 - preparacion de series horarias reales (UTC) para El Prat de Llobregat (41.30 N, 2.08 E).
Fuentes (descargadas sin credenciales, guardadas en data/):
  - FV: PVGIS v5.3 API seriescalc (JRC), radiacion PVGIS-SARAH3, meteo ERA5, 2014-2023, c-Si, 1 kWp,
        perdidas 14 %, inclinacion/azimut optimos (38 deg / 2 deg), horizonte DEM.
  - Eolica: ERA5 (ECMWF/Copernicus) via Open-Meteo Historical Weather API, viento 10 m y 100 m, 2014-2023.
        Celda mas cercana 41.25 N 2.00 E (costera, base) y celda 'land' 41.50 N 2.00 E (sensibilidad pesimista).
        Curva de potencia Enercon E-53/800 (OEDB via windpowerlib), buje 73 m, cizalla horaria ley potencial
        con alfa derivado de ERA5 10 m/100 m.
  - Precio: mercado diario OMIE zona ES via API Energy-Charts (Fraunhofer ISE), 2019-2025 (2025: MTU 15 min -> media horaria).
  - Perfil PPA: CF horario nacional Espana (eolica terrestre, solar) 2024-2025 = generacion / potencia instalada media,
        Energy-Charts public_power + installed_power (fuente primaria REE/ENTSO-E).
  - Periodos tarifarios 6.1TD (Circular CNMC 3/2020), hora local Europe/Madrid; festivos nacionales no modelados.
"""
import json, datetime as dt
from zoneinfo import ZoneInfo
from pathlib import Path
import numpy as np

D = Path(__file__).resolve().parent / "data"
Y0, Y1 = 2014, 2023

def horas_utc(y0, y1):
    t0 = dt.datetime(y0, 1, 1, tzinfo=dt.timezone.utc); t1 = dt.datetime(y1 + 1, 1, 1, tzinfo=dt.timezone.utc)
    n = int((t1 - t0).total_seconds() // 3600)
    return np.array([int(t0.timestamp()) + 3600 * i for i in range(n)], dtype=np.int64)

def fv():
    h = json.load(open(D / "pvgis_2014_2023.json"))["outputs"]["hourly"]
    return np.array([x["P"] for x in h]) / 1000.0         # kW por kWp (marca HH:10 -> hora HH)

def curva_e53():
    from windpowerlib import data as wd
    df = wd.get_turbine_types(print_out=False)
    from windpowerlib import WindTurbine
    t = WindTurbine(turbine_type="E-53/800", hub_height=73)
    pc = t.power_curve
    return pc["wind_speed"].to_numpy(float), pc["value"].to_numpy(float) / t.nominal_power

def eolica(fichero):
    w = json.load(open(D / fichero))["hourly"]
    v10 = np.array(w["wind_speed_10m"], float); v100 = np.array(w["wind_speed_100m"], float)
    alfa = np.clip(np.log(np.maximum(v100, 0.1) / np.maximum(v10, 0.1)) / np.log(10.0), 0.0, 0.6)
    v73 = v100 * (73.0 / 100.0) ** alfa
    vs, pc = curva_e53()
    cf = np.interp(v73, vs, pc, left=0.0, right=0.0)
    cf[v73 > vs.max()] = 0.0                               # corte por viento alto
    return cf, v100

def omie():
    m = {}
    for y in range(2019, 2026):
        p = json.load(open(D / f"omie_es_{y}.json"))
        for u, pr in zip(p["unix_seconds"], p["price"]):
            if pr is None: continue
            k = (u // 3600) * 3600; m.setdefault(k, []).append(pr)
    return {k: float(np.mean(v)) for k, v in m.items()}

def perfil_nacional(ts_p):
    """CF horario nacional (Espana) eolica terrestre y solar 2024-2025: generacion Energy-Charts public_power /
    potencia instalada media del ano (media fin de ano anterior y actual, Energy-Charts installed_power)."""
    cap = json.load(open(D / "ec_installed_power_es.json")); yrs = [int(x) for x in cap["time"]]
    capd = {p["name"]: dict(zip(yrs, p["data"])) for p in cap["production_types"]}
    out = {"Wind onshore": np.full(len(ts_p), np.nan), "Solar": np.full(len(ts_p), np.nan)}
    idx = {int(u): i for i, u in enumerate(ts_p)}
    for y in (2024, 2025):
        g = json.load(open(D / f"ec_public_power_es_{y}.json")); us = np.array(g["unix_seconds"]) // 3600 * 3600
        for p in g["production_types"]:
            if p["name"] not in out: continue
            cn = "Wind onshore" if p["name"] == "Wind onshore" else "Solar AC"
            c_mid = 0.5 * (capd[cn][y - 1] + capd[cn][y]) * 1000.0           # MW
            v = np.array([x if x is not None else np.nan for x in p["data"]], float)
            acc = {}
            for uu, vv in zip(us, v):
                if not np.isnan(vv): acc.setdefault(int(uu), []).append(vv)
            for uu, vs in acc.items():
                if uu in idx: out[p["name"]][idx[uu]] = np.mean(vs) / c_mid
    return np.clip(out["Solar"], 0, 1), np.clip(out["Wind onshore"], 0, 1)

def periodo_61td(ts):
    tz = ZoneInfo("Europe/Madrid"); out = np.empty(len(ts), np.int64)
    temporada = {1: "A", 2: "A", 7: "A", 12: "A", 3: "MA", 11: "MA", 6: "M", 8: "M", 9: "M", 4: "B", 5: "B", 10: "B"}
    pico = {"A": (1, 2), "MA": (2, 3), "M": (3, 4), "B": (4, 5)}
    for i, u in enumerate(ts):
        l = dt.datetime.fromtimestamp(int(u), tz)
        if l.weekday() >= 5 or l.hour < 8: out[i] = 6; continue
        a, b = pico[temporada[l.month]]
        out[i] = a if (9 <= l.hour < 14 or 18 <= l.hour < 22) else b
    return out

def main():
    ts = horas_utc(Y0, Y1)
    pv = fv(); assert len(pv) == len(ts), (len(pv), len(ts))
    w_near, v_near = eolica("era5_wind_nearest_41.25_2.0_2014_2023.json")
    w_land, v_land = eolica("era5_wind_land_41.5_2.0_2014_2023.json")
    assert len(w_near) == len(ts)
    ts_p = horas_utc(2019, 2025); pm = omie()
    precio = np.array([pm.get(int(u), np.nan) for u in ts_p])
    nan = np.isnan(precio); precio[nan] = np.interp(np.flatnonzero(nan), np.flatnonzero(~nan), precio[~nan])
    ppa_fv, ppa_eol = perfil_nacional(ts_p)
    for a in (ppa_fv, ppa_eol):
        m = (anio_p_tmp := np.array([dt.datetime.fromtimestamp(int(u), dt.timezone.utc).year for u in ts_p])) >= 2024
        bad = m & np.isnan(a); good = m & ~np.isnan(a)
        a[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(good), a[good])
    anio = np.array([dt.datetime.fromtimestamp(int(u), dt.timezone.utc).year for u in ts])
    anio_p = np.array([dt.datetime.fromtimestamp(int(u), dt.timezone.utc).year for u in ts_p])
    np.savez_compressed(D / "series_horarias.npz", ts=ts, anio=anio, fv_kw_kwp=pv, eol_cf_cercana=w_near, eol_cf_tierra=w_land,
                        v100_cercana=v_near, v100_tierra=v_land, ts_precio=ts_p, anio_precio=anio_p, omie_eur_mwh=precio,
                        periodo_precio=periodo_61td(ts_p), ppa_fv_cf_nacional=ppa_fv, ppa_eol_cf_nacional=ppa_eol, precio_huecos_rellenos=int(nan.sum()))
    print("horas", len(ts), "| CF FV", round(pv.mean(), 4), "| CF eol cercana", round(w_near.mean(), 4), "tierra", round(w_land.mean(), 4))
    for y in range(Y0, Y1 + 1):
        s = anio == y; print(y, "FV", round(pv[s].mean(), 4), "eol", round(w_near[s].mean(), 4), "v100", round(v_near[s].mean(), 2))
    for y in range(2019, 2026):
        s = anio_p == y; print(y, "OMIE media", round(precio[s].mean(), 1), "min", round(precio[s].min(), 1), "max", round(precio[s].max(), 1))
    print("huecos precio rellenados", int(nan.sum()))
    for y in (2024, 2025):
        s = anio_p == y; print(y, "CF nacional FV", round(np.nanmean(ppa_fv[s]), 4), "eolica", round(np.nanmean(ppa_eol[s]), 4))

if __name__ == "__main__":
    main()
