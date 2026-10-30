# CERO-A — Simulación base del prototipo piloto P2A (evidencia E2)

**Estado:** validación de concepto por modelo. **No hay datos experimentales.** Todas las cifras salen de supuestos de literatura con rangos de incertidumbre. Fecha: 18-10-2026.
**Reproducir:** `cd /workspace/cero-a && .venv/bin/python simulacion_cero_a.py` (~26 s, semillas fijas). Salidas: `resultados.json` y `grafico_sensibilidad.png`.

## 1. Sistema modelado (balance horario, 8 760 h)
FV 1,5 MWp + eólica 1,0 MW (perfiles sintéticos calibrados al factor de capacidad) → PEM 1 MW → buffer de H2 (30→200 bar, 12 h de consumo nominal del HB = 109 kg) → N2 por PSA → lazo Haber-Bosch de 50 kg/h NH3 (conversión por paso del 15 %, global del 98 %, purga y recirculación) → tanque de NH3.
Prioridad de despacho: los auxiliares (HB y PSA) se alimentan primero; el resto va al electrolizador. En el caso base, la red respalda **solo** a los auxiliares y ese consumo se contabiliza; el escenario aislado va aparte.
El control del HB es heurístico: sigue la producción de H2 y corrige hacia un SOC objetivo del 30 % con τ = 6 h. Se aplican carga mínima, rampa, umbral de rearranque y parada si falta H2.
*El dimensionado es una decisión de diseño provisional, no un dato de literatura.*

## 2. Resultados principales
Caso base: media de 5 años meteorológicos sintéticos. Rango: Monte Carlo con 200 muestras, distribuciones triangulares sobre todos los supuestos y año meteorológico aleatorio.

| Indicador | Base | Rango P5–P95 |
|---|---|---|
| Producción NH3 | **303 t/año** (meteo: 302–305) | **276–321 t/año** |
| Consumo específico total | **12,3 kWh/kg NH3** | **11,4–14,2** |
| – de él, electrólisis | 9,96 kWh/kg NH3 | — |
| Eficiencia PtA (LHV NH3 / electricidad) | 42 % | 36–45 % |
| Factor de capacidad renovable | 20,6 % (FV 19 %, eólica 23 %) | según CF de entrada |
| Factor de capacidad del electrolizador | 34,7 % | 32,6–37,5 % |
| Factor de capacidad del HB | 69 % | 63–73 % |
| Vertido renovable | 18,5 % | 15–25 % |
| Arranques del HB/año | ~91 | 44–156 |
| Importación de red (auxiliares) | 86 MWh/año (2,3 %) | — |
| Escenario **aislado** (sin red) | 269 t/año, **~521 arranques/año** | — |
| Tanque de NH3 para retirada constante | ~23 t | — |

Contraste con literatura: Wang et al. (iScience 2022) dan 11,1 kWh/kg a gran escala; ISPT P2A dan 9,5 kWh/kg con PEM. El valor más alto obtenido aquí se debe sobre todo al consumo del lazo HB a escala piloto (base de 2,0 kWh/kg).

**Balance de masa** (año base, semilla 11): H2 producido 55,3 t; N2 al HB 256,4 t; NH3 305,5 t; H2 purgado 1,1 t; N2 purgado 5,1 t; agua estequiométrica ≥ 494 t; O2 coproducido 439 t. El balance de H2 cierra con un error menor de 1 g. La recirculación molar es 5,5 veces la alimentación fresca y se purga el 0,4 % del gas no convertido.
**Balance de energía** (MWh/año): renovable generada 4 511 (vertida 834); electrolizador 3 043; compresión al buffer 18; lazo HB 611; PSA 92; importación de red 86. Salidas: LHV del NH3 1 578; calor de reacción del HB 229 (no recuperado); LHV del H2 purgado 37.

## 3. Sensibilidad (`grafico_sensibilidad.png`)
- **Eficiencia del electrolizador (50→65 kWh/kg H2):** la producción baja de 314 a 278 t/año y el consumo sube de 11,4 a 14,1 kWh/kg NH3. Es el parámetro más influyente en el consumo (Spearman 0,79), seguido del consumo del lazo HB (0,66).
- **Tamaño del buffer:** con 0 h se producen ~190–207 t/año, con cientos de arranques; con 12 h, ~300–306 t/año; con 48 h, ~330–333 t/año. Es la palanca de diseño más fuerte.
- **Carga mínima del HB (10–100 %):** con buffer ≥ 12 h apenas cambia la producción (±3 %), pero los arranques/año se multiplican (con 12 h de buffer: 1 al 10 % de carga mínima y ~250 al 100 %). **El modelo no penaliza los arranques**, así que el efecto real de la carga mínima está infraestimado.
- **Política de control:** según el SOC objetivo y τ, la producción varía entre 279 y 308 t/año (±5 %).
- **Mayor efecto sobre la producción (Spearman):** CF eólico (+0,51), eficiencia del electrolizador (−0,63), consumo del lazo HB (−0,35) y CF FV (+0,34).

## 4. Supuestos críticos (base [rango] — fuente)
- PEM: 55 [50–65] kWh/kg H2; carga mínima del 5 % [5–10 %]. Fuentes: IRENA 2020 (sistema 50–83 kWh/kg; carga 5–120 %) y OIES EL47.
- Lazo HB: 2,0 [0,64–3,62] kWh/kg NH3. Fuentes: Rouwenhorst et al., RSER 2019 (Cussler 3,62; NFUEL ~2) e Ikäheimo et al., IJHE 2018 (0,64).
- Conversión por paso del 15 % [10–25 %] y global del 98 % [97–99 %]. Fuente: Rouwenhorst et al. 2021, vía Wang et al. 2022.
- PSA: 0,45 [0,30–0,60] kWh/Nm3 N2, con rango operativo del 80–100 %. Fuente: ficha de Messer.
- Carga mínima del HB: 40 % [20–60 %]; rampa del 20 %/h. Fuentes: Armijo y Philibert 2020; Fasihi et al. 2021; ICAE 2021; IEA (rango "normal" del 60 %); Cheema y Krewer 2018.
- CF FV: 19 % [17–21 %]. Fuente: REE, Informe de Renovables 2023 (valor derivado). CF eólico: 23 % [20–30 %]. Fuente: IEA Wind TCP, España 2023.
- Compresión de H2: trabajo isotermo de 30 a 200 bar con eficiencia de 0,6 [0,5–0,75], lo que da ~1,06 kWh/kg. El rango es un supuesto, contrastado con el DOE Program Record 9013.
- Constantes: LHV del H2 33,33 kWh/kg; LHV del NH3 18,6 MJ/kg; ΔHf del NH3 −45,9 kJ/mol.

## 5. Limitaciones
1. Los perfiles renovables son **sintéticos** y solo están calibrados en CF anual, con un emplazamiento genérico a 40° N. No reproducen correlaciones FV-viento ni eventos extremos reales.
2. Las eficiencias son constantes con la carga: no se modelan curvas de carga parcial del PEM, del PSA ni del lazo, ni la degradación.
3. El HB es un balance estacionario hora a hora. No hay cinética, ni térmica de lechos, ni autotermia a baja carga, ni tiempos o energía de arranque, ni hot-standby.
4. No hay batería, buffer de N2 ni deoxo. La purga no se valoriza y el calor de reacción no se recupera.
5. El control es heurístico, sin previsión. Una optimización con previsión daría otra producción.
6. No se calculan costes; quedan para la siguiente fase (LCOA).

## 6. Próximo paso
Sustituir los perfiles por series reales del emplazamiento (PVGIS/ERA5) y hacer un dimensionado conjunto con costes (renovable, PEM, buffer, HB y batería). Así se fijarán el buffer y la carga mínima objetivo del HB, y después se podrá definir el ensayo mínimo para E3: rampa y carga mínima del HB, y PSA con deoxo.
