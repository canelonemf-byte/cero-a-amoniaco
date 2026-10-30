#!/usr/bin/env python3
"""Construye resultados.json, estado_cero_a.json y grafico_lcoa_v3.png a partir de data/v3_bruto.json (salida de simulacion_cero_a_v3.py)."""
import json, datetime
from pathlib import Path
import numpy as np
import simulacion_cero_a_v3 as m
OUT = Path(__file__).resolve().parent
B = json.loads((OUT / "data" / "v3_bruto.json").read_text()); O = B["opt"]
V2 = {"ppa_fv_eol_red": (1849, 1750, 2281), "red_auxiliares_fv_eol": (2575, 2391, 3302), "aislado_solo_fv_bat": (2767, 2637, 5353),
      "aislado_fv_eol_bat": (2751, 2630, 4420), "red_spot_omie_no_verde": (1821, 1721, 2232)}
AUT = "Lázaro López Paz, El Prat de Llobregat, Barcelona, España; con asistencia de inteligencia artificial"
FECHA = datetime.date.today().isoformat()
r0 = lambda x: round(float(x)); r1 = lambda x: round(float(x), 1); r3 = lambda x: round(float(x), 3)
NOM = {"ppa_red_mensual": "PPA + red (correl. mensual)", "ppa_rfnbo_horario": "PPA + red RFNBO horaria (modo 3)",
       "fv_in_situ_suelo_red_aux": "FV in situ en suelo alquilado + red aux.", "fv_cubierta_red_aux": "FV en cubierta/suelo sin alquiler + red aux.",
       "aislado_fv_cubierta_bat": "Aislado FV cubierta + bateria", "red_spot_omie_no_verde": "Red spot OMIE (no verde)"}

def limpiar(x):
    if isinstance(x, dict): return {str(k): limpiar(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [limpiar(v) for v in x]
    if x is None: return ""
    if isinstance(x, (bool, np.bool_)): return bool(x)
    if isinstance(x, (int, np.integer)): return int(x)
    if isinstance(x, (float, np.floating)):
        if not np.isfinite(x): return ""
        return round(float(x), 4)
    return x

def sup(P): return [dict(parametro=k, base=v["base"], rango=[v["min"], v["max"]], unidad=v["unidad"], fuente=v["fuente"]) for k, v in P.items()]

RFNBO_NORMA = {
 "fuentes": ["Reglamento Delegado (UE) 2023/1184 (texto consolidado 10-06-2024, CELEX 02023R1184-20240610)", "Reglamento Delegado (UE) 2023/1185, Anexo (metodologia GEI)",
             "Directiva (UE) 2018/2001 art. 27(3) y 25(2)", "Eurostat SHARES 2024 (cuota renovable electrica Espana 56.9 % 2023, 59.7 % 2024)"],
 "art_3_conexion_directa": "electricidad de instalacion conectada directamente (o en la misma instalacion) cuenta como totalmente renovable si la instalacion renovable entro en servicio <= 36 meses antes que la de RFNBO y, si hay conexion a red, se demuestra con contador inteligente que no se importa electricidad de red para producir el combustible",
 "art_4_red": "electricidad de red totalmente renovable si: zona de oferta con > 90 % renovable (Espana no), o intensidad < 18 gCO2e/MJ (Espana 54.1, no), o PPA renovable con adicionalidad (art. 5) y correlacion temporal (art. 6) y geografica (art. 7)",
 "art_5_adicionalidad": "instalacion renovable del PPA en servicio no antes de 36 meses previos a la de RFNBO y sin ayudas de funcionamiento o inversion (salvo excepciones)",
 "art_6_correlacion_temporal": "hasta 31-12-2029: mismo mes natural; desde 1-1-2030: misma hora (un Estado miembro puede adelantar la horaria a 1-7-2027). Excepcion: hora con precio diario <= 20 EUR/MWh o < 0.36 x precio EUA; almacenamiento nuevo detras del mismo punto de conexion permitido",
 "art_7_correlacion_geografica": "misma zona de oferta (o interconectada con precio igual/superior, o offshore adyacente). PPA en Espana peninsular: cumple",
 "art_11_transitorio": "instalaciones RFNBO en servicio antes de 1-1-2028 exentas de art. 5(a)(b) (adicionalidad) hasta 1-1-2038 (no aplica a ampliaciones posteriores)",
 "gei_2023_1185": "ahorro >= 70 % frente a 94 gCO2e/MJ -> limite 28.2 gCO2e/MJ; electricidad no renovable de red con factor 54.1 gCO2e/MJ (Espana, Anexo); calculo por mes o periodo mas corto",
 "umbral_excepcion_precio_modelo_eur_mwh": m.UMBRAL_RFNBO, "eua_usado_eur_t": m.EUA_UMBRAL,
}

def bloque(e):
    v = O[e]; k = v["kpi"]; rf = k["rfnbo"]; d = v["diseno"]
    v2e = m.V2_EQ[e]; vv = V2.get(v2e, ("", "", ""))
    elig = e not in ("red_spot_omie_no_verde",)
    var = {}
    for a, b in v["variantes"].items():
        var[a] = dict(lcoa_base=r0(b["base"]), p5_p95=[r0(b["p5"]), r0(b["p95"])], aplicable=bool(elig if a != "o2" else True))
    var["nota"] = ("H2 Pioneros: convocatorias 2022-2023 cerradas, intensidad 40-60 % solo sobre PEM+almacenamiento H2 (elegible); "
                   "Hydrogen Bank: HIPOTETICO, el piloto (<5 MWe) no es elegible; prima solo sobre H2 RFNBO, 10 anos; O2: ingreso bruto sin coste de purificacion/logistica. "
                   + ("" if elig else "Escenario no verde: ayudas no aplicables (se muestran solo como calculo)."))
    return dict(
        escenario=e, nombre=NOM[e], modo_red=int(d["modo"]),
        diseno={a: r3(b) for a, b in d.items() if a in m.ESC[e]["vars"]},
        lcoa_eur_t=r0(k["lcoa_eur_t"]),
        mc_diseno_fijo=dict(n=B["n_mc"], p5=r0(v["mc_fijo"]["p5"]), p50=r0(v["mc_fijo"]["p50"]), p95=r0(v["mc_fijo"]["p95"])),
        mc_reoptimizado=dict(n=B["n_mc_reopt"], p5=r0(v["mc_reoptimizado"]["p5"]), p50=r0(v["mc_reoptimizado"]["p50"]), p95=r0(v["mc_reoptimizado"]["p95"]),
                             diseno_p5_p95={a: [r1(x) for x in b] for a, b in v["mc_reoptimizado"]["diseno_p5_p95"].items()}),
        desglose_eur_t={a: r0(b) for a, b in k["coste_eur_t"].items()},
        nh3_t_ano=r1(k["nh3_t_ano"]), consumo_kwh_kg_nh3=r3(k["consumo_especifico_kwh_kg_nh3"]), cf_hb=r3(k["cf_hb"]), cf_pem=r3(k["cf_pem"]),
        arranques_hb_ano=r1(k["arranques_hb_ano"]), import_red_mwh_ano=r1(k["import_red_mwh_ano"]), potencia_contratada_kw=r0(k["potencia_contratada_kw"]),
        tanque_nh3_t=r1(k["tanque_nh3_t"]), seveso=k["seveso"], superficie_m2=r0(k["superficie_m2"]), capex_total_eur=r0(k["capex_total_eur"]),
        lcoa_precios_2024=r0(v["lcoa_precios_2024"]) if v.get("lcoa_precios_2024") else "", lcoa_precios_2025=r0(v["lcoa_precios_2025"]) if v.get("lcoa_precios_2025") else "",
        rfnbo={a: (r3(b) if isinstance(b, float) else b) for a, b in rf.items()},
        variantes_aparte=var, importancia_spearman=v["importancia_spearman"],
        v2_equivalente=dict(escenario=v2e, lcoa=vv[0], p5_p95=[vv[1], vv[2]] if vv[0] != "" else []),
    )

def rfnbo_texto(e):
    rf = O[e]["kpi"]["rfnbo"]
    if e.startswith("ppa"):
        return dict(cumple_mensual_hasta_2029=rf["cumple_mensual_hasta_2029"], cumple_horaria_desde_2030=rf["cumple_horaria_desde_2030"],
                    adicionalidad="condicionada: PPA con planta nueva (<=36 meses, sin ayudas) o electrolizador en servicio antes de 1-1-2028 (exento hasta 1-1-2038)",
                    geografica="cumple (zona ES)", comentario="PPA sobredimensionado (~9x PEM) cubre la demanda hora a hora con perfil nacional; la correlacion horaria no encarece (modo 3 = mismo LCOA)")
    if e == "red_spot_omie_no_verde":
        return dict(cumple_mensual_hasta_2029=False, cumple_horaria_desde_2030=False, adicionalidad="no", geografica="cumple",
                    comentario="sin PPA la red espanola no es renovable (art. 4); GEI %.0f gCO2e/MJ > 28.2" % rf["gei_horaria_gco2e_mj"])
    if e.startswith("aislado"):
        return dict(cumple_mensual_hasta_2029=True, cumple_horaria_desde_2030=True, adicionalidad="art. 3: FV en servicio <=36 meses antes del electrolizador",
                    geografica="no aplica", comentario="conexion directa sin red: 100 % RFNBO")
    return dict(cumple_mensual_hasta_2029=False, cumple_horaria_desde_2030=False, adicionalidad="art. 3 FV nueva <=36 meses; la red de auxiliares no tiene PPA",
                geografica="no aplica (directa) / cumple (red)",
                comentario="lectura A (toda la electricidad): %.1f %% renovable -> solo esa fraccion seria RFNBO; GEI %.1f gCO2e/MJ < 28.2 (cumple GEI). Lectura B (solo PEM+compresion): 100 %% -> cumpliria. Requiere confirmacion juridica"
                % (100 * rf["fraccion_renovable_horaria"], rf["gei_horaria_gco2e_mj"]))

PROX = [
 dict(id="p1", paso="cotizacion de alquiler de suelo industrial (no nave) en El Prat/Zona Franca para 1500-5000 m2 con uso quimico", criterio_aceptacion=">= 3 ofertas escritas con EUR/m2/mes y condiciones de uso; rango recalculado y LCOA v4 actualizado", entregable="data/cotizaciones_suelo.csv + delta LCOA en informe v4", plazo_semanas=4),
 dict(id="p2", paso="cotizaciones de proveedor HB+PSA modular 1-2 t/d y PEM 0.5-1 MW", criterio_aceptacion=">= 2 cotizaciones por equipo con CAPEX, carga minima, rampa y tiempo de arranque; sustituyen rangos de literatura", entregable="data/cotizaciones_equipos.csv + supuestos actualizados en simulacion v4", plazo_semanas=8),
 dict(id="p3", paso="oferta indicativa de PPA pay-as-produced eolico+FV de 1-5 MW (via agregador) con planta nueva (adicionalidad) y garantias de origen horarias", criterio_aceptacion=">= 2 ofertas con precio EUR/MWh, perfil horario y fecha de puesta en servicio de la planta", entregable="data/ofertas_ppa.csv + verificacion art. 5/6 en informe v4", plazo_semanas=8),
 dict(id="p4", paso="dictamen juridico RFNBO: lectura A vs B para electricidad de auxiliares y aplicacion del art. 11 (en servicio antes de 1-1-2028)", criterio_aceptacion="respuesta escrita de asesor o de la entidad certificadora (ISCC/REDcert/CertifHy) a 3 preguntas definidas", entregable="docs/dictamen_rfnbo.md", plazo_semanas=6),
 dict(id="p5", paso="ensayo/datos de fabricante E3 de arranque del HB (H2 perdido y parada minima)", criterio_aceptacion="valor medido o garantizado de h_perdidas_arranque_hb y min_parada_hb_h con incertidumbre <= 25 %", entregable="data/arranque_hb.json + re-optimizacion", plazo_semanas=12),
 dict(id="p6", paso="plantilla operativa del piloto (FTE por turno) y perfil salarial", criterio_aceptacion="organigrama con FTE justificados y coste por perfil con fuente (convenio quimico Cataluna)", entregable="docs/plantilla_piloto.md; rango personal_fte/coste_fte sustituido", plazo_semanas=4),
 dict(id="p7", paso="consulta a e-distribucion: punto de conexion MT, distancia y presupuesto", criterio_aceptacion="pliego de condiciones tecnico-economicas con EUR y km", entregable="data/conexion_red.json", plazo_semanas=10),
 dict(id="p8", paso="validacion del modelo: reproducir un caso publicado (p. ej. Wang et al. iScience 2022 o EES 2026) con el nucleo v3", criterio_aceptacion="LCOA reproducido dentro de +-10 % del publicado con sus supuestos", entregable="validacion/caso_referencia.md + script", plazo_semanas=3),
]

def main():
    esc = list(O)
    resultados = {e: bloque(e) for e in esc}
    verdes = [e for e in esc if "no_verde" not in e]
    mejor = min(verdes, key=lambda e: O[e]["kpi"]["lcoa_eur_t"])
    gr = B["gris"]
    meta = dict(proyecto="cero_a", version="v3", version_anterior="v2/ (sin personal/terreno/permisos/conexion/tanque; sin rfnbo)", nivel_evidencia="e2_validacion_concepto",
                fecha=FECHA, zona_horaria="Europe/Madrid", autoria=AUT, emplazamiento=dict(nombre="el_prat_de_llobregat_barcelona", lat=41.30, lon=2.08),
                scripts=["datos_cero_a.py", "simulacion_cero_a_v3.py", "construir_v3.py"], datos_experimentales=[],
                n_monte_carlo_diseno_fijo=B["n_mc"], n_monte_carlo_reoptimizado=B["n_mc_reopt"],
                metodo_mc_reoptimizado="cada muestra triangular re-optimiza el diseno (evolucion diferencial popsize 8, maxiter 35; 8 nucleos en paralelo)",
                anos=dict(meteo=[2022, 2023], precios_omie=[2024, 2025]), moneda="EUR 2024 (USD->EUR 1/1.0824)", tiempo_ejecucion_s=r1(B["t"]),
                advertencia="resultados de modelo con supuestos de literatura; no validados experimentalmente; no constituye asesoramiento juridico sobre rfnbo")
    res = dict(
        meta=meta,
        objetivo="piloto de amoniaco verde 50 kg/h nh3 en el prat: lcoa completo con rangos y cumplimiento rfnbo por escenario de suministro",
        datos_clave=dict(
            supuestos_tecnicos=sup(m.PT), supuestos_economicos=sup(m.PE), supuestos_escenarios_aparte=sup(m.EXTRA),
            derechos_conexion_eur_kw=dict(valor=m.DERECHOS_EUR_KW, fuente="derechos de extension 15.718632 + acceso 16.992541 EUR/kW, 1-36 kV, suelo urbanizado (<=250 kW); aplicado a toda la potencia contratada (aprox.)"),
            rfnbo_normativa=RFNBO_NORMA,
            escenarios=resultados, mejor_verde=mejor,
            cumplimiento_rfnbo={e: rfnbo_texto(e) for e in esc},
            amoniaco_gris=dict(gas_eur_t=r0(gr["gas_eur_t"]), co2_eur_t=r0(gr["co2_eur_t"]), gas_mas_co2_p5_p95=[r0(x) for x in gr["gas_mas_co2_p5_p95"]], referencias_mercado=m.GRIS["referencias_mercado"]),
            cambios_vs_v2=[
                "costes nuevos: personal, alquiler de suelo, permisos+ingenieria (% capex proceso), conexion a red (derechos + linea mt), tanque nh3 (tamano por balance horario + dias de seguridad)",
                "rfnbo: contabilidad mensual (<=2029) y horaria (>=2030), excepcion de precio art. 6, gei 2023/1185; nuevo modo 3 (red solo en horas de excepcion)",
                "eolica in situ eliminada (aeropuerto, cf 6-13 %); fv in situ separada en suelo alquilado y cubierta/suelo sin alquiler",
                "monte carlo re-optimizando cada muestra (n=%d) ademas del de diseno fijo (n=%d)" % (B["n_mc_reopt"], B["n_mc"]),
                "venta de o2 y ayudas (h2 pioneros, hydrogen bank) como escenarios aparte"]),
        tareas=[dict(id=p["id"], tarea=p["paso"], criterio_aceptacion=p["criterio_aceptacion"], entregable=p["entregable"], plazo_semanas=p["plazo_semanas"], estado="pendiente") for p in PROX]
              + [dict(id="h1", tarea="costes faltantes, rfnbo y mc re-optimizado (v3)", criterio_aceptacion="todos los parametros con fuente y rango; json sin valores nulos", entregable="resultados.json v3", plazo_semanas=0, estado="hecho")],
        riesgos=[
            dict(riesgo="alquiler de suelo (rentas de nave 6.5-11 EUR/m2/mes) es el mayor coste nuevo (~700 EUR/t) y hace inviable la fv en suelo alquilado (~19 000 EUR/t)", impacto="alto", mitigacion="p1: cotizar suelo; fv en cubierta propia o ppa"),
            dict(riesgo="costes fijos (personal + alquiler) ~1100-1300 EUR/t por la escala de 50 kg/h", impacto="alto", mitigacion="compartir personal/emplazamiento con instalacion existente; escalar"),
            dict(riesgo="adicionalidad del ppa: requiere planta nueva salvo entrada en servicio antes de 1-1-2028", impacto="alto", mitigacion="p3, p4; calendario"),
            dict(riesgo="interpretacion rfnbo de la electricidad de auxiliares tomada de red (lectura a vs b) en fv in situ", impacto="medio", mitigacion="p4; bateria o ppa para auxiliares"),
            dict(riesgo="perfil ppa nacional (energy-charts) puede sobreestimar la cobertura horaria de un ppa de una planta concreta", impacto="medio", mitigacion="p3: perfil horario real de la planta"),
            dict(riesgo="ayudas: h2 pioneros cerrado; hydrogen bank exige >= 5 mwe", impacto="medio", mitigacion="no incluidas en el caso base"),
            dict(riesgo="sin datos experimentales (e2); capex de equipos a escala piloto inciertos", impacto="alto", mitigacion="p2, p5, p8")],
        decisiones=[
            dict(decision="escenario preferente: ppa + red; con perfil nacional cumple rfnbo mensual y horario sin coste adicional", tipo="resultado_modelo", estado="provisional"),
            dict(decision="ayudas y venta de o2 fuera del caso base", tipo="criterio_prudencia", estado="hecho"),
            dict(decision="eolica in situ descartada", tipo="supuesto_de_diseno", estado="hecho"),
            dict(decision="lectura a (toda la electricidad) como criterio rfnbo conservador; lectura b informada", tipo="supuesto_regulatorio", estado="provisional"),
            dict(decision="v2 conservada en v2/", tipo="gestion", estado="hecho")],
        proximo_paso="p1 y p3 en paralelo (suelo y ppa: ~60 % del lcoa del escenario ppa); despues p2 y p4; re-optimizar en v4",
    )
    res = limpiar(res); s = json.dumps(res, ensure_ascii=False, indent=2)
    import re; bad = [mm.start() for mm in re.finditer(r": null|NaN", s)]; assert not bad, s[bad[0]-200:bad[0]+50]
    (OUT / "resultados.json").write_text(s)
    b = resultados[mejor]; sp = resultados["red_spot_omie_no_verde"]
    estado = limpiar(dict(
        meta=dict(proyecto="cero_a", version="v3", fecha=FECHA, zona_horaria="Europe/Madrid", autoria=AUT, nivel_evidencia="e2", emplazamiento="el_prat_de_llobregat",
                  versiones=["v1/", "v2/", "v3 (raiz)"], ficheros=["resultados.json", "informe.md", "grafico_lcoa_v3.png", "simulacion_cero_a_v3.py", "construir_v3.py", "log_v3.txt"]),
        objetivo="amoniaco_verde_piloto_50_kg_h_nh3_rfnbo_con_lcoa_completo",
        datos_clave=dict(mejor_escenario_verde=mejor, lcoa_mejor_verde_eur_t=b["lcoa_eur_t"], lcoa_mejor_verde_p5_p95_reoptimizado=[b["mc_reoptimizado"]["p5"], b["mc_reoptimizado"]["p95"]],
                         lcoa_por_escenario={e: dict(base=r["lcoa_eur_t"], p5_p95_reopt=[r["mc_reoptimizado"]["p5"], r["mc_reoptimizado"]["p95"]], p5_p95_fijo=[r["mc_diseno_fijo"]["p5"], r["mc_diseno_fijo"]["p95"]]) for e, r in resultados.items()},
                         rfnbo={e: dict(mensual=rfnbo_texto(e)["cumple_mensual_hasta_2029"], horaria=rfnbo_texto(e)["cumple_horaria_desde_2030"], fraccion_horaria=resultados[e]["rfnbo"].get("fraccion_renovable_horaria", "")) for e in esc},
                         lcoa_v2_ppa_eur_t=1849, lcoa_gris_eur_t=[r0(x) for x in gr["gas_mas_co2_p5_p95"]], produccion_t_ano=b["nh3_t_ano"]),
        tareas=res["tareas"], riesgos=res["riesgos"], decisiones=res["decisiones"], proximo_paso=res["proximo_paso"]))
    s2 = json.dumps(estado, ensure_ascii=False, indent=2); assert ": null" not in s2
    (OUT / "estado_cero_a.json").write_text(s2)
    grafico(resultados, gr)
    print(json.dumps({e: [r["lcoa_eur_t"], r["mc_diseno_fijo"]["p5"], r["mc_diseno_fijo"]["p95"], r["mc_reoptimizado"]["p5"], r["mc_reoptimizado"]["p95"]] for e, r in resultados.items()}))

def grafico(R, gr):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(15, 11)); esc = [e for e in R if e != "fv_in_situ_suelo_red_aux"]
    a = ax[0, 0]; x = np.arange(len(esc)); L = [R[e]["lcoa_eur_t"] for e in esc]
    lo = [R[e]["lcoa_eur_t"] - R[e]["mc_reoptimizado"]["p5"] for e in esc]; hi = [R[e]["mc_reoptimizado"]["p95"] - R[e]["lcoa_eur_t"] for e in esc]
    a.bar(x + 0.2, L, 0.4, yerr=[np.clip(lo, 0, None), np.clip(hi, 0, None)], capsize=4, color="tab:green", label="v3 base (barras: P5-P95 MC re-optimizado)")
    v2 = [R[e]["v2_equivalente"]["lcoa"] or 0 for e in esc]
    a.bar(x - 0.2, v2, 0.4, color="lightgray", label="v2 (escenario equivalente)")
    a.axhspan(*gr["gas_mas_co2_p5_p95"], color="k", alpha=0.15, label="gris gas+CO2 P5-P95")
    a.set_xticks(x); a.set_xticklabels([NOM[e] for e in esc], rotation=25, ha="right", fontsize=8); a.set_ylabel("EUR/t NH3"); a.legend(fontsize=8)
    a.set_title("LCOA v3 vs v2 (FV en suelo alquilado: %d EUR/t, fuera de escala)" % R["fv_in_situ_suelo_red_aux"]["lcoa_eur_t"], fontsize=10)
    a = ax[0, 1]; keys = [k for k in R[esc[0]]["desglose_eur_t"]]; bot = np.zeros(len(esc)); cm = plt.get_cmap("tab20")
    for i, k in enumerate(keys):
        v = np.array([R[e]["desglose_eur_t"].get(k, 0) for e in esc], float)
        if np.abs(v).max() < 5: continue
        pos = np.clip(v, 0, None); a.bar(x, pos, bottom=bot, color=cm(i % 20), label=k); bot += pos
        neg = np.clip(v, None, 0)
        if neg.min() < 0: a.bar(x, neg, color=cm(i % 20), hatch="//")
    a.set_xticks(x); a.set_xticklabels([NOM[e] for e in esc], rotation=25, ha="right", fontsize=8); a.legend(fontsize=7, ncol=2); a.set_title("Desglose LCOA v3 (EUR/t)", fontsize=10)
    a = ax[1, 0]; vs = ["o2", "pioneros", "h2bank", "todo"]; vv = [e for e in esc if "no_verde" not in e]
    for j, k in enumerate(["base"] + vs):
        val = [R[e]["lcoa_eur_t"] if k == "base" else R[e]["variantes_aparte"][k]["lcoa_base"] for e in vv]
        a.bar(np.arange(len(vv)) + (j - 2) * 0.16, val, 0.16, label=k)
    a.set_xticks(np.arange(len(vv))); a.set_xticklabels([NOM[e] for e in vv], rotation=20, ha="right", fontsize=8); a.legend(fontsize=8)
    a.set_title("Escenarios aparte: venta O2, H2 Pioneros, Hydrogen Bank (hipotetico)", fontsize=10); a.set_ylabel("EUR/t NH3")
    a = ax[1, 1]; e2 = list(R)
    fm = [R[e]["rfnbo"].get("fraccion_renovable_mensual", 0) * 100 for e in e2]; fh = [R[e]["rfnbo"].get("fraccion_renovable_horaria", 0) * 100 for e in e2]
    g = [R[e]["rfnbo"].get("gei_horaria_gco2e_mj", 0) for e in e2]; xx = np.arange(len(e2))
    a.bar(xx - 0.2, fm, 0.4, label="% renovable mensual (<=2029)"); a.bar(xx + 0.2, fh, 0.4, label="% renovable horaria (>=2030)")
    a2 = a.twinx(); a2.plot(xx, g, "ko", label="GEI gCO2e/MJ"); a2.axhline(28.2, color="r", ls="--", label="limite 28.2"); a2.set_ylabel("gCO2e/MJ")
    a.set_xticks(xx); a.set_xticklabels([NOM[e] for e in e2], rotation=25, ha="right", fontsize=7); a.set_ylabel("%"); a.legend(fontsize=7, loc="center left"); a2.legend(fontsize=7, loc="center right")
    a.set_title("RFNBO (lectura A: toda la electricidad) y GEI", fontsize=10)
    fig.suptitle("CERO-A v3 - El Prat de Llobregat - modelo E2 (sin datos experimentales)"); fig.tight_layout(); fig.savefig(OUT / "grafico_lcoa_v3.png", dpi=130)

if __name__ == "__main__":
    main()
