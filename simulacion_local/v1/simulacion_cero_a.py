#!/usr/bin/env python3
"""
CERO-A - Simulacion base de prototipo piloto Power-to-Ammonia (evidencia E2: validacion de concepto).
Cadena: renovable (FV + eolica, perfil horario sintetico anual) -> electrolizador PEM -> buffer H2
        -> N2 por PSA -> lazo Haber-Bosch (conversion por paso + recirculacion + purga) -> almacen NH3.

Reproducible: semillas fijas. Ejecutar:  .venv/bin/python simulacion_cero_a.py
Salidas: resultados.json, informe.md (lo escribe a mano el equipo a partir de resultados.json),
         grafico_sensibilidad.png
IMPORTANTE: modelo de balance horario (no dinamico, no termodinamico detallado). Sin datos experimentales.
"""
import json, math, time
from pathlib import Path
import numpy as np

OUT = Path(__file__).resolve().parent
HOURS = 8760

# ---------------------------------------------------------------------------
# Constantes fisicas (estequiometria; no son supuestos)
M_H2, M_N2, M_NH3 = 2.01588, 28.0134, 17.03052          # g/mol
H2_STOICH = 1.5 * M_H2 / M_NH3                           # kg H2 / kg NH3  (0.1776)
N2_STOICH = 0.5 * M_N2 / M_NH3                           # kg N2 / kg NH3  (0.8225)
LHV_H2_KWH = 33.33                                       # kWh/kg (120 MJ/kg)
LHV_NH3_KWH = 18.6 / 3.6                                 # kWh/kg (18.6 MJ/kg)
DH_NH3_KWH = 45.9 / M_NH3 / 3.6                          # calor de reaccion liberado, kWh/kg NH3 (dHf gas -45.9 kJ/mol)
RHO_N2_NM3 = 1.2506                                      # kg/Nm3 (0 C, 1 atm)
R = 8.314

# ---------------------------------------------------------------------------
# Supuestos parametrizados: base, rango [min, max], fuente. Rangos = incertidumbre (E2).
P = {
 "e_electrolizador_kwh_kg_h2": dict(base=55.0, min=50.0, max=65.0, unidad="kWh/kg H2 (sistema)",
    fuente="IRENA (2020) Green Hydrogen Cost Reduction, Tabla KPI PEM 2020: sistema 50-83 kWh/kg; estado del arte 52-56 kWh/kg (KEROGREEN/ LUT 2022). Se acota a 50-65 (equipos actuales)."),
 "carga_min_electrolizador": dict(base=0.05, min=0.05, max=0.10, unidad="fraccion de potencia nominal",
    fuente="IRENA (2020): rango de carga PEM 5-120 %; OIES EL47 (2022): carga parcial 0-10 %."),
 "conversion_por_paso_hb": dict(base=0.15, min=0.10, max=0.25, unidad="fraccion H2 convertida por paso",
    fuente="Rouwenhorst et al. (2021) citado en Wang et al., iScience 25 (2022) 104724: conversion por paso 10-15 % en HB industrial; hasta ~25 % segun presion (Appl, Ullmann's)."),
 "conversion_global_lazo": dict(base=0.98, min=0.97, max=0.99, unidad="fraccion (con recirculacion y purga)",
    fuente="Rouwenhorst et al. (2021) via Wang et al. (2022): conversion total 97-99 % con recirculacion."),
 "e_lazo_hb_kwh_kg_nh3": dict(base=2.0, min=0.64, max=3.62, unidad="kWh/kg NH3 (compresion syngas + recirculacion + refrigeracion)",
    fuente="Rouwenhorst et al., RSER 114 (2019) 109339: planta pequena (Cussler) 3.62 kWh/kg; NFUEL ~2 kWh/kg sintesis; Ikaheimo et al., IJHE 43 (2018): 0.64 kWh/kg (gran escala). Base 2.0 = escala piloto."),
 "e_psa_kwh_nm3_n2": dict(base=0.45, min=0.30, max=0.60, unidad="kWh/Nm3 N2 (incl. compresor de aire)",
    fuente="Messer, ficha PSA (99.9 % N2): 0.3-0.6 kWh/Nm3, rango operativo 80-100 %."),
 "cf_fv": dict(base=0.19, min=0.17, max=0.21, unidad="factor de capacidad anual",
    fuente="REE, Informe Renovables 2023: 37.3 TWh FV con ~22.5 GW -> ~18.9 % (estimacion derivada; depende del emplazamiento)."),
 "cf_eolica": dict(base=0.23, min=0.20, max=0.30, unidad="factor de capacidad anual",
    fuente="IEA Wind TCP, Spain 2023: CF eolica terrestre 23.3 %; emplazamientos buenos >= 30 %."),
 "carga_min_hb": dict(base=0.40, min=0.20, max=0.60, unidad="fraccion de capacidad nominal",
    fuente="Armijo & Philibert, IJHE 45 (2020) 1541: 20 %; Fasihi et al., Appl. Energy 294 (2021): 20 %; ICAE 2021 (Australia): 40 % flexible; IEA 'normal' 60 %; Cheema & Krewer, RSC Adv. 8 (2018) 34926."),
 "rampa_hb_frac_h": dict(base=0.20, min=0.10, max=0.30, unidad="fraccion nominal por hora",
    fuente="Evaluating the Economic Potential for Green Ammonia Production in Australia, ICAE 2021: HB flexible 40 % min y 20 %/h."),
 "eficiencia_compresor_h2": dict(base=0.60, min=0.50, max=0.75, unidad="eficiencia isoterma",
    fuente="Trabajo isotermo ideal 30->200 bar (~0.45 kWh/kg) / eficiencia; contraste: DOE Program Record 9013 (2-4 kWh/kg a 350 bar). Rango = supuesto."),
}
# Parametros de diseno del piloto (decisiones de diseno, NO datos de literatura)
DISENO = dict(
    p_electrolizador_kw=1000.0, p_fv_kwp=1500.0, p_eolica_kw=1000.0,
    nh3_nominal_kg_h=50.0,              # ~1.2 t/d
    buffer_h_nominal=12.0,              # horas de consumo H2 nominal del HB
    p_electrolizador_bar=30.0, p_buffer_max_bar=200.0,
    latitud_deg=40.0,                   # emplazamiento generico peninsula iberica
    tau_control_h=6.0, objetivo_soc=0.3,      # politica de control heuristica (decision de modelo)
    arranque_buffer_h_min=4.0, min_parada_h=1,
    respaldo_red_auxiliares=True,       # piloto conectado: red solo para auxiliares HB+PSA (contabilizado)
)

def base_params():
    d = {k: v["base"] for k, v in P.items()}; d.update(DISENO); return d

# ---------------------------------------------------------------------------
def perfil_fv(cf_obj, lat, rng):
    h = np.arange(HOURS); doy = h // 24 + 1; hod = h % 24 + 0.5
    dec = math.radians(23.45) * np.sin(2 * np.pi * (284 + doy) / 365)
    ha = np.radians(15 * (hod - 12)); la = math.radians(lat)
    cosz = np.sin(la) * np.sin(dec) + np.cos(la) * np.cos(dec) * np.cos(ha)
    clear = np.clip(cosz, 0, None) ** 1.15
    # nubosidad diaria AR(1) (indice de claridad) + ruido horario
    kd = np.empty(365); x = 0.0
    for d in range(365):
        x = 0.7 * x + rng.normal(0, 1); kd[d] = x
    kd = 1 / (1 + np.exp(-(kd * 1.2 + 1.2)))
    k = np.repeat(kd, 24) * np.clip(1 + 0.08 * rng.normal(size=HOURS), 0.5, 1.2)
    raw = clear * k
    lo, hi = 0.1, 20.0
    for _ in range(50):
        s = (lo + hi) / 2
        if np.clip(raw * s, 0, 1).mean() < cf_obj: lo = s
        else: hi = s
    return np.clip(raw * s, 0, 1)

def curva_eolica(v):
    p = np.where((v >= 3) & (v < 12), ((v - 3) / 9) ** 3, 0.0)
    return np.where((v >= 12) & (v < 25), 1.0, p)

def perfil_eolico(cf_obj, rng):
    # Rayleigh (Weibull k=2) con autocorrelacion horaria via AR(1) gaussiano en 2 componentes
    a = 0.97; z = np.empty((HOURS, 2)); x = rng.normal(size=2)
    e = rng.normal(size=(HOURS, 2))
    for t in range(HOURS):
        x = a * x + math.sqrt(1 - a * a) * e[t]; z[t] = x
    base = np.sqrt((z ** 2).sum(1) / 2)          # media ~0.886 -> Rayleigh unitario
    diurno = 1 + 0.08 * np.sin(2 * np.pi * (np.arange(HOURS) % 24 - 9) / 24)
    lo, hi = 1.0, 25.0
    for _ in range(50):
        s = (lo + hi) / 2
        if curva_eolica(base * diurno * s).mean() < cf_obj: lo = s
        else: hi = s
    return curva_eolica(base * diurno * s)

def perfiles(cf_fv, cf_eol, lat, seed):
    rng = np.random.default_rng(seed)
    return perfil_fv(cf_fv, lat, rng), perfil_eolico(cf_eol, rng)

# ---------------------------------------------------------------------------
def simular(p, pv=None, wd=None, seed=1, serie=False):
    if pv is None: pv, wd = perfiles(p["cf_fv"], p["cf_eolica"], p["latitud_deg"], seed)
    Pren = pv * p["p_fv_kwp"] + wd * p["p_eolica_kw"]
    X, eta = p["conversion_por_paso_hb"], p["conversion_global_lazo"]
    purga = X * (1 - eta) / (eta * (1 - X))                      # fraccion del no convertido purgada
    recic = (1 - purga) * (1 - X) / (X + purga * (1 - X))        # kmol recirculado / kmol alimentacion fresca
    h2_in_kg_nh3 = H2_STOICH / eta; n2_in_kg_nh3 = N2_STOICH / eta
    e_aux_kg_nh3 = p["e_lazo_hb_kwh_kg_nh3"] + p["e_psa_kwh_nm3_n2"] * n2_in_kg_nh3 / RHO_N2_NM3
    aux_por_h2 = e_aux_kg_nh3 / h2_in_kg_nh3                     # kWh por kg H2 alimentado al HB
    r_nom = p["nh3_nominal_kg_h"] * h2_in_kg_nh3
    r_min = p["carga_min_hb"] * r_nom; ramp = p["rampa_hb_frac_h"] * r_nom
    Bcap = p["buffer_h_nominal"] * r_nom
    ec = R * 293.15 * math.log(p["p_buffer_max_bar"] / p["p_electrolizador_bar"]) / (M_H2 / 1000) / 3.6e6 / p["eficiencia_compresor_h2"]
    eel = p["e_electrolizador_kwh_kg_h2"]; Pn = p["p_electrolizador_kw"]; pmin = p["carga_min_electrolizador"] * Pn
    grid = p["respaldo_red_auxiliares"]

    def g(P_av):  # produccion potencial de H2 con potencia disponible
        pe = min(Pn, max(P_av, 0.0)); return pe / eel if pe >= pmin else 0.0

    B = Bcap * p["objetivo_soc"]; B0 = B; on = False; r = 0.0; off_h = 99; starts = 0
    acc = dict(h2_prod=0, h2_hb=0, e_el=0, e_comp=0, e_aux=0, e_grid=0, e_ren_usada=0, horas_hb=0, horas_el=0)
    nh3_h = np.zeros(HOURS); ser = {k: np.zeros(HOURS) for k in ("buffer", "r_hb", "p_el")} if serie else None
    for t in range(HOURS):
        Pr = Pren[t]
        # 1) decision HB
        if on:
            g0 = g(Pr - aux_por_h2 * r if not grid else Pr - min(Pr, aux_por_h2 * r))
            des = g0 + ((B - Bcap * p["objetivo_soc"]) / p["tau_control_h"] if Bcap > 0 else 0.0)
            lo, hi = max(r_min, r - ramp), min(r_nom, r + ramp)
            rn = min(max(des, lo), hi)
            if B + g0 - rn < 0: rn = max(B + g0, r_min)            # bajada de emergencia hasta carga minima
            if B + g0 - rn < -1e-9 or (not grid and Pr < aux_por_h2 * rn):
                on, r, off_h = False, 0.0, 0
            else: r = rn
        else:
            off_h += 1
            g0 = g(Pr - (0 if grid else aux_por_h2 * r_min))
            ok_buf = (B >= min(p["arranque_buffer_h_min"] * r_min, 0.8 * Bcap)) if Bcap > 0 else (g0 >= r_min)
            if off_h >= p["min_parada_h"] and ok_buf and B + g0 - r_min >= 0 and (grid or Pr >= aux_por_h2 * r_min):
                on, r = True, r_min; starts += 1
        # 2) potencia auxiliares y electrolizador (+compresion al buffer)
        aux = aux_por_h2 * r
        from_ren = min(Pr, aux); imp = aux - from_ren
        Pav = Pr - from_ren
        room = Bcap - B + r
        prod = min(Pn / eel, room, Pav / eel)
        if prod > r: prod = min(prod, (Pav + ec * r) / (eel + ec))
        prod = max(prod, 0.0)
        if prod * eel < pmin: prod = 0.0
        if B + prod - r < -1e-9:                                   # correccion final
            r = B + prod if B + prod >= r_min else 0.0
            if r == 0.0: on, off_h = False, 0
            aux = aux_por_h2 * r; from_ren = min(Pr, aux); imp = aux - from_ren
        comp = ec * max(prod - r, 0.0)
        B = min(max(B + prod - r, 0.0), Bcap)
        acc["h2_prod"] += prod; acc["h2_hb"] += r; acc["e_el"] += prod * eel; acc["e_comp"] += comp
        acc["e_aux"] += aux; acc["e_grid"] += imp; acc["e_ren_usada"] += prod * eel + comp + from_ren
        acc["horas_hb"] += r > 0; acc["horas_el"] += prod > 0
        nh3_h[t] = r / h2_in_kg_nh3
        if serie: ser["buffer"][t], ser["r_hb"][t], ser["p_el"][t] = B, r, prod * eel
    nh3 = nh3_h.sum(); e_ren = Pren.sum()
    e_tot = acc["e_el"] + acc["e_comp"] + acc["e_aux"]
    dev = np.cumsum(nh3_h - nh3_h.mean())
    res = dict(
        nh3_t_ano=nh3 / 1000, consumo_especifico_kwh_kg_nh3=e_tot / nh3 if nh3 else float("nan"),
        consumo_electrolisis_kwh_kg_nh3=acc["e_el"] / nh3 if nh3 else float("nan"),
        cf_renovable=e_ren / (HOURS * (p["p_fv_kwp"] + p["p_eolica_kw"])), cf_fv_real=pv.mean(), cf_eolica_real=wd.mean(),
        cf_electrolizador=acc["e_el"] / (Pn * HOURS), cf_hb=nh3 / (p["nh3_nominal_kg_h"] * HOURS),
        horas_hb=int(acc["horas_hb"]), arranques_hb=starts, vertido_frac=1 - acc["e_ren_usada"] / e_ren,
        import_red_mwh=acc["e_grid"] / 1000, cuota_renovable=1 - acc["e_grid"] / e_tot,
        eficiencia_lhv_ptx=nh3 * LHV_NH3_KWH / e_tot if e_tot else float("nan"),
        tanque_nh3_t_offtake_constante=(dev.max() - dev.min()) / 1000,
        balance_masa_t=dict(h2_producido=acc["h2_prod"] / 1000, h2_al_hb=acc["h2_hb"] / 1000,
            h2_purgado=(acc["h2_hb"] - nh3 * H2_STOICH) / 1000, delta_buffer_h2=(B - B0) / 1000,
            n2_al_hb=nh3 * n2_in_kg_nh3 / 1000, n2_purgado=nh3 * (n2_in_kg_nh3 - N2_STOICH) / 1000,
            agua_estequiometrica=acc["h2_prod"] * 18.015 / M_H2 / 1000, o2_subproducto=acc["h2_prod"] * 7.937 / 1000,
            nh3=nh3 / 1000, cierre_h2_kg=acc["h2_prod"] - acc["h2_hb"] - (B - B0)),
        balance_energia_mwh=dict(renovable_generada=e_ren / 1000, vertida=(e_ren - acc["e_ren_usada"]) / 1000,
            electrolizador=acc["e_el"] / 1000, compresion_buffer=acc["e_comp"] / 1000,
            lazo_hb=nh3 * p["e_lazo_hb_kwh_kg_nh3"] / 1000, psa_n2=(acc["e_aux"] - nh3 * p["e_lazo_hb_kwh_kg_nh3"]) / 1000,
            importada_red=acc["e_grid"] / 1000, lhv_h2_producido=acc["h2_prod"] * LHV_H2_KWH / 1000,
            lhv_nh3=nh3 * LHV_NH3_KWH / 1000, calor_reaccion_hb=nh3 * DH_NH3_KWH / 1000,
            lhv_h2_purgado=(acc["h2_hb"] - nh3 * H2_STOICH) * LHV_H2_KWH / 1000),
        lazo=dict(fraccion_purga=purga, ratio_recirculacion_molar=recic, buffer_kg_h2=Bcap, e_compresion_kwh_kg_h2=ec),
    )
    if serie: res["_serie"] = ser; res["_pren"] = Pren
    return res

# ---------------------------------------------------------------------------
def pct(a, q): return float(np.nanpercentile(a, q))

def main():
    t0 = time.time(); bp = base_params(); SEEDS = [11, 22, 33, 44, 55]
    base_runs = [simular(bp, seed=s) for s in SEEDS]
    base = simular(bp, seed=SEEDS[0], serie=True)
    isla = dict(bp, respaldo_red_auxiliares=False); isla_runs = [simular(isla, seed=s) for s in SEEDS]

    def media(runs, k): return float(np.mean([r[k] for r in runs]))
    def sweep(key, vals, extra=None):
        out = []
        for v in vals:
            q = dict(bp, **(extra or {})); q[key] = v
            prof = [perfiles(q["cf_fv"], q["cf_eolica"], q["latitud_deg"], s) for s in SEEDS]
            rs = [simular(q, pv, wd) for pv, wd in prof]
            out.append(dict(valor=v, nh3_t_ano=media(rs, "nh3_t_ano"), consumo_especifico_kwh_kg_nh3=media(rs, "consumo_especifico_kwh_kg_nh3"),
                            cf_hb=media(rs, "cf_hb"), arranques_hb=media(rs, "arranques_hb"), vertido_frac=media(rs, "vertido_frac")))
        return out
    sens = {
        "e_electrolizador_kwh_kg_h2": sweep("e_electrolizador_kwh_kg_h2", [50, 52.5, 55, 57.5, 60, 62.5, 65]),
        "buffer_h_nominal": {f"carga_min_{m:.1f}": sweep("buffer_h_nominal", [0, 2, 4, 8, 12, 24, 48, 72], {"carga_min_hb": m}) for m in (0.2, 0.4, 0.6)},
        "carga_min_hb": {f"buffer_{b}h": sweep("carga_min_hb", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0], {"buffer_h_nominal": b}) for b in (4, 12, 48)},
    }
    pol = []
    for soc in (0.15, 0.3, 0.5):
        for tau in (6.0, 12.0):
            for m in (0.2, 0.4, 0.6):
                q = dict(bp, objetivo_soc=soc, tau_control_h=tau, carga_min_hb=m)
                rs = [simular(q, seed=s) for s in SEEDS]
                pol.append(dict(objetivo_soc=soc, tau_control_h=tau, carga_min_hb=m, nh3_t_ano=media(rs, "nh3_t_ano"), arranques_hb=media(rs, "arranques_hb")))
    sens["politica_control_hb"] = pol
    # Monte Carlo (propagacion de incertidumbre, distribucion triangular min/base/max, semilla meteo aleatoria)
    rng = np.random.default_rng(2026); N = 200; mc = []
    for i in range(N):
        q = dict(bp)
        for k, v in P.items(): q[k] = float(rng.triangular(v["min"], v["base"], v["max"]))
        mc.append(simular(q, seed=int(rng.integers(1e6))) | {"_q": q})
    keys = ["nh3_t_ano", "consumo_especifico_kwh_kg_nh3", "cf_hb", "cf_electrolizador", "vertido_frac", "eficiencia_lhv_ptx", "arranques_hb"]
    mc_res = {k: dict(p5=pct([m[k] for m in mc], 5), p50=pct([m[k] for m in mc], 50), p95=pct([m[k] for m in mc], 95)) for k in keys}
    # importancia (correlacion de rangos de Spearman) sobre produccion y consumo especifico
    def spearman(x, y):
        rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y)); return float(np.corrcoef(rx, ry)[0, 1])
    imp = {out: {k: round(spearman([m["_q"][k] for m in mc], [m[out] for m in mc]), 3) for k in P} for out in ("nh3_t_ano", "consumo_especifico_kwh_kg_nh3")}

    grafico(base, sens)
    b0 = {k: v for k, v in base.items() if not k.startswith("_")}
    rb = lambda k, runs: dict(media=media(runs, k), min=min(r[k] for r in runs), max=max(r[k] for r in runs))
    resultados = construir_json(bp, b0, base_runs, isla_runs, sens, mc_res, imp, rb, N, SEEDS, time.time() - t0)
    (OUT / "resultados.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2, default=lambda o: float(o)))
    print(json.dumps({"base": {k: b0[k] for k in ("nh3_t_ano", "consumo_especifico_kwh_kg_nh3", "cf_renovable", "cf_electrolizador", "cf_hb", "arranques_hb", "vertido_frac", "cuota_renovable", "eficiencia_lhv_ptx")},
                      "isla": {k: media(isla_runs, k) for k in ("nh3_t_ano", "cf_hb", "arranques_hb", "consumo_especifico_kwh_kg_nh3")},
                      "mc": mc_res, "importancia": imp, "balances": {"masa": b0["balance_masa_t"], "energia": b0["balance_energia_mwh"], "lazo": b0["lazo"]},
                      "tanque": b0["tanque_nh3_t_offtake_constante"], "s": time.time() - t0}, indent=1, default=float))

def grafico(base, sens):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))
    a = ax[0, 0]; h = np.arange(24 * 7) + 24 * 170   # semana de junio
    s = base["_serie"]
    a.plot(h - h[0], base["_pren"][h], label="Renovable [kW]", color="orange")
    a.plot(h - h[0], s["p_el"][h], label="Electrolizador [kW]", color="tab:blue")
    a2 = a.twinx(); a2.plot(h - h[0], s["buffer"][h], color="green", ls="--", label="Buffer H2 [kg]")
    a2.plot(h - h[0], s["r_hb"][h] * 10, color="k", lw=1, label="HB alimentacion H2 x10 [kg/h]")
    a.set_title("Operacion caso base (semana de verano, perfil sintetico)"); a.set_xlabel("h"); a.legend(loc="upper left", fontsize=7); a2.legend(loc="upper right", fontsize=7)
    a = ax[0, 1]; d = sens["e_electrolizador_kwh_kg_h2"]
    a.plot([x["valor"] for x in d], [x["nh3_t_ano"] for x in d], "o-", label="NH3 [t/a]")
    a.set_xlabel("Electrolizador [kWh/kg H2]"); a.set_ylabel("NH3 [t/a]"); a.set_title("Sensibilidad: eficiencia electrolizador")
    a3 = a.twinx(); a3.plot([x["valor"] for x in d], [x["consumo_especifico_kwh_kg_nh3"] for x in d], "s--", color="tab:red"); a3.set_ylabel("kWh/kg NH3", color="tab:red")
    a = ax[1, 0]
    for k, d in sens["buffer_h_nominal"].items():
        a.plot([x["valor"] for x in d], [x["nh3_t_ano"] for x in d], "o-", label=k.replace("carga_min_", "carga min HB "))
    a.set_xscale("symlog", linthresh=2); a.set_xlabel("Buffer H2 [h de consumo nominal HB]"); a.set_ylabel("NH3 [t/a]"); a.set_title("Sensibilidad: tamano buffer"); a.legend(fontsize=8)
    a = ax[1, 1]
    for k, d in sens["carga_min_hb"].items():
        a.plot([x["valor"] * 100 for x in d], [x["nh3_t_ano"] for x in d], "o-", label=k.replace("buffer_", "buffer "))
    a4 = a.twinx()
    for k, d in sens["carga_min_hb"].items():
        a4.plot([x["valor"] * 100 for x in d], [x["arranques_hb"] for x in d], ":", marker="x")
    a4.set_ylabel("Arranques HB/ano (punteado)")
    a.set_xlabel("Carga minima HB [%]"); a.set_ylabel("NH3 [t/a] (continuo)"); a.set_title("Sensibilidad: carga minima HB (sin penalizar arranques)"); a.legend(fontsize=8, loc="center left")
    fig.suptitle("CERO-A piloto P2A (E2, simulacion sin datos experimentales) - media de 5 anos meteo sinteticos", fontsize=11)
    fig.tight_layout(); fig.savefig(OUT / "grafico_sensibilidad.png", dpi=130)

def construir_json(bp, b0, base_runs, isla_runs, sens, mc_res, imp, rb, N, SEEDS, dt):
    r3 = lambda x: round(float(x), 3)
    return {
      "meta": {"proyecto": "cero_a", "nivel_evidencia": "e2_validacion_concepto", "tipo": "simulacion_base_prototipo_piloto",
               "fecha": "2026-10-18", "script": "simulacion_cero_a.py", "semillas_meteo": SEEDS, "n_monte_carlo": N,
               "tiempo_ejecucion_s": round(dt, 1), "datos_experimentales": [], "advertencia": "resultados de modelo con supuestos de literatura; no validados experimentalmente"},
      "objetivo": "estimar balances de masa y energia, consumo especifico, produccion anual y factores de capacidad de un piloto fv+eolica -> pem -> buffer h2 -> psa n2 -> haber-bosch -> nh3, e identificar parametros criticos para pasar de e2 a e3",
      "datos_clave": {
        "diseno_piloto": {k: v for k, v in DISENO.items()},
        "supuestos": [{"parametro": k, "base": v["base"], "rango": [v["min"], v["max"]], "unidad": v["unidad"], "fuente": v["fuente"]} for k, v in P.items()],
        "resultado_base_semilla_11": {k: (r3(v) if isinstance(v, (int, float)) else {kk: r3(vv) for kk, vv in v.items()}) for k, v in b0.items()},
        "variabilidad_meteo_base_5_semillas": {k: {kk: r3(vv) for kk, vv in rb(k, base_runs).items()} for k in ("nh3_t_ano", "consumo_especifico_kwh_kg_nh3", "cf_hb", "arranques_hb")},
        "escenario_aislado_sin_red": {k: {kk: r3(vv) for kk, vv in rb(k, isla_runs).items()} for k in ("nh3_t_ano", "consumo_especifico_kwh_kg_nh3", "cf_hb", "arranques_hb")},
        "monte_carlo_p5_p50_p95": {k: {kk: r3(vv) for kk, vv in v.items()} for k, v in mc_res.items()},
        "importancia_spearman": imp,
        "sensibilidad": sens,
      },
      "tareas": [
        {"id": "t1", "tarea": "sustituir perfiles sinteticos por series horarias reales del emplazamiento (pvgis / era5)", "estado": "pendiente"},
        {"id": "t2", "tarea": "obtener curva de eficiencia a carga parcial del pem y del psa de proveedor", "estado": "pendiente"},
        {"id": "t3", "tarea": "modelo cinetico/termico del lazo hb a baja carga (temperatura lecho, autotermia, arranques)", "estado": "pendiente"},
        {"id": "t4", "tarea": "optimizar dimensionado conjunto (renovable/electrolizador/buffer/hb/bateria) con costes", "estado": "pendiente"},
        {"id": "t5", "tarea": "disenar campana experimental minima para e3 (rampa y carga minima hb, deoxo n2)", "estado": "pendiente"},
      ],
      "riesgos": [
        {"riesgo": "carga minima y rampa del hb a escala piloto no demostradas; domina la produccion", "impacto": "alto", "mitigacion": "ensayo dedicado; buffer >= 12 h"},
        {"riesgo": "consumo del lazo hb a pequena escala muy incierto (0.64-3.62 kWh/kg nh3)", "impacto": "medio", "mitigacion": "datos de proveedor de lazo modular"},
        {"riesgo": "operacion aislada: auxiliares sin renovable de noche provocan paradas del hb", "impacto": "alto", "mitigacion": "respaldo de red o bateria para auxiliares"},
        {"riesgo": "psa con rango operativo 80-100 % (messer) no sigue la carga del hb; o2 residual envenena catalizador", "impacto": "medio", "mitigacion": "psa modular + buffer n2 + deoxo"},
        {"riesgo": "perfiles renovables sinteticos calibrados solo en factor de capacidad", "impacto": "medio", "mitigacion": "tarea t1"},
      ],
      "decisiones": [
        {"decision": "piloto de 1 mw pem, 1.5 mwp fv, 1 mw eolica, hb 50 kg/h nh3", "tipo": "supuesto_de_diseno", "estado": "provisional"},
        {"decision": "respaldo de red solo para auxiliares hb+psa en caso base; escenario aislado como alternativa", "tipo": "supuesto_de_diseno", "estado": "provisional"},
        {"decision": "eficiencias constantes con la carga (sin curvas de carga parcial)", "tipo": "simplificacion", "estado": "provisional"},
      ],
      "proximo_paso": "ejecutar t1 (series reales del emplazamiento) y t4 (dimensionado con costes) para fijar buffer y carga minima objetivo del hb; despues definir el ensayo experimental e3",
    }

if __name__ == "__main__":
    main()
