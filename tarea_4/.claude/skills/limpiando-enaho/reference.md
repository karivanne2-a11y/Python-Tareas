# Referencia técnica: ENAHO 2024

## Archivos
| Módulo | Archivo | Una fila por | Filas | Llaves | Factor |
|---|---|---|---|---|---|
| 34 sumaria | `sumaria-2024.dta` | hogar | 33,691 | `conglome`, `vivienda`, `hogar` | `factor07` |
| 02 miembros | `Enaho01-2024-200.dta` | persona | 117,721 | las tres + `codperso` | `facpob07` |

## Reglas
- Leer con `pd.read_stata(..., convert_categoricals=False)`. Pasar las columnas a minúscula (el año llega como `aÑo`).
- Las llaves y el `ubigeo` van como **texto de ancho fijo**: conglome 6, vivienda 3, hogar 2, codperso 2, ubigeo 6. Si se leen como número se pierden los ceros iniciales y el merge falla.
- Residente habitual: `((p204 == 1) & (p205 == 2)) | ((p204 == 2) & (p206 == 1))` → 108,664 de 117,721.
- Unión: `merge(personas, hogares, on=[conglome, vivienda, hogar], validate="m:1")`.
- `departamento = ubigeo[:2]` (25 códigos; Lima = 15, Callao = 07, separados).
- `urbano = estrato <= 5`. `pobre = pobreza <= 2` (1 extremo, 2 no extremo, 3 no pobre). `pobre_extremo = pobreza == 1`.

## Dos formas válidas de estimar la pobreza nacional
| Método | Resultado |
|---|---|
| Sumaria, `factor07 × mieperho` (método oficial del INEI, por hogares) | 27.58 % |
| Personas residentes, `facpob07` | 27.53 % |

Ambas están dentro de ±0.1 pp de 27.6 %. **Por departamento solo el método de la sumaria reproduce la referencia de la Sesión 16** (diferencia máxima 0.05 pp; con personas y `facpob07` llega a 0.52 pp, en Puno). Por eso `indicadores.csv`, los gráficos de área/departamento y el mapa usan hogares con `factor07 × mieperho` (se toma un registro por hogar); solo sexo usa personas con `facpob07`. La columna `metodo` de `indicadores.csv` lo indica.

## Variables de la base procesada
`conglome, vivienda, hogar, codperso, ubigeo, departamento, dominio, estrato, urbano, area, sexo, edad, pobreza, pobre, pobre_extremo, facpob07, factor07, mieperho`.

## Trampas
- Promedio simple de `pobre` (≈ 20-26 %) ≠ estimación ponderada (≈ 27.5 %).
- Unir por nombre de departamento ("APURIMAC" ≠ "Apurímac"): unir siempre por código.
- No interpretar diferencias como causales.
