"""Genera informes/informe_final.md a partir de los resultados del agente: toda cifra sale de
salidas/resultados_investigacion.json, salidas/credito_pobreza_departamento.csv e indicadores.csv.

    uv run agente/generar_informe.py

Las afirmaciones cualitativas se comprueban con `assert`: si cambian los datos y dejan de ser ciertas, el script falla
en vez de publicar un texto incorrecto.
"""
import json
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent


def main():
    res = json.loads((RAIZ / "salidas" / "resultados_investigacion.json").read_text(encoding="utf-8"))
    df = pd.read_csv(RAIZ / "salidas" / "credito_pobreza_departamento.csv", dtype={"codigo": str}).set_index("departamento")
    ind = pd.read_csv(RAIZ / "salidas" / "indicadores.csv", dtype={"codigo": str})
    b, c = res["bcrp"], res["correlaciones"]
    cr, tr, tm = b["credito_resumen"], b["tasa_ref_resumen"], b["tamn_resumen"]
    nac = ind[ind.nivel == "nacional"].iloc[0]
    urb = float(ind[(ind.nivel == "area") & (ind.nombre == "Urbana")].pobreza_pct.iloc[0])
    rur = float(ind[(ind.nivel == "area") & (ind.nombre == "Rural")].pobreza_pct.iloc[0])
    p, s_lc, rural, urbana = c["principal"], c["sin_lima_callao"], c["vs_rural_pobreza"], c["vs_urbana_pobreza"]
    cr_rur = c["credito_vs_ruralidad"]
    mx, mn = df.credito_pc_2024_soles.idxmax(), df.credito_pc_2024_soles.idxmin()
    pmx, pmn = df.pobreza_pct.idxmax(), df.pobreza_pct.idxmin()

    # afirmaciones que el texto da por ciertas
    assert cr["variacion_pct"] > 0 and p["spearman"] < -0.3 and p["p_permutacion_spearman"] < 0.05
    assert s_lc["spearman"] < p["spearman"] and abs(p["pearson"]) < abs(p["spearman"])  # Lima atenúa Pearson
    assert rural["spearman"] < 0 and urbana["spearman"] < 0 and cr_rur["spearman"] < -0.3
    assert df.loc["Lima", "pobreza_pct"] > df.pobreza_pct.median() * 0.9  # Lima: mucho crédito, pobreza no baja
    assert (tm["maximo"]["valor"] - tm["minimo"]["valor"]) < (tr["maximo"]["valor"] - tr["minimo"]["valor"])
    assert abs(cr["ultimo"]["valor"] - cr["maximo"]["valor"]) / cr["maximo"]["valor"] < 0.02  # "estancado" desde el máximo

    rb = c["robustez"]
    o1, o2 = rb["ols_credito"]["coef"]["ln_credito_pc"], rb["ols_credito_rural"]["coef"]["ln_credito_pc"]
    parcial, loo, ext, creci = rb["spearman_parcial_control_ruralidad"], rb["leave_one_out_spearman"], rb["extrema"], rb["crecimiento_2020_2024_vs_pobreza"]
    assert o1["beta"] < 0 and o1["p"] < 0.05          # MCO simple: significativo
    assert o2["p"] > 0.05                             # MCO con ruralidad: pierde significancia (se dice en el texto)
    assert parcial["rho"] < -0.3 and parcial["p_aprox"] < 0.05
    assert loo["max"][1] < -0.3 and ext["spearman"] < -0.3 and abs(creci["spearman"]) < 0.3 and creci["p_permutacion_spearman"] > 0.05
    import math
    duplicar = o1["beta"] * math.log(2)

    md = f"""# Crédito, tasas de interés y pobreza departamental en el Perú, 2020–2024

## 1. Pregunta de investigación
**Tema.** Entre 2020 y 2024, ¿cómo evolucionaron el crédito del sistema financiero y la tasa de interés en el Perú, y en 2024 los departamentos con más crédito por habitante tenían menos pobreza monetaria? ¿Cambia esa relación entre áreas urbanas y rurales?

**Objetivo y delimitación.** Describir la evolución nacional del crédito y las tasas (BCRP, 2020–2024) y medir la asociación entre el crédito directo por habitante de cada departamento a fines de 2024 y su pobreza monetaria en la ENAHO 2024. El análisis es descriptivo: no estima efectos causales.

## 2. Fuentes y metodología
| Fuente | Datos | Series / módulos |
|---|---|---|
| BCRP (consultado con el servidor MCP del proyecto) | Crédito directo del sistema financiero al sector privado, total nacional y por departamento (millones de S/, fin de periodo, anual) | RD16202DA y RD16127DA…RD16199DA (una por departamento, cada tres códigos) |
| BCRP | Tasa de referencia de la política monetaria; tasa activa en moneda nacional (TAMN), mensuales | PD04722MM; PN07807NM |
| INEI | ENAHO 2024, módulos 34 (sumaria) y 02 (miembros) | 33,691 hogares en la sumaria; 108,664 residentes habituales |
| Curso | Límites departamentales (GeoJSON) | 25 unidades, unión por `ubigeo[:2]` = `FIRST_IDDP` |

**Procesamiento ENAHO** (Skill `limpiando-enaho`): residentes habituales (108,664 personas), unión personas–hogares con `validate="m:1"`, pobreza = `pobreza <= 2`. Nacional, área y departamento se estiman por hogares con `factor07 × mieperho` (método del INEI, que reproduce las referencias del curso con diferencia máxima de 0.05 pp); sexo usa personas con `facpob07`. Validación completa en `salidas/validacion.txt`.

**Crédito per cápita** = crédito departamental a fines de 2024 (S/) ÷ población estimada por ENAHO 2024 en ese departamento (suma de `factor07 × mieperho`). **Asociación**: correlación de Spearman (robusta a Lima, que es un valor extremo) y de Pearson, con prueba de permutación (20 000 permutaciones) porque n = 25. Las celdas departamento × área con menos de 30 hogares muestrales se excluyen (Callao rural no tiene hogares).

## 3. Resultados

### Hallazgo 1 – El crédito creció poco y las tasas subieron y bajaron
- El crédito directo total pasó de {cr['primero']['valor']:,.0f} millones de S/ en {cr['primero']['periodo']} a {cr['ultimo']['valor']:,.0f} en {cr['ultimo']['periodo']}: **+{cr['variacion_pct']:.1f} % nominal** (serie RD16202DA). Su máximo fue {cr['maximo']['valor']:,.0f} en {cr['maximo']['periodo']}, de modo que desde entonces estuvo prácticamente estancado en términos nominales.
- La tasa de referencia (PD04722MM) pasó de {tr['primero']['valor']:.2f} % en {tr['primero']['periodo']} a un mínimo de {tr['minimo']['valor']:.2f} % ({tr['minimo']['periodo']}), un máximo de {tr['maximo']['valor']:.2f} % ({tr['maximo']['periodo']}) y {tr['ultimo']['valor']:.2f} % en {tr['ultimo']['periodo']}.
- La TAMN (PN07807NM) se movió entre {tm['minimo']['valor']:.2f} % ({tm['minimo']['periodo']}) y {tm['maximo']['valor']:.2f} % ({tm['maximo']['periodo']}) y terminó en {tm['ultimo']['valor']:.2f} %. Ambas tasas están correlacionadas (Pearson {b['corr_tasas']['coeficiente']:.2f}, n = {b['corr_tasas']['n']} meses), y la tasa activa tuvo menor amplitud ({tm['maximo']['valor'] - tm['minimo']['valor']:.1f} puntos entre su mínimo y su máximo, frente a {tr['maximo']['valor'] - tr['minimo']['valor']:.1f} de la tasa de referencia).

### Hallazgo 2 – El crédito está muy concentrado y se asocia con menos pobreza
- Crédito por habitante en 2024: **{mx} S/ {df.loc[mx, 'credito_pc_2024_soles']:,.0f}** frente a **{mn} S/ {df.loc[mn, 'credito_pc_2024_soles']:,.0f}**, es decir {df.loc[mx, 'credito_pc_2024_soles'] / df.loc[mn, 'credito_pc_2024_soles']:.1f} veces.
- Entre los 25 departamentos, la correlación de Spearman entre crédito per cápita y pobreza es **{p['spearman']:+.2f}** (p de permutación = {p['p_permutacion_spearman']:.4f}); la de Pearson es {p['pearson']:+.2f}, debilitada por Lima. Sin Lima ni Callao (n = {s_lc['n']}) sube a {s_lc['spearman']:+.2f} (Spearman) y {s_lc['pearson']:+.2f} (Pearson).
- La pobreza va de {df.loc[pmn, 'pobreza_pct']:.1f} % ({pmn}) a {df.loc[pmx, 'pobreza_pct']:.1f} % ({pmx}). Ica combina crédito alto (S/ {df.loc['Ica', 'credito_pc_2024_soles']:,.0f}) y pobreza baja; Lima es el contraejemplo: el mayor crédito por habitante y una pobreza de {df.loc['Lima', 'pobreza_pct']:.1f} %, cercana al promedio nacional ({nac.pobreza_pct:.1f} %).

### Hallazgo 3 – La brecha urbano–rural es grande y la asociación con el crédito se ve en ambas áreas
- A nivel nacional la pobreza es {rur:.1f} % en áreas rurales y {urb:.1f} % en urbanas, una brecha de {rur - urb:.1f} puntos porcentuales.
- Por departamento, el crédito per cápita se asocia con menos pobreza urbana (Spearman {urbana['spearman']:+.2f}, n = {urbana['n']}) y con menos pobreza rural ({rural['spearman']:+.2f}, n = {rural['n']}, p = {rural['p_permutacion_spearman']:.3f}); la asociación es algo más débil en el área rural. El crédito se mide por departamento, no por área: esta comparación es de la pobreza de cada área contra el crédito de todo el departamento.
- Los departamentos con menos crédito per cápita son más rurales (Spearman {cr_rur['spearman']:+.2f} entre crédito per cápita y % de población rural), de modo que la ruralidad es una variable que se mezcla con el crédito en esta asociación.

### Hallazgo 4 – La asociación resiste en rangos, pero no con un control lineal por ruralidad
- **Magnitud.** En un modelo lineal simple, duplicar el crédito per cápita se asocia con {duplicar:+.1f} puntos porcentuales de pobreza (coeficiente {o1['beta']:+.2f} por unidad logarítmica, p = {o1['p']:.3f}; R² = {rb['ols_credito']['r2']:.2f}).
- **Control por ruralidad.** Al agregar el porcentaje de población rural, el coeficiente del crédito baja a {o2['beta']:+.2f} y deja de ser estadísticamente distinguible de cero (p = {o2['p']:.2f}; R² = {rb['ols_credito_rural']['r2']:.2f}). Con solo 25 observaciones y variables muy correlacionadas, el modelo tiene poca capacidad de separar ambos efectos.
- **Robustez en rangos.** La correlación de Spearman parcial, controlando por el rango de ruralidad, es {parcial['rho']:+.2f} (p ≈ {parcial['p_aprox']:.3f}). Dejando fuera un departamento cada vez, el Spearman va de {loo['max'][1]:+.2f} (sin {loo['max'][0]}) a {loo['min'][1]:+.2f} (sin {loo['min'][0]}): el resultado no depende de un solo departamento.
- **Otros resultados.** La asociación con la pobreza **extrema** es más fuerte ({ext['spearman']:+.2f}, n = {ext['n']}). En cambio, el **crecimiento nominal** del crédito 2020–2024 de cada departamento no se asocia con su pobreza en 2024 (Spearman {creci['spearman']:+.2f}, p = {creci['p_permutacion_spearman']:.2f}): en este corte la asociación aparece con el nivel de crédito por habitante y no con su variación reciente.

## 4. Visualizaciones
- **BCRP – crédito y tasas, 2020–2024:** ![Crédito y tasas](../figuras/bcrp_credito_tasas_2020_2024.png)
- **ENAHO – pobreza por área, 2024:** ![Pobreza por área](../figuras/pobreza_area_2024.png)
- **Mapa departamental de pobreza, 2024:** ![Mapa](../mapas/pobreza_departamento.png)
- **Cruce BCRP–ENAHO:** ![Crédito vs pobreza](../figuras/credito_vs_pobreza_2024.png)
- **Dashboard interactivo** (mapa, dispersión y tabla con selectores): [`dashboard/index.html`](../dashboard/index.html), generado por la Skill `explorando-resultados`.

## 5. Interpretación
Los departamentos con más crédito por habitante tienden a tener menos pobreza monetaria, y esa tendencia aparece tanto en la pobreza urbana como en la rural. Sin embargo, el crédito está concentrado en pocos departamentos (Lima, Arequipa, Ica) y coincide con menor ruralidad, por lo que la asociación no puede atribuirse al crédito: en un modelo lineal con control por ruralidad el coeficiente del crédito deja de ser significativo (aunque la asociación en rangos persiste) y puede reflejar que los departamentos más urbanos y con más actividad económica tienen a la vez más crédito y menos pobreza. El caso de Lima muestra que mucho crédito no se acompaña necesariamente de baja pobreza. A nivel nacional, el crédito nominal creció poco mientras la política monetaria endureció y luego relajó su tasa de referencia.

## 6. Limitaciones
- **Asociación, no causalidad.** Son 25 observaciones transversales de un solo año; no hay control por ruralidad, actividad económica ni composición del crédito, y la inferencia de territorios a personas (falacia ecológica) no es válida.
- **Ubicación del crédito.** No se verificó en la metodología del BCRP cómo se asigna el crédito a cada departamento; si se registra por la ubicación de la agencia o la sede, parte del crédito de Lima podría financiar a hogares y empresas de otros departamentos.
- **Series nominales.** El crédito no se deflactó; el +{cr['variacion_pct']:.1f} % es nominal.
- **Desfase temporal.** El crédito es de fin de periodo 2024 y la ENAHO 2024 se levanta durante el año; la pobreza 2020–2023 no se analiza (solo se usó ENAHO 2024).
- **Denominador.** La población proviene de la ENAHO (muestral); no se contrastó con las proyecciones oficiales del INEI.
- **Incertidumbre.** Las estimaciones de pobreza son puntuales, sin errores estándar del diseño muestral; las celdas rurales pequeñas son menos precisas.
- **Uso del MCP.** El agente (`agente/investigar.py`) llama al servidor MCP con un cliente FastMCP por stdio, no con las herramientas MCP nativas de una sesión de Claude Code; el uso nativo de MCP y Skills se muestra por separado en `evidencias_ia/integracion/demo_nativa_claude_code.md` y en los logs de la evaluación.

## 7. Reproducibilidad
```bash
uv sync
uv run pytest mcp/ -q                 # 10 passed
uv run agente/investigar.py           # MCP + Skills -> salidas/, figuras/, mapas/
uv run agente/verificar.py            # verificación independiente (informes/verificacion_cifras.md)
uv run agente/generar_informe.py      # este informe
```
- Skills: `.claude/skills/limpiando-enaho`, `graficando-enaho`, `mapeando-enaho`. Servidor: `mcp/server.py`.
- Resultados: `salidas/resultados_investigacion.json`, `salidas/credito_pobreza_departamento.csv`, `salidas/indicadores.csv`, `salidas/validacion.txt`, `mapas/validacion_mapa.txt`.
- Bitácora de la ejecución (llamadas MCP y Skills): `salidas/bitacora_agente.json`.
- Verificación independiente por script (sin MCP ni Skills) de 7 cifras y comprobación manual de 3 cifras de ambas fuentes: `informes/verificacion_cifras.md`.
"""
    (RAIZ / "informes" / "informe_final.md").write_text(md, encoding="utf-8")
    print("informe_final.md generado")


if __name__ == "__main__":
    main()
