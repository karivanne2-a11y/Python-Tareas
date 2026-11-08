# Verificación independiente de cifras del informe

Cada afirmación se recalculó por un camino distinto al del agente (sin el MCP ni las Skills). Generado por `agente/verificar.py`.

| Afirmación del informe | Valor del informe | Valor verificado | Procedimiento | ¿Coincide? | Diferencia |
|---|---:|---:|---|:---:|---:|
| Crédito directo total a fines de 2024 (millones de S/) | 407,351.74 | 407,351.74 | API del BCRP con httpx, serie RD16202DA, sin MCP | Sí | +0.0000 |
| Suma de los 25 departamentos = total nacional (millones de S/) | 407,351.74 | 407,351.74 | Suma de las series departamentales vs total nacional del BCRP | Sí | -0.000 |
| Tasa de referencia a dic-2024 (%) | 5.00 | 5.00 | API del BCRP con httpx, serie PD04722MM | Sí | +0.000 |
| Pobreza monetaria nacional 2024 (%) | 27.58 | 27.58 | Lectura directa de sumaria-2024.dta con factor07 × mieperho (sin Skills). Referencia INEI: 27.6 % | Sí | +0.001 |
| Pobreza en Cajamarca 2024 (%) | 45.01 | 45.0 | Referencia de la Sesión 16 (redondeada a 1 decimal) | Sí | +0.01 |
| Spearman crédito per cápita vs pobreza (n=25) | -0.604 | -0.604 | scipy.stats.spearmanr sobre salidas/credito_pobreza_departamento.csv | Sí | -0.0000 |
| Pendiente de pobreza sobre ln(crédito per cápita) | -8.704 | -8.704 | scipy.stats.linregress sobre el CSV del cruce | Sí | +0.0001 |

Resultado: 7/7 verificaciones coinciden.

## Comprobación manual de la estudiante (8 de noviembre de 2026)

Comprobadas a mano, abriendo la fuente en el navegador o el archivo de validación, y comparando con el informe.

| Afirmación del informe | Valor del informe | Fuente o procedimiento | ¿Coincide? | Diferencia observada |
|---|---:|---|:---:|---|
| Crédito directo total a fines de 2024 (millones de S/) | 407,351.74 | API del BCRP en el navegador: `.../api/RD16202DA/json/2024/2024` | Sí | Ninguna |
| Tasa de referencia a dic-2024 (%) | 5.00 | API del BCRP en el navegador: `.../api/PD04722MM/json/2024-12/2024-12` | Sí | Ninguna |
| Pobreza monetaria nacional 2024 (%) | 27.58 | `salidas/validacion.txt` frente al 27.6 % de referencia del enunciado | Sí | 0.02 pp, por redondeo de la referencia |
