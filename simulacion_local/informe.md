# CERO-A v3: piloto de amoníaco verde en El Prat de Llobregat

**Autoría:** Lázaro López Paz, El Prat de Llobregat, Barcelona, España; con asistencia de inteligencia artificial.
**Nivel de evidencia:** E2 (validación de concepto por modelo; sin datos experimentales). La versión v2 se conserva en `v2/` y la v1 en `v1/`.
**Ejecución:** `.venv/bin/python simulacion_cero_a_v3.py && .venv/bin/python construir_v3.py` (unos 4 minutos con 8 núcleos). Salidas: `resultados.json`, `estado_cero_a.json`, `grafico_lcoa_v3.png` y `log_v3.txt`.

## 1. Qué cambia respecto a v2

- **Costes añadidos al LCOA** (cada uno con fuente y rango en `resultados.json`):
  - Personal: 4 FTE (rango 2–6) × 45 k€ (rango 37,5–60 k€). El mínimo es el coste laboral medio del INE 2024; el número de FTE es un supuesto.
  - Alquiler de suelo: 3000 m² (1500–5000, supuesto) a 8,5 €/m²/mes (rango 6,54–11; anuncios en El Prat, Zona Franca, BNP Paribas y CBRE). Son rentas de naves, por lo que es una cota alta para suelo desnudo.
  - Permisos e ingeniería: 15 % del CAPEX de proceso (rango 10–25 %; NETL, EPRI).
  - Conexión a red: derechos de extensión y acceso, 32,7 €/kW, más una línea de media tensión de 0,5 km (0,2–2) a 146–218 k€/km (valores de referencia CNMC 2013).
  - Tanque de NH3: dimensionado por balance horario más 7 días de seguridad (3–14), a 3000 USD/t (2000–4000; Rouwenhorst et al. 2021). Se comprueba el umbral Seveso de 50 t.
- **RFNBO:** contabilidad mensual (hasta 2029) y horaria (desde 2030), con la excepción de precio del art. 6: OMIE ≤ máx(20; 0,36 × EUA) = 23,4 €/MWh, que se da en el 27 % de las horas de 2024–2025. Se calcula el GEI según 2023/1185.
  - Nuevo **modo 3**: la red solo puede alimentar los auxiliares en horas de excepción de precio.
- **Escenarios:**
  - Se elimina la eólica in situ (aeropuerto; factor de capacidad 6–13 %).
  - La FV in situ se separa en dos casos: en suelo alquilado, y en cubierta o suelo sin alquiler. Este segundo caso es un supuesto.
- **Monte Carlo:**
  - Diseño fijo: n = 300.
  - **Reoptimizando cada muestra:** n = 64 por escenario, con evolución diferencial reducida y en paralelo.
- **Escenarios aparte**, no incluidos en el caso base: venta de O2, H2 Pioneros (PERTE ERHA) y Hydrogen Bank.

## 2. Resultados de LCOA v3 (€/t NH3; meteorología 2022–2023 con precios 2024–2025)

| Escenario | Base | P5–P95 MC reoptimizado | P5–P95 MC diseño fijo | v2 equivalente |
|---|---|---|---|---|
| PPA + red, correlación mensual | **3166** | 2960–3701 | 3017–3924 | 1849 (1750–2281) |
| PPA + red, RFNBO horaria (modo 3) | **3166** | 2960–3702 | 3018–3923 | — |
| FV in situ en suelo alquilado + red auxiliares | 19 129 | 15 229–22 308 | 14 888–22 284 | 2575 |
| FV en cubierta sin alquiler + red auxiliares | 4114 | 3923–4981 | 3871–5142 | 2575 (2391–3302) |
| Aislado: FV en cubierta + batería | 4338 | 4113–5231 | 4153–8023 | 2767 (2637–5353) |
| Red spot OMIE (no verde) | 3052 | 2850–3570 | 2918–3833 | 1821 (1721–2232) |
| Amoníaco gris (gas + CO2) | 383–562 (P5–P95) | | | |

**Diseño óptimo PPA + red:**
- PPA de 1,21 MW FV y 3,67 MW eólica; electrolizador PEM de 537 kW; buffer de H2 de 14 h; carga mínima del HB del 29 %.
- Produce 423 t/año con 0,5 arranques/año.
- Tanque de 16 t (por debajo del umbral Seveso de 50 t). Potencia contratada 653 kW.

**Desglose del escenario PPA + red (€/t):**

| Partida | €/t |
|---|---|
| PPA | 1004 |
| Alquiler | 724 |
| PEM | 516 |
| Personal | 426 |
| PSA + HB | 375 |
| Peajes y cargos | 211 |
| Permisos | 92 |
| Buffer de H2 | 30 |
| Conexión | 21 |
| Tanque | 12 |
| Venta de excedentes del PPA | −249 |

Los costes nuevos suman unos 1275 €/t, y explican casi todo el salto respecto a v2 (1849 → 3166). Los costes fijos (personal + alquiler) suponen unos 1150 €/t y son ahora el primer factor de sensibilidad (Spearman: superficie 0,59, personal 0,31, alquiler 0,24). Por eso la conclusión de escala es más fuerte que en v2: a 50 kg/h, el piloto no se paga con el producto.

En el MC reoptimizado, el P95 es menor que en el MC de diseño fijo porque el diseño se adapta a cada muestra. Los rangos de diseño (P5–P95) son: PEM 512–603 kW; eólica PPA 3,3–4,3 MW; buffer 9–26 h.

### Escenarios aparte (€/t, caso base)

| Escenario | Venta de O2 (80–100 €/t) | H2 Pioneros 40 % | Hydrogen Bank 0,84 €/kg (hipotético) | Todo junto |
|---|---|---|---|---|
| PPA + red | 3036 | 3047 | 3065 | 2817 (2696–3562) |
| FV en cubierta + red auxiliares | 3985 | 3756 | 4023 | 3535 |
| Aislado FV + batería | 4208 | 4004 | 4237 | 3772 |

Notas sobre estas ayudas e ingresos:
- **H2 Pioneros:** las convocatorias de 2022–2023 están cerradas. La intensidad (40/50/60 % según tamaño de empresa) se aplica solo al PEM y al almacenamiento de H2.
- **Hydrogen Bank:** exige un mínimo de 5 MWe (pendiente de verificar en las bases), así que el piloto **no es elegible**. Se incluye solo como cota.
- **Venta de O2:** es ingreso bruto, sin coste de purificación ni logística.
- Ninguna combinación se acerca al amoníaco gris (383–562 €/t).

## 3. Cumplimiento RFNBO (Reglamentos Delegados 2023/1184 y 2023/1185)

| Escenario | Mensual (≤2029) | Horaria (≥2030) | % renovable (lectura A) | GEI (gCO2e/MJ; límite 28,2) | Adicionalidad |
|---|---|---|---|---|---|
| PPA + red | Cumple | Cumple | 100 % | 0 | Condicionada (ver abajo) |
| PPA, modo 3 | Cumple | Cumple | 100 % | 0 | Condicionada |
| FV in situ + red auxiliares (suelo o cubierta) | No al 100 % | No al 100 % | 90,5–90,6 % | 12,2–12,3 (cumple GEI) | Art. 3: FV con ≤ 36 meses de antigüedad |
| Aislado FV + batería | Cumple | Cumple | 100 % | 0 | Art. 3 |
| Red spot | No | No | 0 % | 128 | No |

**Criterios aplicados** (texto consolidado de 2023/1184, CELEX 02023R1184-20240610):
- **Art. 3, conexión directa:** la electricidad cuenta como totalmente renovable si la instalación renovable entró en servicio como máximo 36 meses antes que la planta de RFNBO. Si además hay conexión a red, un contador inteligente debe demostrar que no se importa electricidad de red para producir el combustible.
- **Art. 4, electricidad de red:** España no cumple la vía de más del 90 % de renovables ni la de menos de 18 gCO2e/MJ (factor de red 54,1). Por tanto necesita un PPA con adicionalidad (art. 5), correlación temporal (art. 6) y correlación geográfica (art. 7).
- **Correlación geográfica:** la zona de oferta ES cumple.
- **Art. 11, transitorio:** las plantas en servicio **antes del 1-1-2028** quedan exentas de la adicionalidad del art. 5(a)(b) hasta el 1-1-2038. Si el piloto entra en servicio más tarde, el PPA debe proceder de una planta nueva (≤ 36 meses) y sin ayudas. Además, el precio P25 de LevelTen usado en el modelo puede no corresponder a planta nueva.

**PPA + red.** El óptimo sobredimensiona el PPA (unas 9 veces la potencia del PEM; se revende el 41 % de la energía del PPA, acreditada al menor de OMIE y el precio PPA). Con el perfil nacional de Energy-Charts, la demanda queda cubierta hora a hora, de modo que la correlación horaria **no encarece** el LCOA: el modo 3 da el mismo resultado. Este resultado depende de usar el perfil nacional; el perfil horario de una planta concreta puede dar huecos (riesgo; paso p3).

**FV in situ con red para auxiliares.** La red aporta alrededor del 9,5 % de la electricidad, para los auxiliares de noche, y no tiene PPA.
- **Lectura A** (toda la electricidad cuenta): solo ese 90,5 % sería RFNBO.
- **Lectura B** (solo PEM y compresión deben ser renovables; los auxiliares solo cuentan en el GEI): 100 % renovable, y cumpliría.
- Esta interpretación queda **pendiente de dictamen** (paso p4). Para cumplir con seguridad: batería para los auxiliares (escenario aislado, +224 €/t) o un PPA.

**No modelado:** contar la red con la cuota renovable nacional (59,7 % en 2024, art. 27(3) de RED), ni las garantías de origen horarias.

## 4. Supuestos críticos y limitaciones

- No hay datos experimentales. El CAPEX del HB, la PSA y el PEM a escala piloto, el arranque del HB y la carga mínima siguen basados en literatura (ver v2).
- Las rentas de alquiler son de naves, no de suelo. La superficie, el número de FTE y la distancia de la línea son **supuestos sin fuente**, con rangos amplios.
- El caso "FV en cubierta o suelo sin alquiler" supone superficie disponible sin coste (unos 2,6–4 ha equivalentes). Es una hipótesis, no un hecho.
- La correlación mensual usa meses de 730,5 h, una aproximación. Factor de red de 54,1 gCO2e/MJ (anexo de 2023/1185, dato de 2020). EUA fijo en 65 €/t para el umbral de excepción de precio.
- El Monte Carlo reoptimizado usa evolución diferencial reducida: n = 64, población 8 e iteraciones 35, frente a 12 y 60 en el óptimo base. Puede quedarse algo por encima del óptimo real.
- Nada de lo anterior es asesoramiento jurídico.

## 5. Próximos pasos verificables

| ID | Paso | Criterio de aceptación (medible) | Entregable | Plazo |
|---|---|---|---|---|
| p1 | Cotizar suelo industrial (no nave) de 1500–5000 m² en El Prat o Zona Franca | ≥ 3 ofertas escritas con €/m²/mes y uso químico permitido | `data/cotizaciones_suelo.csv` y delta de LCOA | 4 sem |
| p2 | Cotizaciones de HB + PSA modular de 1–2 t/d y PEM de 0,5–1 MW | ≥ 2 por equipo, con CAPEX, carga mínima, rampa y tiempo de arranque | `data/cotizaciones_equipos.csv` | 8 sem |
| p3 | Ofertas de PPA eólico + FV de 1–5 MW de planta nueva, a través de agregador | ≥ 2 ofertas con precio, perfil horario y fecha de puesta en servicio | `data/ofertas_ppa.csv` y verificación de los art. 5 y 6 | 8 sem |
| p4 | Dictamen RFNBO sobre lectura A frente a B y aplicación del art. 11 | Respuesta escrita de asesor o certificadora (ISCC, REDcert o CertifHy) a 3 preguntas | `docs/dictamen_rfnbo.md` | 6 sem |
| p5 | Datos de arranque del HB (fabricante o ensayo E3) | H2 perdido y parada mínima con incertidumbre ≤ 25 % | `data/arranque_hb.json` | 12 sem |
| p6 | Plantilla operativa del piloto | FTE por turno justificados; salarios del convenio químico | `docs/plantilla_piloto.md` | 4 sem |
| p7 | Consulta a e-distribución sobre el punto de conexión | Pliego técnico-económico con € y km | `data/conexion_red.json` | 10 sem |
| p8 | Validar el núcleo del modelo frente a un caso publicado | LCOA reproducido dentro de ±10 % | `validacion/caso_referencia.md` | 3 sem |

**Próximo paso inmediato:** p1 y p3 en paralelo, porque suelo y PPA suponen cerca del 55 % del LCOA del escenario PPA. Después, p2 y p4, y reoptimización en v4.
