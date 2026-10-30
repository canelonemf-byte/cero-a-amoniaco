# CERO-A v2: piloto P2A en El Prat de Llobregat, con series reales, LCOA y dimensionado óptimo (E2)

**Estado:** validación de concepto por modelo, **sin datos experimentales**. Fecha: 18-10-2026. La versión anterior (perfiles sintéticos, sin costes) está en `v1/`.
**Reproducir:** `.venv/bin/python datos_cero_a.py && .venv/bin/python simulacion_cero_a_v2.py` (unos 40 s; semillas fijas). Salidas: `resultados.json`, `grafico_lcoa_v2.png`, `grafico_operacion_v2.png` y `log_v2.txt`.

## 1. Datos horarios reales (`data/`, descargados sin credenciales)
| Serie | Fuente | Años | Resultado |
|---|---|---|---|
| FV in situ | PVGIS v5.3 `seriescalc` (JRC), radiación SARAH3 y meteorología ERA5; c-Si, pérdidas del 14 %, inclinación 38° y azimut 2° óptimos | 2014–2023 | CF 17,9 % (17,1–18,7 % según el año) |
| Eólica in situ | ERA5 (viento a 10 y 100 m) vía Open-Meteo Archive; curva Enercon E-53/800 (OEDB/windpowerlib), buje a 73 m, cizalladura horaria calculada de ERA5 | 2014–2023 | CF 13,4 % (celda más cercana, 41,25N 2,00E) y 6,4 % (celda "tierra", 41,50N) |
| Perfil PPA | CF horario nacional de España (eólica terrestre y solar) de Energy-Charts (generación y potencia instalada; origen REE/ENTSO-E) | 2024–2025 | FV 20,4 / 17,0 %; eólica 22,0 / 20,0 % |
| Precio | OMIE, mercado diario, zona ES, vía API de Energy-Charts (2025 en periodos de 15 min, promediado a horario) | 2019–2025 | Media: 2019 47,7; 2021 111,9; 2022 167,5; 2024 63,0; 2025 65,3 €/MWh |
| Peajes de red | Peajes 6.1TD 2025 (BOE-A-2024-26218) y cargos del segmento 3 (Orden TED/1487/2024), periodos P1–P6 de la Circular 3/2020 en hora local | 2025 | — |

Renewables.ninja **no se usó** porque su API exige token. El año base es la meteorología de 2022–2023 con precios, PPA y peajes de 2024–2025, para que todo sea coherente con el precio de PPA de 2025. Como prueba de estrés se usa el periodo 2019–2023 emparejado (incluye la crisis de 2021–2022).

## 2. Modelo
- **Proceso** (igual que en v1): HB fijo de 50 kg/h NH3, buffer de H2 a 30–200 bar y auxiliares (HB + PSA) servidos primero. Novedades: batería (4 h, eficiencia del 85 %), PPA "pay-as-produced" y compra en el mercado spot.
- **Penalización por arranque del HB:** en cada arranque se consumen 6 h × la carga mínima de H2 sin producir NH3 (rango 2–12 h), con una parada mínima de 6 h. *Supuesto sin fuente cuantitativa.*
- **LCOA:** coste anual equivalente con la anualidad (CRF) de cada equipo según su vida útil, más O&M, reposición de stacks (según horas de operación / 50 000 h), electricidad (OMIE + peajes + cargos + término de potencia), PPA y agua.
- **Excedentes del PPA:** se revenden a OMIE con un crédito limitado al precio del PPA, para que no haya beneficio por arbitraje. Sin ese límite, los años de crisis daban LCOA negativos.
- **Optimización:** evolución diferencial (scipy) sobre FV, eólica, PPA, potencia PEM, buffer, batería, carga mínima del HB (20–60 %) y umbral de precio.
- **Incertidumbre:** Monte Carlo de 300 muestras (triangulares) sobre todos los parámetros técnicos y económicos, con el diseño óptimo fijo.

## 3. Resultados: LCOA óptimo por escenario (€/t NH3, EUR 2024)
| Escenario | LCOA base | P5–P95 | Dimensionado óptimo | NH3 (t/año) | Arranques/año |
|---|---|---|---|---|---|
| **PPA FV+eólica + red (verde, el mejor)** | **1 849** | **1 750–2 281** | PPA 1,03 MW FV + 2,79 MW eólica; PEM 503 kW; buffer 1,7 h (≈15 kg); sin batería; carga mínima HB 20 % | 389 | 3,5 |
| FV in situ + red solo para auxiliares | 2 575 | 2 391–3 302 | FV 3,13 MWp; sin eólica; PEM 1,37 MW; buffer 26 h (≈240 kg); sin batería; carga mínima 23 % | 358 | 0,5 |
| Aislado FV+eólica+batería | 2 751 | 2 630–4 420 | FV 3,10 MWp; eólica 0,40 MW; PEM 1,29 MW; buffer 26 h; batería 1,61 MWh; carga mínima 21 % | 365 | 9 |
| Aislado solo FV + batería | 2 767 | 2 637–5 353 | FV 3,40 MWp; PEM 1,27 MW; buffer 25 h; batería 1,76 MWh; carga mínima 22 % | 348 | 44 |
| Red spot OMIE (**no verde**) | 1 821 | 1 721–2 232 | PEM 499 kW; buffer 3,8 h; compra si OMIE ≤ 136 €/MWh | 412 | 25 |

- **Consumo específico:** 12,3–12,5 kWh/kg NH3 en todos los escenarios. En el PPA, el 100 % del consumo queda cubierto hora a hora por la generación contratada; en la opción FV in situ + red para auxiliares, el 90,8 %.
- **Desglose del mejor escenario (€/t):** PPA 846; PEM 522; PSA+HB 407; peajes y cargos 216; reventa de excedentes −149 (se revende el 30 % del PPA).
- **FV in situ:** PEM 1 238 y FV 705 €/t; el PEM solo funciona al 30 % de su capacidad.
- **Variabilidad por año:**
  - PPA con precios de 2024: 1 863; con precios de 2025: 1 833.
  - FV in situ + red con la meteorología de cada año 2014–2023: 2 507–2 680.
  - Spot no verde: 1 470 con los precios de 2020 y **4 286 con los de 2022**.
- **Vender los excedentes in situ a OMIE** bajaría la opción FV in situ + red de 2 575 a 2 498 €/t.
- **Eólica in situ:** el optimizador la descarta, tanto con la celda ERA5 cercana como con la de tierra.

**Sensibilidad del diseño** (resto del óptimo fijo, arranques penalizados):
- **Buffer (FV in situ):** 0 h → 7 628 €/t con 376 arranques/año; 12 h → 3 139; 24 h → 2 584; 48 h → 2 618. El óptimo está en unas 24–26 h.
- **Buffer (PPA):** es casi indiferente entre 0 y 12 h (1 857–1 870).
- **Carga mínima del HB:** subirla siempre encarece. PPA: 1 849 al 20 %, 1 961 al 60 % y 2 117 al 80 %, con los arranques pasando de 3,5 a 182/año. FV in situ: 2 576 → 2 630 → 2 731.
- **Penalización por arranque (0–24 h) y parada mínima (1–72 h):** cambian el LCOA menos de 5 €/t en el óptimo, porque el dimensionado ya evita arranques. El riesgo aparece si el buffer es pequeño.

**Parámetros más influyentes** (Spearman en el Monte Carlo; tornado en `grafico_lcoa_v2.png`):
- **PPA:** eficiencia del PEM (0,56), CAPEX del HB (0,45), WACC (0,36) y CAPEX del PEM (0,34). En el tornado: kWh/kg H2 da 1 764–2 154 y CAPEX del HB 1 740–2 107.
- **Aislado:** consumo del lazo HB (0,62), WACC (0,37) y CAPEX del PEM (0,37).
- **Fragilidad del aislado:** su P95 es muy alto porque, si el consumo de los auxiliares resulta mayor de lo supuesto, el diseño fijo deja de sostener el HB. Es un diseño poco robusto.

## 4. Comparación con amoníaco gris
- **Gas:** 33 GJ/t (28–38) × TTF 34 €/MWh (media 2024, ACER) = **312 €/t** (P5–P95: 255–426).
- **Gas + CO2 sin asignación gratuita:** 1,8 t/t × EUA 65 €/t = +117, en total **383–562 €/t** (P5–P95).
- **Referencias de mercado:** 423 USD/t como coste medio en Europa occidental en 2024 (QCIntel); 665 €/t sin capex en abril de 2026 (Argus); unos 300 €/t históricos con picos de 800 (Haber–Bosch 2.0, EES 2026).
- **Resultado:** el mejor verde (1 849 €/t, P5–P95 1 750–2 281) cuesta **unas 3,3–4,8 veces el gris** (gas + CO2) y 2,3–6 veces el rango de mercado.
- **Coherencia con la literatura:** EES 2026 da 740–4 100 €/t para Haber–Bosch descentralizado (más de 1 100 aislado), y la planta de 2,4 t/d de Santander, 2 408 €/t.

## 5. Supuestos críticos (base [rango] — fuente; detalle completo en `resultados.json`)
- **PEM:** 2 264 €/kW [1 755–3 000], según IEA GHR 2024/2025 (2 000–2 450 USD/kW fuera de China). El máximo para escala piloto es un supuesto. O&M del 3 % y stack de 50 000 h [50–95 kh] (anexo de IEA GHR 2024). El stack supone el 30–45 % del coste (IRENA 2020).
- **HB:** 1,09 M€ [0,75–1,9]. Sale de EES 2026 (8 600 €/(kg/h) a 20 t/d) escalado con exponente 0,6–0,8; el máximo, de Malmali et al. 2018.
- **PSA:** 183 k€ [126–222], escalado del mismo modo desde EES 2026 (1 720 €/(kg N2/h)).
- **Buffer de H2:** 867 €/kg [535–1 000], según EES 2026 (26 €/kWh) y ENTEC 2022.
- **FV:** 800 €/kWp [620–1 000]. IRENA 2023 da 671 USD/kW para España; la prima de escala piloto es un supuesto. O&M 12 [9,5–18] €/kW·año (IRENA: 10,3 USD).
- **Eólica:** 1 400 €/kW [1 072–1 800], según IRENA 2023 (1 160 USD/kW). El O&M de 30–50 €/kW·año es un supuesto.
- **Batería:** 400 €/kWh [252–485], según IRENA 2023 (273 USD/kWh) y NREL ATB 2024 (525 USD/kWh).
- **PPA:** solar 33,5 €/MWh [30–40] y eólica 53 €/MWh [45–60], según LevelTen (P25 de España, T3–T4 de 2025).
- **WACC:** 7 % [5–10 %]. Es un supuesto.
- **Cambio de divisa:** 1 USD = 0,924 € (media BCE 2024).
- **Técnicos:** iguales que en v1.
- **Supuestos sin fuente cuantitativa:** penalización y parada mínima del HB, y O&M eólico.

## 6. Limitaciones
1. **No se incluyen** personal, terreno, permisos, conexión a red, tanque de NH3, venta de O2 ni ayudas. En un piloto el personal puede añadir cientos de €/t, así que **el LCOA está infraestimado**.
2. **PPA:** el perfil es el nacional, no el de una planta concreta. Además, un PPA de 1–4 MW está por debajo del tamaño típico de mercado y requeriría un agregador. No se ha verificado el cumplimiento RFNBO (Reglamento Delegado UE 2023/1184: adicionalidad, correlación temporal y geográfica).
3. **Precios:** los de 2024–2025 se combinan con la meteorología de 2022–2023 (la forma diaria de la FV se conserva). La licencia de Energy-Charts es de uso privado o interno. No se modelan festivos ni el Impuesto Especial sobre la Electricidad (posible exención para procesos electrolíticos).
4. **ERA5:** con resolución de unos 31 km, no representa bien el viento costero de El Prat. Además, el aeropuerto y el Delta del Llobregat hacen muy improbable instalar eólica in situ.
5. **Modelado técnico:** eficiencias constantes con la carga y HB en balance horario, sin térmica ni datos reales de arranque. El control es heurístico y sin previsión.
6. **Optimización e incertidumbre:** el Monte Carlo se hace con el diseño fijo, sin reoptimizar en cada muestra. El HB de 50 kg/h no se ha optimizado.

## 7. Próximo paso
Pedir cotizaciones de un HB + PSA modular de 1–2 t/d y de un PEM de 0,5–1,5 MW, y una oferta de PPA o agregador. Con esas cifras, reoptimizar e incluir el personal y la conexión. Después, definir el ensayo E3: energía y H2 por arranque, y carga mínima real del HB.
