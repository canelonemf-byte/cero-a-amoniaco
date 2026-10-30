#!/usr/bin/env python3
"""
CERO-A v2 - Piloto Power-to-Ammonia en El Prat de Llobregat (41.30 N, 2.08 E), evidencia E2 (sin datos experimentales).
Series horarias reales (PVGIS-SARAH3/ERA5, ERA5 viento via Open-Meteo, OMIE via Energy-Charts; ver datos_cero_a.py),
modelo de costes LCOA con rangos, optimizacion del dimensionado (evolucion diferencial) por escenario de suministro,
penalizacion de arranques del HB, Monte Carlo P5-P95 y comparacion con amoniaco gris.
Ejecutar:  .venv/bin/python datos_cero_a.py && .venv/bin/python simulacion_cero_a_v2.py
"""
import json, math, time
from pathlib import Path
import numpy as np
from numba import njit
from scipy.optimize import differential_evolution

OUT = Path(__file__).resolve().parent
S = np.load(OUT / "data" / "series_horarias.npz")
M_H2, M_N2, M_NH3 = 2.01588, 28.0134, 17.03052
H2_STOICH = 1.5 * M_H2 / M_NH3; N2_STOICH = 0.5 * M_N2 / M_NH3
LHV_NH3_KWH = 18.6 / 3.6; RHO_N2_NM3 = 1.2506; R = 8.314
USD_EUR = 1 / 1.0824   # BCE, media 2024 USD/EUR = 1.0824

def T(base, lo, hi, unidad, fuente): return dict(base=base, min=lo, max=hi, unidad=unidad, fuente=fuente)
# ----------------------------------------------------------------------------- supuestos tecnicos
PT = {
 "e_electrolizador_kwh_kg_h2": T(55.0, 50.0, 65.0, "kWh/kg H2", "IRENA (2020) KPI PEM sistema 50-83; estado del arte 52-56"),
 "carga_min_electrolizador": T(0.05, 0.05, 0.10, "fraccion", "IRENA (2020) 5-120 %; OIES EL47 (2022) 0-10 %"),
 "conversion_global_lazo": T(0.98, 0.97, 0.99, "fraccion", "Rouwenhorst et al. 2021 via Wang et al. iScience 2022"),
 "e_lazo_hb_kwh_kg_nh3": T(2.0, 0.64, 3.62, "kWh/kg NH3", "Rouwenhorst et al. RSER 2019 (3.62 pequena escala; NFUEL ~2); Ikaheimo et al. IJHE 2018 (0.64)"),
 "e_psa_kwh_nm3_n2": T(0.45, 0.30, 0.60, "kWh/Nm3", "Messer, ficha PSA 99.9 %"),
 "rampa_hb_frac_h": T(0.20, 0.10, 0.30, "fraccion/h", "ICAE 2021 (Australia): HB flexible 20 %/h"),
 "eficiencia_compresor_h2": T(0.60, 0.50, 0.75, "isoterma", "supuesto; contraste DOE Record 9013"),
 "rte_bateria": T(0.85, 0.80, 0.90, "fraccion", "NREL ATB 2024: 85 % (rango supuesto)"),
 "h_perdidas_arranque_hb": T(6.0, 2.0, 12.0, "h a carga minima sin NH3 por arranque", "SUPUESTO sin fuente cuantitativa (calentamiento/estabilizacion); rango amplio"),
 "min_parada_hb_h": T(6.0, 1.0, 24.0, "h", "SUPUESTO; Joule 2023 (dynamic operation) usa paradas planificadas >= 3 dias"),
}
# ----------------------------------------------------------------------------- supuestos economicos (EUR 2024)
u = USD_EUR
PE = {
 "capex_fv_eur_kwp": T(800, 671 * u, 1000, "EUR/kWp", "IRENA RPGC 2023: Espana FV utility 671 USD/kW (2023); prima escala piloto = supuesto"),
 "om_fv_eur_kwp_a": T(12, 10.3 * u, 18, "EUR/kWp/a", "IRENA RPGC 2023: O&M FV global 10.3 USD/kW/a; prima piloto = supuesto"),
 "capex_eol_eur_kw": T(1400, 1160 * u, 1800, "EUR/kW", "IRENA RPGC 2023: eolica terrestre global 1160 USD/kW; prima Europa/turbina pequena = supuesto"),
 "om_eol_eur_kw_a": T(40, 30, 50, "EUR/kW/a", "rango SUPUESTO (orden de magnitud NREL ATB eolica terrestre)"),
 "capex_pem_eur_kw": T(2450 * u, 1900 * u, 3000, "EUR/kW instalado (incl. EPC)", "IEA GHR 2024: 2000-2450 USD/kW fuera de China (PEM extremo alto); IEA 2025: 1900-2500; max piloto = supuesto"),
 "om_pem_frac": T(0.03, 0.02, 0.04, "fraccion CAPEX/a", "IEA GHR 2024 Assumptions annex: 3 %"),
 "vida_stack_h": T(50000, 50000, 95000, "h", "IEA GHR 2024 annex: 50 000 h (hasta 95 000 h)"),
 "frac_stack_capex": T(0.35, 0.30, 0.45, "fraccion", "IRENA (2020) Green H2 cost reduction: stack 30-45 % del coste"),
 "capex_buffer_eur_kg": T(26 * 33.33, 535, 1000, "EUR/kg H2 util", "Haber-Bosch 2.0, EES 2026, Tabla 2: 26 EUR/kWh (=867 EUR/kg); ENTEC/Fraunhofer 2022: ~535 EUR/kg tanques; max supuesto"),
 "capex_psa_eur": T(183e3, 126e3, 222e3, "EUR (42 kg N2/h)", "EES 2026 Tabla 2: ASU 1720 EUR/(kg N2/h) a 20 t/d, escalado exp. 0.6-0.8 (base 0.67, Malmali et al. Processes 2018)"),
 "capex_hb_eur": T(1.09e6, 0.75e6, 1.9e6, "EUR (50 kg NH3/h)", "EES 2026 Tabla 2: 8600 EUR/(kg NH3/h) a 20 t/d escalado exp 0.6-0.8; max: Malmali et al. 2018 (3 t/d = 3.8 M USD) escalado"),
 "om_hb_psa_frac": T(0.03, 0.02, 0.05, "fraccion CAPEX/a", "Pozo et al. 2022 (3 %); Wang et al. iScience 2022 (5 %)"),
 "capex_bat_eur_kwh": T(400, 273 * u, 525 * u * 1.0, "EUR/kWh (4 h)", "IRENA RPGC 2023: 273 USD/kWh (2023); NREL ATB 2024: 525 USD/kWh (4 h, USD 2022)"),
 "om_bat_frac": T(0.025, 0.02, 0.03, "fraccion CAPEX/a", "NREL ATB 2024 (FOM ~2.5 %); rango supuesto"),
 "wacc": T(0.07, 0.05, 0.10, "real", "SUPUESTO: renovables Europa bajo (IRENA Cost of financing 2023) + prima primera planta"),
 "ppa_fv_eur_mwh": T(33.5, 30.0, 40.0, "EUR/MWh", "LevelTen PPA Index Espana Q3 2025 P25 solar 33.5; Q4 2025 32.5; ofertas < 30"),
 "ppa_eol_eur_mwh": T(53.0, 45.0, 60.0, "EUR/MWh", "LevelTen PPA Index Espana Q3 2025 P25 eolica 53; rango supuesto"),
 "agua_eur_m3": T(2.0, 1.5, 3.0, "EUR/m3", "Wang et al. iScience 2022: 2.15 USD/m3 (Toronto); rango supuesto Barcelona"),
}
VIDA = dict(fv=25, eol=25, pem=20, buffer=20, psa=20, hb=20, bat=15)  # anos (IRENA LCOE 25 a; NREL ATB bateria 15 a; resto = vida proyecto 20 a, supuesto)
# Peajes 6.1TD (Res. CNMC 4-12-2024, BOE-A-2024-26218) + cargos segmento 3 (Orden TED/1487/2024) - 2025, P1..P6
PEAJE_E = np.array([0.027104, 0.011894, 0.004726, 0.002739, 0.000122, 0.000029])
CARGO_E = np.array([0.017674, 0.013092, 0.007069, 0.003535, 0.002266, 0.001414])
PEAJE_P = np.array([23.669055, 12.513915, 4.696330, 3.309245, 0.069965, 0.062286])
CARGO_P = np.array([5.122811, 2.563728, 1.862840, 1.862840, 1.862840, 0.853802])
GRIS = {"gas_gj_t": T(33.0, 28.0, 38.0, "GJ/t NH3", "BAT ~28 GJ/t; media Europa ~36 MMBtu/t (~38 GJ/t) (Nitrogen Signal, CBAM cost stack)"),
        "ttf_eur_mwh": T(34.0, 25.0, 50.0, "EUR/MWh", "ACER/Energy-Charts: TTF media 2024 ~34 EUR/MWh; rango supuesto"),
        "co2_t_t": T(1.8, 1.7, 2.0, "t CO2/t NH3", "Hydrogen Europe Clean Ammonia 2023; DECHEMA: 1.7-2.0"),
        "eua_eur_t": T(65.0, 60.0, 90.0, "EUR/t CO2", "ESMA 2025: media spot EUA 2024 65 EUR/t; rango supuesto"),
        "referencias_mercado": ["QCIntel 2024: coste implicito produccion Europa occidental medio 423 USD/t (2024)",
                                "Argus via Nitrogen Signal: 665 EUR/t excl. capex (abril 2026)",
                                "Haber-Bosch 2.0 EES 2026: amoniaco centralizado ~300 EUR/t historico, picos ~800 EUR/t"]}
AP = [2024, 2025]
NH3_NOM = 50.0  # kg/h, fijo (decision de diseno piloto, igual que v1)

# ----------------------------------------------------------------------------- nucleo de simulacion
@njit(cache=True)
def kernel(P_on, P_ppa, barato, modo, Pn, eel, pmin_frac, ec, r_nom, r_min, ramp, Bcap, soc_obj, tau, arr_h,
           min_parada, h_pen, aux_h2, bat_kwh, rte, eta_loop):
    n = P_on.shape[0]
    nh3 = np.zeros(n); imp = np.zeros(n); sur_on = np.zeros(n); sur_ppa = np.zeros(n); el = np.zeros(n)
    used_ppa = np.zeros(n); Bs = np.zeros(n); rs = np.zeros(n)
    se = math.sqrt(rte); bat_kw = bat_kwh / 4.0
    B = Bcap * soc_obj; soc = 0.5 * bat_kwh; on = False; r = 0.0; off_h = 1000; starts = 0; pen_left = 0.0
    h2_prod = 0.0; comp_tot = 0.0; pmin = pmin_frac * Pn; perdido = 0.0
    for t in range(n):
        own = P_on[t] + P_ppa[t]; gaux = modo >= 1; gel = (modo == 2) and barato[t]
        dis_av = min(bat_kw, soc * se)
        # produccion potencial con HB a tasa rr
        # (auxiliares primero; el electrolizador no se alimenta de bateria)
        if on:
            x = own - aux_h2 * r
            if gel: x = Pn
            x = min(Pn, max(x, 0.0)); g0 = x / eel if x >= pmin else 0.0
            des = g0 + ((B - Bcap * soc_obj) / tau if Bcap > 0 else 0.0)
            lo = max(r_min, r - ramp); hi = min(r_nom, r + ramp)
            rn = min(max(des, lo), hi)
            if B + g0 - rn < 0: rn = max(B + g0, r_min)
            ok = B + g0 - rn >= -1e-9
            if not gaux and own + dis_av < aux_h2 * rn: ok = False
            if ok: r = rn
            else:
                on = False; r = 0.0; off_h = 0
        else:
            off_h += 1
            x = own - aux_h2 * r_min
            if gel: x = Pn
            x = min(Pn, max(x, 0.0)); g0 = x / eel if x >= pmin else 0.0
            okb = (B >= min(arr_h * r_min, 0.8 * Bcap)) if Bcap > 0 else (g0 >= r_min)
            okp = gaux or (own + dis_av >= aux_h2 * r_min)
            if off_h >= min_parada and okb and B + g0 - r_min >= 0 and okp:
                on = True; r = r_min; starts += 1; pen_left = h_pen * r_min
        # suministro auxiliares
        aux = aux_h2 * r
        f_on = min(P_on[t], aux); rem = aux - f_on
        f_ppa = min(P_ppa[t], rem); rem -= f_ppa
        d = min(rem, dis_av); soc -= d / se; rem -= d
        if rem > 1e-9: imp[t] += rem   # solo posible si gaux (comprobado arriba)
        av_on = P_on[t] - f_on; av_ppa = P_ppa[t] - f_ppa
        Pav = av_on + av_ppa + (Pn if gel else 0.0)
        room = Bcap - B + r
        prod = min(Pn / eel, room, Pav / eel)
        if prod > r: prod = min(prod, (Pav + ec * r) / (eel + ec))
        if prod < 0: prod = 0.0
        if prod * eel < pmin: prod = 0.0
        if B + prod - r < -1e-9:
            r2 = B + prod
            if r2 >= r_min: r = r2
            else:
                r = 0.0; on = False; off_h = 0
        comp = ec * max(prod - r, 0.0)
        E = prod * eel + comp
        e_on = min(av_on, E); E -= e_on; e_ppa = min(av_ppa, E); E -= e_ppa
        if E > 1e-9: imp[t] += E
        B = min(max(B + prod - r, 0.0), Bcap)
        s_on = av_on - e_on; s_ppa = av_ppa - e_ppa
        ch = min(bat_kw, (bat_kwh - soc) / se, s_on + s_ppa)
        if ch > 0:
            soc += ch * se; c1 = min(ch, s_on); s_on -= c1; s_ppa -= (ch - c1)
        sur_on[t] = s_on; sur_ppa[t] = s_ppa
        used_ppa[t] = P_ppa[t] - s_ppa
        el[t] = prod * eel; h2_prod += prod; comp_tot += comp
        h2_util = r
        if pen_left > 0:
            q = min(pen_left, r); pen_left -= q; h2_util -= q; perdido += q
        nh3[t] = h2_util * eta_loop / (1.5 * 2.01588 / 17.03052)
        Bs[t] = B; rs[t] = r
    return nh3, imp, sur_on, sur_ppa, used_ppa, el, Bs, rs, starts, h2_prod, comp_tot, perdido

def tec(q):
    eta = q["conversion_global_lazo"]; h2_in = H2_STOICH / eta; n2_in = N2_STOICH / eta
    e_aux = q["e_lazo_hb_kwh_kg_nh3"] + q["e_psa_kwh_nm3_n2"] * n2_in / RHO_N2_NM3
    ec = R * 293.15 * math.log(200 / 30) / (M_H2 / 1000) / 3.6e6 / q["eficiencia_compresor_h2"]
    return eta, h2_in, e_aux / h2_in, ec

def simular(d, q, ser):
    """d: diseno (fv_kwp, eol_kw, ppa_fv_kw, ppa_eol_kw, pem_kw, buffer_h, bat_kwh, carga_min_hb, umbral_eur_mwh, modo)."""
    eta, h2_in, aux_h2, ec = tec(q)
    r_nom = NH3_NOM * h2_in; r_min = d["carga_min_hb"] * r_nom
    P_on = ser["fv"] * d["fv_kwp"] + ser["eol"] * d["eol_kw"]
    P_ppa = ser["ppa_fv"] * d["ppa_fv_kw"] + ser["ppa_eol"] * d["ppa_eol_kw"]
    barato = ser["omie"] <= d["umbral_eur_mwh"]
    o = kernel(P_on, P_ppa, barato, int(d["modo"]), d["pem_kw"], q["e_electrolizador_kwh_kg_h2"], q["carga_min_electrolizador"], ec,
               r_nom, r_min, q["rampa_hb_frac_h"] * r_nom, d["buffer_h"] * r_nom, 0.3, 6.0, 4.0, q["min_parada_hb_h"],
               q["h_perdidas_arranque_hb"], aux_h2, d["bat_kwh"], q["rte_bateria"], eta)
    return dict(zip(["nh3", "imp", "sur_on", "sur_ppa", "used_ppa", "el", "B", "r", "starts", "h2_prod", "comp", "h2_perdido_arranques"], o)), P_on, P_ppa

def crf(i, n): return i * (1 + i) ** n / ((1 + i) ** n - 1)

def lcoa(d, q, ser, detalle=False):
    s, P_on, P_ppa = simular(d, q, ser); ny = ser["anos"]
    nh3 = s["nh3"].sum() / ny
    if nh3 < 1000: return (1e5, None) if detalle else 1e5
    w = q["wacc"]; r_nom_h2 = NH3_NOM * H2_STOICH / q["conversion_global_lazo"]
    c = {}
    c["fv"] = d["fv_kwp"] * (q["capex_fv_eur_kwp"] * crf(w, VIDA["fv"]) + q["om_fv_eur_kwp_a"])
    c["eolica"] = d["eol_kw"] * (q["capex_eol_eur_kw"] * crf(w, VIDA["eol"]) + q["om_eol_eur_kw_a"])
    capem = d["pem_kw"] * q["capex_pem_eur_kw"]
    horas_eq = s["el"].sum() / max(d["pem_kw"], 1) / ny
    c["pem"] = capem * (crf(w, VIDA["pem"]) + q["om_pem_frac"]) + capem * q["frac_stack_capex"] * horas_eq / q["vida_stack_h"]
    c["buffer_h2"] = d["buffer_h"] * r_nom_h2 * q["capex_buffer_eur_kg"] * (crf(w, VIDA["buffer"]) + 0.02)
    c["psa_hb"] = (q["capex_psa_eur"] + q["capex_hb_eur"]) * (crf(w, VIDA["hb"]) + q["om_hb_psa_frac"])
    c["bateria"] = d["bat_kwh"] * q["capex_bat_eur_kwh"] * (crf(w, VIDA["bat"]) + q["om_bat_frac"])
    per = ser["periodo"] - 1
    red_draw = s["imp"] + (s["used_ppa"] if d["modo"] >= 1 else 0)       # energia que pasa fisicamente por la red
    c["red_energia_omie"] = float((s["imp"] * ser["omie"]).sum() / 1000 / ny)
    c["red_peajes_cargos"] = float((red_draw * (PEAJE_E + CARGO_E)[per]).sum() / ny + (red_draw.max() * (PEAJE_P + CARGO_P).sum() if red_draw.max() > 0 else 0))
    c["ppa"] = float((ser["ppa_fv"] * d["ppa_fv_kw"]).sum() / 1000 * q["ppa_fv_eur_mwh"] / ny + (ser["ppa_eol"] * d["ppa_eol_kw"]).sum() / 1000 * q["ppa_eol_eur_mwh"] / ny)
    pf, pe = ser["ppa_fv"] * d["ppa_fv_kw"], ser["ppa_eol"] * d["ppa_eol_kw"]
    p_ppa_h = np.where(pf + pe > 0, (pf * q["ppa_fv_eur_mwh"] + pe * q["ppa_eol_eur_mwh"]) / np.maximum(pf + pe, 1e-9), 0.0)
    c["venta_excedentes"] = -float((s["sur_ppa"] * np.minimum(ser["omie"], p_ppa_h)).sum() / 1000 / ny)   # reventa PPA: credito <= precio PPA (sin arbitraje)
    if d["modo"] >= 1 and d["exporta"]:
        c["venta_excedentes"] -= float((s["sur_on"] * ser["omie"]).sum() / 1000 / ny)
    c["agua"] = s["h2_prod"] / ny * 9.0 / 1000 * q["agua_eur_m3"]
    tot = sum(c.values()); L = tot / (nh3 / 1000)
    if not detalle: return L
    E_tot = s["el"].sum() + s["comp"] + (q["e_lazo_hb_kwh_kg_nh3"] + q["e_psa_kwh_nm3_n2"] * N2_STOICH / q["conversion_global_lazo"] / RHO_N2_NM3) * s["nh3"].sum()
    renov = P_on.sum() + P_ppa.sum()
    ren_cons = E_tot - s["imp"].sum()
    k = dict(lcoa_eur_t=L, nh3_t_ano=nh3 / 1000, costes_eur_ano=c, coste_eur_t={kk: v / (nh3 / 1000) for kk, v in c.items()},
             consumo_especifico_kwh_kg_nh3=E_tot / s["nh3"].sum(), cf_hb=nh3 / (NH3_NOM * 8760), cf_pem=s["el"].sum() / (d["pem_kw"] * 8760 * ny),
             arranques_hb_ano=s["starts"] / ny, h2_perdido_arranques_t_ano=s["h2_perdido_arranques"] / 1000 / ny,
             import_red_mwh_ano=s["imp"].sum() / 1000 / ny, cuota_electricidad_renovable_contratada_horaria=max(ren_cons / E_tot, 0.0),
             excedente_frac=(s["sur_on"].sum() + s["sur_ppa"].sum()) / renov if renov > 0 else 0.0,
             potencia_contratada_kw=float(red_draw.max()))
    return L, k

# ----------------------------------------------------------------------------- series y escenarios
def series(anos, eol="eol_cf_cercana", anos_precio=None):
    m = np.isin(S["anio"], anos); ap = anos_precio or anos
    mp = np.isin(S["anio_precio"], ap)
    fv, e = S["fv_kw_kwp"][m], S[eol][m]; om, pe = S["omie_eur_mwh"][mp], S["periodo_precio"][mp]
    pf, pw = S["ppa_fv_cf_nacional"][mp], S["ppa_eol_cf_nacional"][mp]
    n = min(len(fv), len(om))
    if np.isnan(pf[:n]).any():   # anos sin perfil nacional (pre-2024): proxy local (documentado)
        pf, pw = fv, e
    return dict(fv=fv[:n], eol=e[:n], omie=om[:n], periodo=pe[:n], ppa_fv=pf[:n], ppa_eol=pw[:n], anos=n / 8766.0)

BASE_T = {k: v["base"] for k, v in PT.items()}; BASE_E = {k: v["base"] for k, v in PE.items()}
def qbase(): return {**BASE_T, **BASE_E}
D0 = dict(fv_kwp=0.0, eol_kw=0.0, ppa_fv_kw=0.0, ppa_eol_kw=0.0, pem_kw=1000.0, buffer_h=12.0, bat_kwh=0.0, carga_min_hb=0.4, umbral_eur_mwh=-1e9, modo=0, exporta=0)
ESC = {
 "aislado_fv_eol_bat": dict(modo=0, vars={"fv_kwp": (500, 12000), "eol_kw": (0, 6000), "pem_kw": (200, 4000), "buffer_h": (0, 120), "bat_kwh": (0, 6000), "carga_min_hb": (0.2, 0.6)}),
 "aislado_solo_fv_bat": dict(modo=0, vars={"fv_kwp": (500, 12000), "pem_kw": (200, 4000), "buffer_h": (0, 120), "bat_kwh": (0, 6000), "carga_min_hb": (0.2, 0.6)}),
 "red_auxiliares_fv_eol": dict(modo=1, vars={"fv_kwp": (500, 12000), "eol_kw": (0, 6000), "pem_kw": (200, 4000), "buffer_h": (0, 120), "bat_kwh": (0, 3000), "carga_min_hb": (0.2, 0.6)}),
 "ppa_fv_eol_red": dict(modo=1, vars={"ppa_fv_kw": (0, 12000), "ppa_eol_kw": (0, 8000), "pem_kw": (200, 4000), "buffer_h": (0, 120), "carga_min_hb": (0.2, 0.6)}),
 "red_spot_omie_no_verde": dict(modo=2, vars={"pem_kw": (200, 4000), "buffer_h": (0, 120), "umbral_eur_mwh": (0, 200), "carga_min_hb": (0.2, 0.6)}),
}
def diseno(esc, x):
    d = dict(D0, modo=ESC[esc]["modo"], exporta=ESC[esc].get("exporta", 0)); d.update(dict(zip(ESC[esc]["vars"], x))); return d

def optimizar(esc, ser, q, seed=7):
    b = list(ESC[esc]["vars"].values())
    r = differential_evolution(lambda x: lcoa(diseno(esc, x), q, ser), b, seed=seed, popsize=12, maxiter=60, tol=1e-4, polish=False)
    return diseno(esc, r.x), float(r.fun), int(r.nfev)

def muestrear(rng):
    q = {}
    for P in (PT, PE):
        for k, v in P.items(): q[k] = float(rng.triangular(v["min"], v["base"], v["max"])) if v["max"] > v["min"] else v["base"]
    return q

def gris(rng=None):
    g = GRIS
    def val(k): return g[k]["base"] if rng is None else float(rng.triangular(g[k]["min"], g[k]["base"], g[k]["max"]))
    gas = val("gas_gj_t") / 3.6 * val("ttf_eur_mwh"); co2 = val("co2_t_t") * val("eua_eur_t")
    return gas, co2

# ----------------------------------------------------------------------------- main
def main():
    t0 = time.time(); q = qbase(); A = [2022, 2023]
    ser = series(A, anos_precio=AP); r3 = lambda x: round(float(x), 3)
    ser_hist = series([2019, 2020, 2021, 2022, 2023])
    lcoa(D0, q, series([2019]))  # compilacion numba
    opt = {}
    for e in ESC:
        d, L, nf = optimizar(e, ser, q)
        _, k = lcoa(d, q, ser, True); opt[e] = dict(diseno=d, kpi=k, evaluaciones=nf); print(e, round(L, 1), {a: r3(b) for a, b in d.items()}, round(time.time() - t0))
    # Monte Carlo en el diseno optimo (parametros tecnicos + economicos, distribuciones triangulares)
    rng = np.random.default_rng(2026); N = 300; Q = [muestrear(rng) for _ in range(N)]
    for e in ESC:
        Ls = np.array([lcoa(opt[e]["diseno"], qq, ser) for qq in Q])
        opt[e]["lcoa_mc"] = dict(p5=pct(Ls, 5), p50=pct(Ls, 50), p95=pct(Ls, 95))
        if e != "ppa_fv_eol_red":   # sin perfil PPA nacional antes de 2024 -> no se calcula historico PPA
            opt[e]["lcoa_por_ano"] = {str(a): lcoa(opt[e]["diseno"], q, series([a])) for a in (2019, 2020, 2021, 2022, 2023)}
            opt[e]["lcoa_historico_2019_2023"] = lcoa(opt[e]["diseno"], q, ser_hist)
        else:
            opt[e]["lcoa_por_ano"] = {}; opt[e]["lcoa_historico_2019_2023"] = ""
        if opt[e]["diseno"]["modo"] >= 1:
            opt[e]["lcoa_precios_2024"] = lcoa(opt[e]["diseno"], q, series([2022], anos_precio=[2024]))
            opt[e]["lcoa_precios_2025"] = lcoa(opt[e]["diseno"], q, series([2023], anos_precio=[2025]))
        if e == "red_auxiliares_fv_eol":
            opt[e]["lcoa_si_vende_excedentes_omie"] = lcoa(dict(opt[e]["diseno"], exporta=1), q, ser)
        imp = {}
        for k in list(PT) + list(PE):
            imp[k] = round(spearman([qq[k] for qq in Q], Ls), 3)
        opt[e]["importancia_spearman"] = dict(sorted(imp.items(), key=lambda kv: -abs(kv[1]))[:8])
    # tornado y variabilidad interanual 2014-2023 (meteo) para el mejor escenario verde
    verdes = [e for e in ESC if "no_verde" not in e]
    mejor = min(verdes, key=lambda e: opt[e]["kpi"]["lcoa_eur_t"]); dm = opt[mejor]["diseno"]
    tornado = {}
    for k, v in {**PT, **PE}.items():
        if v["max"] == v["min"]: continue
        lo = lcoa(dm, dict(q, **{k: v["min"]}), ser); hi = lcoa(dm, dict(q, **{k: v["max"]}), ser); tornado[k] = (lo, hi)
    tornado = dict(sorted(tornado.items(), key=lambda kv: -abs(kv[1][1] - kv[1][0]))[:10])
    insitu = min([e for e in verdes if e != "ppa_fv_eol_red"], key=lambda e: opt[e]["kpi"]["lcoa_eur_t"]); di = opt[insitu]["diseno"]
    interanual = {str(a): lcoa(di, q, series([a], anos_precio=[2024]), True)[1] for a in range(2014, 2024)}  # meteo de cada ano; precios 2024 si aplica
    barr_buf_i = [(b, lcoa(dict(di, buffer_h=b), q, ser, True)[1]) for b in (0, 6, 12, 24, 48, 72, 96, 120)]
    barr_cm_i = [(m, lcoa(dict(di, carga_min_hb=m), q, ser, True)[1]) for m in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)]
    barr_pen_i = [(h, lcoa(di, dict(q, h_perdidas_arranque_hb=h), ser, True)[1]) for h in (0, 2, 6, 12, 24)]
    barr_par_i = [(h, lcoa(di, dict(q, min_parada_hb_h=h), ser, True)[1]) for h in (1, 6, 24, 72)]
    extra_insitu = dict(escenario=insitu, buf=barr_buf_i, cm=barr_cm_i, pen=barr_pen_i, par=barr_par_i)
    # sensibilidades de diseno en el mejor escenario: buffer y carga minima (re-optimizando solo FV/bateria/pem no; barrido directo)
    barr_buf = [(b, lcoa(dict(dm, buffer_h=b), q, ser, True)[1]) for b in (0, 6, 12, 24, 48, 72, 96, 120)]
    barr_cm = [(m, lcoa(dict(dm, carga_min_hb=m), q, ser, True)[1]) for m in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)]
    barr_pen = [(h, lcoa(dm, dict(q, h_perdidas_arranque_hb=h), ser, True)[1]) for h in (0, 2, 6, 12, 24)]
    # viento: celda ERA5 'tierra' (pesimista) re-optimizando el escenario con eolica
    ser_t = series(A, eol="eol_cf_tierra", anos_precio=AP); d_t, L_t, _ = optimizar("red_auxiliares_fv_eol", ser_t, q)
    # escenarios con red re-optimizados con precios recientes (meteo 2022-2023 emparejada con precios 2024-2025)
    ser_r = ser_hist; recientes = {}
    for e in ("red_auxiliares_fv_eol", "red_spot_omie_no_verde"):
        d_r, L_r, _ = optimizar(e, ser_r, q); recientes[e] = dict(diseno=d_r, kpi=lcoa(d_r, q, ser_r, True)[1])
        print("reciente", e, round(L_r, 1))
    # gris
    rg = np.random.default_rng(1); G = [gris(rg) for _ in range(2000)]
    gas_b, co2_b = gris()
    gr = dict(gas_eur_t=gas_b, co2_eur_t_exposicion_total=co2_b,
              gas_mas_co2_p5_p95=[pct([a + b for a, b in G], 5), pct([a + b for a, b in G], 95)], gas_p5_p95=[pct([a for a, _ in G], 5), pct([a for a, _ in G], 95)])
    graficos(opt, tornado, barr_buf, barr_cm, mejor, gr, ser, q, extra_insitu)
    res = construir_json(opt, mejor, tornado, interanual, barr_buf, barr_cm, barr_pen, d_t, L_t, gr, N, A, time.time() - t0, recientes, extra_insitu)
    print("insitu", insitu, "buf", [(b, r3(k["lcoa_eur_t"]), r3(k["arranques_hb_ano"])) for b, k in barr_buf_i], "cm", [(b, r3(k["lcoa_eur_t"]), r3(k["arranques_hb_ano"])) for b, k in barr_cm_i],
          "pen", [(b, r3(k["lcoa_eur_t"])) for b, k in barr_pen_i], "par", [(b, r3(k["lcoa_eur_t"]), r3(k["arranques_hb_ano"])) for b, k in barr_par_i])
    (OUT / "resultados.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float))
    print(json.dumps({e: dict(lcoa=r3(opt[e]["kpi"]["lcoa_eur_t"]), hist=opt[e]["lcoa_historico_2019_2023"], venta=r3(opt[e].get("lcoa_si_vende_excedentes_omie", 0)), dis={a: r3(b) for a, b in opt[e]["diseno"].items()}, exc=r3(opt[e]["kpi"]["excedente_frac"]), cfpem=r3(opt[e]["kpi"]["cf_pem"]), mc={k: r3(v) for k, v in opt[e]["lcoa_mc"].items()}, nh3=r3(opt[e]["kpi"]["nh3_t_ano"]),
                          kwh=r3(opt[e]["kpi"]["consumo_especifico_kwh_kg_nh3"]), arr=r3(opt[e]["kpi"]["arranques_hb_ano"]), anos={a: r3(b) for a, b in opt[e]["lcoa_por_ano"].items()},
                          p24=r3(opt[e].get("lcoa_precios_2024", 0)), p25=r3(opt[e].get("lcoa_precios_2025", 0)), cuota=r3(opt[e]["kpi"]["cuota_electricidad_renovable_contratada_horaria"]),
                          desglose={k: r3(v) for k, v in opt[e]["kpi"]["coste_eur_t"].items()}, imp=opt[e]["importancia_spearman"]) for e in ESC}, indent=1))
    print("mejor", mejor, "tornado", {k: (r3(a), r3(b)) for k, (a, b) in tornado.items()})
    print("tierra", r3(L_t), {a: r3(b) for a, b in d_t.items()}); print("gris", gr)
    print("buf", [(b, r3(k["lcoa_eur_t"]), r3(k["arranques_hb_ano"])) for b, k in barr_buf]); print("cm", [(b, r3(k["lcoa_eur_t"]), r3(k["arranques_hb_ano"])) for b, k in barr_cm])
    print("pen", [(b, r3(k["lcoa_eur_t"])) for b, k in barr_pen]); print("interanual", {a: r3(k["lcoa_eur_t"]) for a, k in interanual.items()}); print("t", time.time() - t0)

def pct(a, p): return float(np.percentile(np.asarray(a, float), p))
def spearman(x, y):
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y)); return float(np.corrcoef(rx, ry)[0, 1])

NOMBRE = {"red_aux_fv_eol_con_venta": "FV/eol + red aux. + venta exced.", "aislado_fv_eol_bat": "Aislado FV+eol+bat", "aislado_solo_fv_bat": "Aislado solo FV+bat", "red_auxiliares_fv_eol": "FV/eol in situ + red aux.",
          "ppa_fv_eol_red": "PPA FV/eol + red", "red_spot_omie_no_verde": "Red spot OMIE (no verde)"}

def graficos(opt, tornado, barr_buf, barr_cm, mejor, gr, ser, q, ex):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(14, 10))
    a = ax[0, 0]; es = list(opt); x = np.arange(len(es))
    L = [opt[e]["kpi"]["lcoa_eur_t"] for e in es]; lo = [max(L[i] - opt[e]["lcoa_mc"]["p5"], 0) for i, e in enumerate(es)]; hi = [max(opt[e]["lcoa_mc"]["p95"] - L[i], 0) for i, e in enumerate(es)]
    a.bar(x, L, yerr=[lo, hi], capsize=5, color=["tab:green", "tab:olive", "tab:blue", "tab:purple", "tab:gray"])
    a.axhspan(300, 800, color="k", alpha=0.08, label="NH3 gris mercado ~300-800 EUR/t")
    a.axhline(gr["gas_eur_t"] + gr["co2_eur_t_exposicion_total"], color="k", ls="--", lw=1, label="Gris: gas+CO2 (TTF 34, EUA 65)")
    a.set_xticks(x, [NOMBRE[e] for e in es], rotation=20, fontsize=8); a.set_ylabel("LCOA [EUR/t NH3]"); a.legend(fontsize=8)
    a.set_title("LCOA optimo por escenario (barras: base; error: P5-P95 MC)")
    a = ax[0, 1]; keys = sorted({k for e in es for k in opt[e]["kpi"]["coste_eur_t"]}); bottom = np.zeros(len(es)); neg = np.zeros(len(es))
    cmap = plt.get_cmap("tab20")
    for i, k in enumerate(keys):
        v = np.array([opt[e]["kpi"]["coste_eur_t"].get(k, 0) for e in es])
        pos = np.where(v > 0, v, 0); ng = np.where(v < 0, v, 0)
        a.bar(x, pos, bottom=bottom, color=cmap(i), label=k); a.bar(x, ng, bottom=neg, color=cmap(i)); bottom += pos; neg += ng
    a.set_xticks(x, [NOMBRE[e] for e in es], rotation=20, fontsize=8); a.set_ylabel("EUR/t NH3"); a.legend(fontsize=7, ncol=2); a.set_title("Desglose del LCOA (base)")
    a = ax[1, 0]; ks = list(tornado); Lb = opt[mejor]["kpi"]["lcoa_eur_t"]
    for i, k in enumerate(ks):
        l, h = tornado[k]; a.barh(i, h - Lb, left=Lb, color="tab:red", alpha=0.7); a.barh(i, l - Lb, left=Lb, color="tab:blue", alpha=0.7)
    a.axvline(Lb, color="k"); a.set_yticks(range(len(ks)), ks, fontsize=7); a.invert_yaxis(); a.set_xlabel("LCOA [EUR/t]")
    a.set_title(f"Tornado (min azul / max rojo): {NOMBRE[mejor]}")
    a = ax[1, 1]
    for bb, nm, c in ((barr_buf, NOMBRE[mejor], "tab:purple"), (ex["buf"], NOMBRE[ex["escenario"]], "tab:blue")):
        a.plot([b for b, _ in bb], [k["lcoa_eur_t"] for _, k in bb], "o-", color=c, label=f"buffer - {nm}")
    a.set_xlabel("Buffer H2 [h consumo nominal HB] (continuo)"); a.set_ylabel("LCOA [EUR/t]")
    a2 = a.twiny()
    for bb, nm, c in ((barr_cm, NOMBRE[mejor], "tab:purple"), (ex["cm"], NOMBRE[ex["escenario"]], "tab:blue")):
        a2.plot([m * 100 for m, _ in bb], [k["lcoa_eur_t"] for _, k in bb], "s--", color=c, alpha=0.6, label=f"carga min - {nm}")
    a2.set_xlabel("Carga minima HB [%] (discontinuo)"); a.legend(loc="upper left", fontsize=7); a2.legend(loc="lower right", fontsize=7)
    a.set_title("Sensibilidad de diseno (resto del optimo fijo; arranques penalizados)", pad=28)
    fig.suptitle("CERO-A v2 - El Prat de Llobregat - meteo real 2022-2023 (PVGIS/ERA5) + OMIE 2024-2025 - E2 sin datos experimentales", fontsize=11)
    fig.tight_layout(); fig.savefig(OUT / "grafico_lcoa_v2.png", dpi=130); plt.close(fig)
    # operacion: semana de invierno y de verano del mejor escenario
    d = opt[mejor]["diseno"]; s, P_on, P_ppa = simular(d, q, ser)
    fig, ax = plt.subplots(2, 1, figsize=(13, 7))
    for a, h0, tt in ((ax[0], 24 * 15, "Semana de enero, ano 1 de la serie base (PPA: perfil nacional 2024)"), (ax[1], 24 * 190, "Semana de julio, ano 1 de la serie base")):
        h = np.arange(h0, h0 + 168)
        a.plot(h - h0, P_on[h] + P_ppa[h], color="orange", label="Renovable [kW]"); a.plot(h - h0, s["el"][h], label="PEM [kW]")
        a2 = a.twinx(); a2.plot(h - h0, s["B"][h], "g--", label="Buffer H2 [kg]"); a2.plot(h - h0, s["r"][h] * 10, "k", lw=1, label="HB H2 x10 [kg/h]")
        a.set_title(f"{tt} - {NOMBRE[mejor]}"); a.legend(loc="upper left", fontsize=8); a2.legend(loc="upper right", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "grafico_operacion_v2.png", dpi=120); plt.close(fig)

def construir_json(opt, mejor, tornado, interanual, barr_buf, barr_cm, barr_pen, d_t, L_t, gr, N, A, dt, recientes, ex):
    r3 = lambda x: round(float(x), 3)
    def kp(k): return {a: ({b: r3(c) for b, c in v.items()} if isinstance(v, dict) else r3(v)) for a, v in k.items()}
    esc = {e: dict(diseno_optimo={a: r3(b) for a, b in o["diseno"].items()}, kpi=kp(o["kpi"]), lcoa_p5_p50_p95={a: r3(b) for a, b in o["lcoa_mc"].items()},
                   lcoa_por_ano_meteo_y_precio={a: r3(b) for a, b in o["lcoa_por_ano"].items()},
                   lcoa_historico_2019_2023_mismo_diseno=(r3(o["lcoa_historico_2019_2023"]) if o["lcoa_historico_2019_2023"] != "" else ""),
                   lcoa_si_vende_excedentes_omie=r3(o["lcoa_si_vende_excedentes_omie"]) if "lcoa_si_vende_excedentes_omie" in o else "",
                   lcoa_met2022_precios_2024=r3(o.get("lcoa_precios_2024", "") or 0) if "lcoa_precios_2024" in o else "",
                   lcoa_met2023_precios_2025=r3(o.get("lcoa_precios_2025", "") or 0) if "lcoa_precios_2025" in o else "",
                   importancia_spearman=o["importancia_spearman"], evaluaciones_optimizador=o["evaluaciones"]) for e, o in opt.items()}
    return {
     "meta": {"proyecto": "cero_a", "version": "v2", "version_anterior": "v1/ (perfiles sinteticos, sin costes)", "nivel_evidencia": "e2_validacion_concepto",
              "fecha": "2026-10-18", "emplazamiento": {"nombre": "el_prat_de_llobregat_barcelona", "lat": 41.30, "lon": 2.08},
              "scripts": ["datos_cero_a.py", "simulacion_cero_a_v2.py"], "datos_experimentales": [], "n_monte_carlo": N, "anos_optimizacion": {"meteo": A, "precios_omie": AP, "nota": "meteo 2022-2023 emparejada con precios 2024-2025 (coherente con ppa y peajes 2025); estres con 2019-2023 emparejado"},
              "fuentes_series": {"fv": "PVGIS v5.3 seriescalc (JRC), PVGIS-SARAH3 + ERA5, 2014-2023, c-Si 1 kWp, perdidas 14 %, 38 deg/2 deg optimos",
                                 "eolica": "ERA5 via Open-Meteo Historical Weather API (viento 10 y 100 m), 2014-2023; celda cercana 41.25N 2.00E (base) y celda tierra 41.50N 2.00E; curva Enercon E-53/800 (OEDB/windpowerlib), buje 73 m",
                                 "perfil_ppa": "CF horario nacional Espana eolica terrestre y solar 2024-2025 (Energy-Charts public_power/installed_power; primaria REE/ENTSO-E); en anos 2019-2023 se usa el perfil local como proxy",
                                 "precio": "OMIE diario zona ES via Energy-Charts API (Fraunhofer ISE), 2019-2025; licencia uso privado/interno",
                                 "renewables_ninja": "no usado: la API requiere token (credencial)"},
              "tiempo_ejecucion_s": round(dt, 1), "moneda": "EUR 2024 (USD->EUR 1/1.0824, BCE media 2024)",
              "advertencia": "resultados de modelo con supuestos de literatura; no validados experimentalmente"},
     "objetivo": "minimizar el lcoa de un piloto de 50 kg/h nh3 en el prat eligiendo fv/eolica/ppa, pem, buffer h2, bateria y carga minima hb, con series horarias reales, y compararlo con amoniaco gris",
     "datos_clave": {
        "supuestos_tecnicos": [{"parametro": k, "base": r3(v["base"]), "rango": [r3(v["min"]), r3(v["max"])], "unidad": v["unidad"], "fuente": v["fuente"]} for k, v in PT.items()],
        "supuestos_economicos": [{"parametro": k, "base": r3(v["base"]), "rango": [r3(v["min"]), r3(v["max"])], "unidad": v["unidad"], "fuente": v["fuente"]} for k, v in PE.items()],
        "vidas_utiles_anos": VIDA, "tarifa_red": "6.1TD 2025: peajes (BOE-A-2024-26218) + cargos segmento 3 (Orden TED/1487/2024); IEE no incluido (posible exencion procesos electroliticos, Ley 38/1992); festivos no modelados",
        "escenarios": esc, "mejor_escenario_verde": mejor,
        "tornado_mejor_escenario": {k: [r3(a), r3(b)] for k, (a, b) in tornado.items()},
        "mejor_escenario_in_situ": ex["escenario"],
        "barridos_mejor_in_situ": dict(buffer=[dict(buffer_h=b, lcoa_eur_t=r3(k["lcoa_eur_t"]), nh3_t_ano=r3(k["nh3_t_ano"]), arranques_hb_ano=r3(k["arranques_hb_ano"])) for b, k in ex["buf"]],
                                       carga_min_hb=[dict(carga_min=b, lcoa_eur_t=r3(k["lcoa_eur_t"]), nh3_t_ano=r3(k["nh3_t_ano"]), arranques_hb_ano=r3(k["arranques_hb_ano"])) for b, k in ex["cm"]],
                                       penalizacion_arranque_h=[dict(h=b, lcoa_eur_t=r3(k["lcoa_eur_t"])) for b, k in ex["pen"]],
                                       parada_minima_h=[dict(h=b, lcoa_eur_t=r3(k["lcoa_eur_t"]), arranques_hb_ano=r3(k["arranques_hb_ano"])) for b, k in ex["par"]]),
        "interanual_meteo_2014_2023_mejor_in_situ_precios_2024": {a: dict(lcoa_eur_t=r3(k["lcoa_eur_t"]), nh3_t_ano=r3(k["nh3_t_ano"])) for a, k in interanual.items()},
        "barrido_buffer_mejor": [dict(buffer_h=b, lcoa_eur_t=r3(k["lcoa_eur_t"]), nh3_t_ano=r3(k["nh3_t_ano"]), arranques_hb_ano=r3(k["arranques_hb_ano"])) for b, k in barr_buf],
        "barrido_carga_min_hb_mejor": [dict(carga_min=m, lcoa_eur_t=r3(k["lcoa_eur_t"]), nh3_t_ano=r3(k["nh3_t_ano"]), arranques_hb_ano=r3(k["arranques_hb_ano"])) for m, k in barr_cm],
        "barrido_penalizacion_arranque_mejor": [dict(h_perdidas=h, lcoa_eur_t=r3(k["lcoa_eur_t"]), arranques_hb_ano=r3(k["arranques_hb_ano"])) for h, k in barr_pen],
        "reoptimizado_meteo_y_precios_historicos_2019_2023": {e: dict(diseno_optimo={a: r3(b) for a, b in o["diseno"].items()}, kpi=kp(o["kpi"])) for e, o in recientes.items()},
        "eolica_celda_tierra_red_aux": dict(lcoa_eur_t=r3(L_t), diseno={a: r3(b) for a, b in d_t.items()}),
        "amoniaco_gris": dict(supuestos={k: v for k, v in GRIS.items()}, gas_eur_t=r3(gr["gas_eur_t"]), co2_eur_t_sin_asignacion_gratuita=r3(gr["co2_eur_t_exposicion_total"]),
                              gas_p5_p95=[r3(x) for x in gr["gas_p5_p95"]], gas_mas_co2_p5_p95=[r3(x) for x in gr["gas_mas_co2_p5_p95"]],
                              nota="solo coste de gas y CO2 (sin capex ni otros opex); la asignacion gratuita ETS se reduce con CBAM 2026-2034"),
     },
     "tareas": [
        {"id": "t1", "tarea": "medicion de recurso eolico in situ o descartar eolica (aeropuerto, servidumbres aeronauticas, espacio)", "estado": "pendiente"},
        {"id": "t2", "tarea": "cotizaciones de proveedor para hb+psa modular de 1-2 t/d y pem 1-3 mw (capex, carga minima, arranque)", "estado": "pendiente"},
        {"id": "t3", "tarea": "cuantificar energia/h2 perdido por arranque y tiempo minimo de parada del lazo hb (ensayo e3)", "estado": "pendiente"},
        {"id": "t4", "tarea": "analisis regulatorio rfnbo (reglamento delegado ue 2023/1184): adicionalidad, correlacion temporal y geografica del ppa", "estado": "pendiente"},
        {"id": "t5", "tarea": "anadir costes de personal, conexion a red, tanque nh3, terreno y permisos", "estado": "pendiente"},
     ],
     "riesgos": [
        {"riesgo": "recurso eolico pobre en el prat (era5 cf 6-13 %) y probable incompatibilidad con el aeropuerto", "impacto": "alto", "mitigacion": "fv + ppa; descartar eolica in situ salvo medicion"},
        {"riesgo": "escala piloto: capex especifico de hb/psa/pem domina el lcoa y es muy incierto", "impacto": "alto", "mitigacion": "cotizaciones (t2); escalar a 20 t/d en fase siguiente"},
        {"riesgo": "precio de red y peajes volatiles (2021-2022) afectan escenarios con red", "impacto": "medio", "mitigacion": "ppa a precio fijo; cobertura"},
        {"riesgo": "penalizacion por arranque del hb sin dato experimental", "impacto": "medio", "mitigacion": "t3"},
        {"riesgo": "cumplimiento rfnbo del escenario ppa no verificado; red spot no es verde", "impacto": "medio", "mitigacion": "t4"},
     ],
     "decisiones": [
        {"decision": "hb fijo 50 kg/h nh3 (como v1); se optimizan generacion, pem, buffer, bateria y carga minima", "tipo": "supuesto_de_diseno", "estado": "provisional"},
        {"decision": "carga minima hb acotada a 20-60 % (literatura); 10 % solo en barrido", "tipo": "supuesto_de_modelo", "estado": "provisional"},
        {"decision": "penalizacion de arranque = h2 consumido sin producir nh3 durante h_perdidas_arranque_hb a carga minima + parada minima", "tipo": "supuesto_de_modelo", "estado": "provisional"},
        {"decision": "v1 conservada en v1/", "tipo": "gestion", "estado": "hecho"},
     ],
     "proximo_paso": "obtener cotizaciones de hb/psa/pem (t2) y decidir entre fv in situ con bateria/red o ppa; con esas cifras re-optimizar y definir el ensayo e3 de arranque y carga minima del hb",
    }

if __name__ == "__main__":
    main()
