#!/usr/bin/env python3
"""
CERO-A v3 - Piloto Power-to-Ammonia en El Prat de Llobregat (41.30 N, 2.08 E), evidencia E2 (modelo, sin datos experimentales).
Sobre v2: (1) costes completos (personal, alquiler/terreno El Prat, permisos+ingenieria, conexion a red, tanque NH3),
venta de O2 y ayudas (H2 Pioneros/PERTE ERHA, Hydrogen Bank) como escenarios aparte; (2) contabilidad RFNBO segun
Reglamentos Delegados (UE) 2023/1184 (adicionalidad, correlacion temporal mensual <=2029 / horaria >=2030, geografica)
y 2023/1185 (GEI <= 28.2 gCO2e/MJ); modo 3 = red solo en horas de excepcion de precio (Art. 6);
(3) re-optimizacion y Monte Carlo re-optimizando cada muestra (paralelo).
Ejecutar:  .venv/bin/python datos_cero_a.py && .venv/bin/python simulacion_cero_a_v3.py
"""
import json, math, time, os, sys
from pathlib import Path
import numpy as np
from numba import njit
from scipy.optimize import differential_evolution
from multiprocessing import Pool

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import simulacion_cero_a_v2 as v2
from simulacion_cero_a_v2 import (T, PT, PE as PE2, VIDA as VIDA2, PEAJE_E, CARGO_E, PEAJE_P, CARGO_P, GRIS, AP, NH3_NOM,
                                  H2_STOICH, N2_STOICH, RHO_N2_NM3, USD_EUR, tec, crf, series, pct, spearman, gris)
u = USD_EUR
# ----------------------------------------------------------------------------- costes nuevos v3 (EUR 2024)
PE_NUEVOS = {
 "personal_fte": T(4.0, 2.0, 6.0, "FTE", "SUPUESTO del modelo (sin referencia publica para piloto 50 kg/h); rango amplio 2-6"),
 "coste_fte_eur_a": T(45000.0, 37525.4, 60000.0, "EUR/FTE/a", "INE ETCL/EACL 2024: coste laboral medio 37 525.40 EUR/trabajador/a (min); base y max = SUPUESTO perfil tecnico/turnos"),
 "superficie_planta_m2": T(3000.0, 1500.0, 5000.0, "m2", "SUPUESTO (PEM, HB, PSA, tanque, distancias de seguridad); sin fuente"),
 "alquiler_eur_m2_mes": T(8.5, 6.54, 11.0, "EUR/m2/mes", "Anuncios El Prat 8.50-9.23; Zona Franca 11 (2025); media Cataluna 6.54 (BNP Paribas RE Q3 2025); CBRE prime BCN ~7 (Q2 2025). Son rentas de naves: cota alta para suelo"),
 "ha_por_mwp_fv": T(2.0, 1.3, 2.0, "ha/MWp", "UNEF/MAPA: ocupacion real 1.3-1.5 ha/MWp; 2 ha/MWp en planificacion"),
 "frac_permisos_ingenieria": T(0.15, 0.10, 0.25, "fraccion CAPEX proceso", "NETL QGESS owner's costs hasta ~20 %; EPRI 10 % ingenieria + 15 % contingencia; caso NL 9 %+9 %"),
 "conexion_km": T(0.5, 0.2, 2.0, "km linea MT", "SUPUESTO (distancia a red MT en poligono); sin fuente"),
 "coste_linea_eur_km": T(146733.0, 146733.0, 217993.0, "EUR/km", "CNMC (2013) valores de referencia linea MT subterranea simple 146 733 / doble 217 993 EUR/km (EUR corrientes 2013, sin actualizar)"),
 "tanque_usd_t": T(3000.0, 2000.0, 4000.0, "USD/t capacidad NH3", "Rouwenhorst et al. 2021 (Techno-Economic Challenges of Green Ammonia, cap.) ~3000 USD/t presurizado pequena escala; rango +-33 % SUPUESTO"),
 "dias_seguridad_tanque": T(7.0, 3.0, 14.0, "dias de produccion nominal", "SUPUESTO logistico (frecuencia de recogida por cisterna)"),
}
DERECHOS_EUR_KW = 15.718632 + 16.992541  # derechos de extension + acceso 1-36 kV (RD 1048/2013 / Orden vigente), suelo urbanizado <=250 kW; aplicado a toda la potencia (aprox.)
PE = {**PE2, **PE_NUEVOS}
# escenarios aparte (no entran en el LCOA base)
EXTRA = {
 "precio_o2_eur_t": T(90.0, 80.0, 100.0, "EUR/t O2", "Energiforsk 2023: O2 merchant bulk 80-100 EUR/t (ingreso bruto; sin coste de purificacion/compresion/logistica)"),
 "intensidad_ayuda_pioneros": T(0.40, 0.40, 0.60, "fraccion costes elegibles", "Orden TED H2 Pioneros (PERTE ERHA): 40 % gran empresa, 50 % mediana, 60 % pequena; elegible: electrolizador, auxiliares, almacenamiento, compresion. Convocatorias 2022-2023 cerradas"),
 "prima_h2bank_eur_kg": T(0.84, 0.44, 0.85, "EUR/kg H2 RFNBO, 10 a", "Hydrogen Bank IF24, adjudicatarios espanoles 0.44/0.84/0.85 EUR/kg; HIPOTETICO: subastas exigen >= 5 MWe (piloto no elegible)"),
}
VIDA = dict(VIDA2, tanque=20, conexion=20, otros=20)
EUA_UMBRAL = GRIS["eua_eur_t"]["base"]   # 65 EUR/t (ESMA 2025, media 2024)
UMBRAL_RFNBO = max(20.0, 0.36 * EUA_UMBRAL)   # Art. 6 RD 2023/1184: <=20 EUR/MWh o < 0.36 x EUA
F_RED_ES = 54.1      # gCO2e/MJ electricidad red Espana, Anexo RD 2023/1185 (dato 2020)
LIM_GEI = 28.2       # 70 % de ahorro vs 94 gCO2e/MJ
LHV_NH3_MJ_KG = 18.6

# ----------------------------------------------------------------------------- nucleo (v2 + modo 3 + salidas aux/comp)
@njit(cache=True)
def kernel(P_on, P_ppa, barato, barato_r, modo, Pn, eel, pmin_frac, ec, r_nom, r_min, ramp, Bcap, soc_obj, tau, arr_h,
           min_parada, h_pen, aux_h2, bat_kwh, rte, eta_loop):
    n = P_on.shape[0]
    nh3 = np.zeros(n); imp = np.zeros(n); sur_on = np.zeros(n); sur_ppa = np.zeros(n); el = np.zeros(n)
    used_ppa = np.zeros(n); auxh = np.zeros(n); comph = np.zeros(n); impel = np.zeros(n)
    se = math.sqrt(rte); bat_kw = bat_kwh / 4.0
    B = Bcap * soc_obj; soc = 0.5 * bat_kwh; on = False; r = 0.0; off_h = 1000; starts = 0; pen_left = 0.0
    h2_prod = 0.0; comp_tot = 0.0; pmin = pmin_frac * Pn; perdido = 0.0
    for t in range(n):
        own = P_on[t] + P_ppa[t]
        gaux = (modo == 1) or (modo == 2) or (modo == 3 and barato_r[t])
        gel = (modo == 2) and barato[t]
        dis_av = min(bat_kw, soc * se)
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
        aux = aux_h2 * r
        f_on = min(P_on[t], aux); rem = aux - f_on
        f_ppa = min(P_ppa[t], rem); rem -= f_ppa
        d = min(rem, dis_av); soc -= d / se; rem -= d
        if rem > 1e-9: imp[t] += rem
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
        if E > 1e-9:
            imp[t] += E; impel[t] = E
        B = min(max(B + prod - r, 0.0), Bcap)
        s_on = av_on - e_on; s_ppa = av_ppa - e_ppa
        ch = min(bat_kw, (bat_kwh - soc) / se, s_on + s_ppa)
        if ch > 0:
            soc += ch * se; c1 = min(ch, s_on); s_on -= c1; s_ppa -= (ch - c1)
        sur_on[t] = s_on; sur_ppa[t] = s_ppa
        used_ppa[t] = P_ppa[t] - s_ppa
        el[t] = prod * eel; h2_prod += prod; comp_tot += comp; auxh[t] = aux; comph[t] = comp
        h2_util = r
        if pen_left > 0:
            q = min(pen_left, r); pen_left -= q; h2_util -= q; perdido += q
        nh3[t] = h2_util * eta_loop / (1.5 * 2.01588 / 17.03052)
    return nh3, imp, sur_on, sur_ppa, used_ppa, el, auxh, comph, impel, starts, h2_prod, comp_tot, perdido

def simular(d, q, ser):
    eta, h2_in, aux_h2, ec = tec(q)
    r_nom = NH3_NOM * h2_in; r_min = d["carga_min_hb"] * r_nom
    P_on = ser["fv"] * d["fv_kwp"] + ser["eol"] * d["eol_kw"]
    P_ppa = ser["ppa_fv"] * d["ppa_fv_kw"] + ser["ppa_eol"] * d["ppa_eol_kw"]
    barato = ser["omie"] <= d["umbral_eur_mwh"]
    barato_r = ser["omie"] <= UMBRAL_RFNBO
    o = kernel(P_on, P_ppa, barato, barato_r, int(d["modo"]), d["pem_kw"], q["e_electrolizador_kwh_kg_h2"], q["carga_min_electrolizador"], ec,
               r_nom, r_min, q["rampa_hb_frac_h"] * r_nom, d["buffer_h"] * r_nom, 0.3, 6.0, 4.0, q["min_parada_hb_h"],
               q["h_perdidas_arranque_hb"], aux_h2, d["bat_kwh"], q["rte_bateria"], eta)
    k = ["nh3", "imp", "sur_on", "sur_ppa", "used_ppa", "el", "aux", "comp_h", "imp_el", "starts", "h2_prod", "comp", "h2_perdido_arranques"]
    return dict(zip(k, o)), P_on, P_ppa

def tanque_t(nh3_h, q):
    m = nh3_h.mean(); dev = np.cumsum(nh3_h - m)
    return (dev.max() - dev.min()) / 1000 + q["dias_seguridad_tanque"] * NH3_NOM * 24 / 1000

def rfnbo(d, s, ser):
    """Contabilidad RFNBO (RD 2023/1184) y GEI (RD 2023/1185). Electricidad consumida = PEM + compresion + auxiliares."""
    E = s["el"] + s["comp_h"] + s["aux"]; Et = E.sum()
    if Et <= 0: return {}
    imp = s["imp"]; tiene_ppa = (d["ppa_fv_kw"] + d["ppa_eol_kw"]) > 0
    barr = ser["omie"] <= UMBRAL_RFNBO
    # horaria (obligatoria desde 1-1-2030): importacion cuenta como renovable solo con PPA y (excedente PPA en la misma hora -> ya netado
    # en el nucleo) o en hora de excepcion de precio
    imp_ok_h = imp * barr if tiene_ppa else 0 * imp
    ren_h = (E - imp).sum() + imp_ok_h.sum()
    # mensual (hasta 31-12-2029): importacion cubierta por excedente PPA inyectado en el mismo mes natural
    if tiene_ppa:
        mes = (np.arange(len(imp)) // 730.5).astype(int)  # mes aproximado (730.5 h); serie horaria sin calendario explicito
        imp_m = np.bincount(mes, imp - imp_ok_h); sur_m = np.bincount(mes, s["sur_ppa"])
        ren_m = (E - imp).sum() + imp_ok_h.sum() + np.minimum(imp_m, sur_m).sum()
    else:
        ren_m = (E - imp).sum()
    # lectura B: solo la electricidad del electrolizador+compresion debe ser renovable (auxiliares solo en GEI)
    Eel = (s["el"] + s["comp_h"]).sum(); impel = s["imp_el"]
    ren_el_h = Eel - impel.sum() + (impel * barr).sum() * tiene_ppa
    nh3 = s["nh3"].sum(); MJ = nh3 * LHV_NH3_MJ_KG
    def gei(no_ren_kwh): return no_ren_kwh * 3.6 * F_RED_ES / MJ if MJ > 0 else 0.0
    out = dict(fraccion_renovable_mensual=ren_m / Et, fraccion_renovable_horaria=ren_h / Et,
               fraccion_renovable_electrolizador_horaria=ren_el_h / max(Eel, 1e-9),
               gei_mensual_gco2e_mj=gei(Et - ren_m), gei_horaria_gco2e_mj=gei(Et - ren_h),
               horas_excepcion_precio_frac=float(barr.mean()), umbral_excepcion_eur_mwh=UMBRAL_RFNBO)
    out["cumple_mensual_hasta_2029"] = bool(out["fraccion_renovable_mensual"] >= 0.999 and out["gei_mensual_gco2e_mj"] <= LIM_GEI)
    out["cumple_horaria_desde_2030"] = bool(out["fraccion_renovable_horaria"] >= 0.999 and out["gei_horaria_gco2e_mj"] <= LIM_GEI)
    out["cumple_horaria_lectura_b"] = bool(out["fraccion_renovable_electrolizador_horaria"] >= 0.999 and out["gei_horaria_gco2e_mj"] <= LIM_GEI)
    return out

def lcoa(d, q, ser, detalle=False, var=None):
    """var: None | 'o2' | 'pioneros' | 'h2bank' | 'todo' (escenarios aparte con q extra)."""
    s, P_on, P_ppa = simular(d, q, ser); ny = ser["anos"]
    nh3 = s["nh3"].sum() / ny
    if nh3 < 1000: return (1e5, None) if detalle else 1e5
    w = q["wacc"]; r_nom_h2 = NH3_NOM * H2_STOICH / q["conversion_global_lazo"]; c = {}
    a20 = crf(w, 20)
    c["fv"] = d["fv_kwp"] * (q["capex_fv_eur_kwp"] * crf(w, VIDA["fv"]) + q["om_fv_eur_kwp_a"])
    c["eolica"] = d["eol_kw"] * (q["capex_eol_eur_kw"] * crf(w, VIDA["eol"]) + q["om_eol_eur_kw_a"])
    capem = d["pem_kw"] * q["capex_pem_eur_kw"]
    horas_eq = s["el"].sum() / max(d["pem_kw"], 1) / ny
    c["pem"] = capem * (crf(w, VIDA["pem"]) + q["om_pem_frac"]) + capem * q["frac_stack_capex"] * horas_eq / q["vida_stack_h"]
    capbuf = d["buffer_h"] * r_nom_h2 * q["capex_buffer_eur_kg"]
    c["buffer_h2"] = capbuf * (crf(w, VIDA["buffer"]) + 0.02)
    cappsahb = q["capex_psa_eur"] + q["capex_hb_eur"]
    c["psa_hb"] = cappsahb * (crf(w, VIDA["hb"]) + q["om_hb_psa_frac"])
    capbat = d["bat_kwh"] * q["capex_bat_eur_kwh"]
    c["bateria"] = capbat * (crf(w, VIDA["bat"]) + q["om_bat_frac"])
    tq = tanque_t(s["nh3"], q); captq = tq * q["tanque_usd_t"] * u
    c["tanque_nh3"] = captq * (crf(w, VIDA["tanque"]) + 0.02)   # O&M 2 % supuesto (igual que buffer)
    per = ser["periodo"] - 1
    red_draw = s["imp"] + (s["used_ppa"] if d["modo"] >= 1 else 0)
    pcon = float(red_draw.max())
    capcon = (DERECHOS_EUR_KW * pcon + q["conexion_km"] * q["coste_linea_eur_km"]) if pcon > 0 else 0.0
    c["conexion_red"] = capcon * crf(w, VIDA["conexion"])
    c["permisos_ingenieria"] = q["frac_permisos_ingenieria"] * (capem + capbuf + cappsahb + capbat + captq + capcon) * a20
    c["personal"] = q["personal_fte"] * q["coste_fte_eur_a"]
    area = q["superficie_planta_m2"] + d.get("fv_suelo", 1) * d["fv_kwp"] / 1000 * q["ha_por_mwp_fv"] * 1e4
    c["alquiler_terreno"] = area * q["alquiler_eur_m2_mes"] * 12
    c["red_energia_omie"] = float((s["imp"] * ser["omie"]).sum() / 1000 / ny)
    c["red_peajes_cargos"] = float((red_draw * (PEAJE_E + CARGO_E)[per]).sum() / ny + (pcon * (PEAJE_P + CARGO_P).sum() if pcon > 0 else 0))
    pf, pe = ser["ppa_fv"] * d["ppa_fv_kw"], ser["ppa_eol"] * d["ppa_eol_kw"]
    c["ppa"] = float(pf.sum() / 1000 * q["ppa_fv_eur_mwh"] / ny + pe.sum() / 1000 * q["ppa_eol_eur_mwh"] / ny)
    p_ppa_h = np.where(pf + pe > 0, (pf * q["ppa_fv_eur_mwh"] + pe * q["ppa_eol_eur_mwh"]) / np.maximum(pf + pe, 1e-9), 0.0)
    c["venta_excedentes"] = -float((s["sur_ppa"] * np.minimum(ser["omie"], p_ppa_h)).sum() / 1000 / ny)
    c["agua"] = s["h2_prod"] / ny * 9.0 / 1000 * q["agua_eur_m3"]
    rf = rfnbo(d, s, ser) if (detalle or var in ("h2bank", "todo")) else {}
    if var in ("o2", "todo"):
        c["venta_o2"] = -s["h2_prod"] / ny * 7.94 / 1000 * q["precio_o2_eur_t"]
    if var in ("pioneros", "todo"):
        c["ayuda_pioneros"] = -q["intensidad_ayuda_pioneros"] * (capem + capbuf) * crf(w, 20)
    if var in ("h2bank", "todo"):
        fr = rf.get("fraccion_renovable_mensual", 0.0)
        c["ayuda_h2bank"] = -q["prima_h2bank_eur_kg"] * s["h2_prod"] / ny * fr * (1 - (1 + w) ** -10) / w * crf(w, 20)
    tot = sum(c.values()); L = tot / (nh3 / 1000)
    if not detalle: return L
    E_tot = s["el"].sum() + s["comp"] + s["aux"].sum()
    renov = P_on.sum() + P_ppa.sum()
    k = dict(lcoa_eur_t=L, nh3_t_ano=nh3 / 1000, costes_eur_ano=c, coste_eur_t={kk: v / (nh3 / 1000) for kk, v in c.items()},
             consumo_especifico_kwh_kg_nh3=E_tot / s["nh3"].sum(), cf_hb=nh3 / (NH3_NOM * 8760), cf_pem=s["el"].sum() / (d["pem_kw"] * 8760 * ny),
             arranques_hb_ano=s["starts"] / ny, import_red_mwh_ano=s["imp"].sum() / 1000 / ny,
             excedente_frac=(s["sur_on"].sum() + s["sur_ppa"].sum()) / renov if renov > 0 else 0.0,
             potencia_contratada_kw=pcon, tanque_nh3_t=tq, seveso="no" if tq < 50 else ("umbral_inferior" if tq < 200 else "umbral_superior"),
             superficie_m2=area, capex_total_eur=capem + capbuf + cappsahb + capbat + captq + capcon + d["fv_kwp"] * q["capex_fv_eur_kwp"],
             rfnbo=rf)
    return L, k

# ----------------------------------------------------------------------------- escenarios v3
D0 = dict(fv_kwp=0.0, eol_kw=0.0, ppa_fv_kw=0.0, ppa_eol_kw=0.0, pem_kw=1000.0, buffer_h=12.0, bat_kwh=0.0, carga_min_hb=0.4,
          umbral_eur_mwh=-1e9, modo=0, exporta=0, fv_suelo=1)
ESC = {
 "ppa_red_mensual": dict(modo=1, vars={"ppa_fv_kw": (0, 12000), "ppa_eol_kw": (0, 8000), "pem_kw": (200, 4000), "buffer_h": (0, 120), "carga_min_hb": (0.2, 0.6)}),
 "ppa_rfnbo_horario": dict(modo=3, vars={"ppa_fv_kw": (0, 12000), "ppa_eol_kw": (0, 8000), "pem_kw": (200, 4000), "buffer_h": (0, 120), "bat_kwh": (0, 3000), "carga_min_hb": (0.2, 0.6)}),
 "fv_in_situ_suelo_red_aux": dict(modo=1, fv_suelo=1, vars={"fv_kwp": (100, 12000), "pem_kw": (100, 4000), "buffer_h": (0, 120), "bat_kwh": (0, 3000), "carga_min_hb": (0.2, 0.6)}),
 "fv_cubierta_red_aux": dict(modo=1, fv_suelo=0, vars={"fv_kwp": (500, 12000), "pem_kw": (200, 4000), "buffer_h": (0, 120), "bat_kwh": (0, 3000), "carga_min_hb": (0.2, 0.6)}),
 "aislado_fv_cubierta_bat": dict(modo=0, fv_suelo=0, vars={"fv_kwp": (500, 12000), "pem_kw": (200, 4000), "buffer_h": (0, 120), "bat_kwh": (0, 6000), "carga_min_hb": (0.2, 0.6)}),
 "red_spot_omie_no_verde": dict(modo=2, vars={"pem_kw": (200, 4000), "buffer_h": (0, 120), "umbral_eur_mwh": (0, 200), "carga_min_hb": (0.2, 0.6)}),
}
V2_EQ = {"ppa_red_mensual": "ppa_fv_eol_red", "ppa_rfnbo_horario": "", "fv_in_situ_suelo_red_aux": "red_auxiliares_fv_eol",
         "fv_cubierta_red_aux": "red_auxiliares_fv_eol", "aislado_fv_cubierta_bat": "aislado_solo_fv_bat", "red_spot_omie_no_verde": "red_spot_omie_no_verde"}

def diseno(esc, x):
    e = ESC[esc]; d = dict(D0, modo=e["modo"], fv_suelo=e.get("fv_suelo", 1)); d.update(dict(zip(e["vars"], x))); return d

def optimizar(esc, ser, q, seed=7, pop=12, it=60):
    b = list(ESC[esc]["vars"].values())
    r = differential_evolution(lambda x: lcoa(diseno(esc, x), q, ser), b, seed=seed, popsize=pop, maxiter=it, tol=1e-4, polish=False)
    return diseno(esc, r.x), float(r.fun), int(r.nfev)

def qbase():
    q = {k: v["base"] for k, v in {**PT, **PE, **EXTRA}.items()}; return q
def muestrear(rng):
    return {k: (float(rng.triangular(v["min"], v["base"], v["max"])) if v["max"] > v["min"] else v["base"]) for k, v in {**PT, **PE, **EXTRA}.items()}

SER = None
def _init():
    global SER; SER = series([2022, 2023], anos_precio=AP)
def _mc_reopt(args):
    esc, qq, seed = args
    d, L, _ = optimizar(esc, SER, qq, seed=seed, pop=8, it=35)
    return esc, L, d

# ----------------------------------------------------------------------------- main
def main():
    t0 = time.time(); q = qbase(); A = [2022, 2023]
    ser = series(A, anos_precio=AP); r3 = lambda x: round(float(x), 3)
    lcoa(D0, q, series([2019]))
    opt = {}
    for e in ESC:
        d, L, nf = optimizar(e, ser, q)
        _, k = lcoa(d, q, ser, True); opt[e] = dict(diseno=d, kpi=k, evaluaciones=nf)
        print(e, round(L, 1), {a: r3(b) for a, b in d.items()}, r3(k["rfnbo"].get("fraccion_renovable_horaria", 0)), round(time.time() - t0), flush=True)
    # MC diseno fijo (300) + variantes
    rng = np.random.default_rng(2026); N = 300; Q = [muestrear(rng) for _ in range(N)]
    for e in ESC:
        dd = opt[e]["diseno"]
        Ls = np.array([lcoa(dd, qq, ser) for qq in Q]); opt[e]["mc_fijo"] = dict(p5=pct(Ls, 5), p50=pct(Ls, 50), p95=pct(Ls, 95))
        imp = {k: round(spearman([qq[k] for qq in Q], Ls), 3) for k in list(PT) + list(PE)}
        opt[e]["importancia_spearman"] = dict(sorted(imp.items(), key=lambda kv: -abs(kv[1]))[:8])
        var = {}
        for vv in ("o2", "pioneros", "h2bank", "todo"):
            Lb = lcoa(dd, q, ser, var=vv); Lm = np.array([lcoa(dd, qq, ser, var=vv) for qq in Q[:100]])
            var[vv] = dict(base=Lb, p5=pct(Lm, 5), p95=pct(Lm, 95))
        opt[e]["variantes"] = var
        if dd["modo"] >= 1:
            opt[e]["lcoa_precios_2024"] = lcoa(dd, q, series([2022], anos_precio=[2024]))
            opt[e]["lcoa_precios_2025"] = lcoa(dd, q, series([2023], anos_precio=[2025]))
        print("mc", e, {k: r3(v) for k, v in opt[e]["mc_fijo"].items()}, {k: r3(v["base"]) for k, v in var.items()}, flush=True)
    # MC re-optimizando cada muestra (DE reducida pop 8, it 35), paralelo
    NR = int(os.environ.get("CERO_A_NR", "48")); rng2 = np.random.default_rng(3030); Q2 = [muestrear(rng2) for _ in range(NR)]
    tareas = [(e, Q2[i], 100 + i) for e in ESC for i in range(NR)]
    with Pool(os.cpu_count(), initializer=_init) as pool:
        res = pool.map(_mc_reopt, tareas, chunksize=2)
    for e in ESC:
        Ls = np.array([L for ee, L, _ in res if ee == e]); Ds = [d for ee, _, d in res if ee == e]
        opt[e]["mc_reoptimizado"] = dict(n=NR, p5=pct(Ls, 5), p50=pct(Ls, 50), p95=pct(Ls, 95),
                                         diseno_p5_p95={k: [pct([d[k] for d in Ds], 5), pct([d[k] for d in Ds], 95)] for k in ESC[e]["vars"]})
        print("mcR", e, {k: r3(v) for k, v in opt[e]["mc_reoptimizado"].items() if k != "diseno_p5_p95"}, flush=True)
    # comprobacion: diseno optimo PPA-mensual evaluado con reglas horarias -> ya en rfnbo; tornado mejor verde horario
    rg = np.random.default_rng(1); G = [gris(rg) for _ in range(2000)]; gas_b, co2_b = gris()
    gr = dict(gas_eur_t=gas_b, co2_eur_t=co2_b, gas_mas_co2_p5_p95=[pct([a + b for a, b in G], 5), pct([a + b for a, b in G], 95)])
    out = dict(opt=opt, gris=gr, n_mc=N, n_mc_reopt=NR, t=time.time() - t0)
    (OUT / "data" / "v3_bruto.json").write_text(json.dumps(out, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print("t", time.time() - t0)

if __name__ == "__main__":
    main()
