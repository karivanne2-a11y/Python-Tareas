# Series del BCRP verificadas (catálogo y API consultados el 2026-11-08)

Catálogo: `https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata` (17 167 series).
API: `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{codigo}/json/{inicio}/{fin}/ep`

## Crédito directo del sistema financiero al sector privado, por departamento
Grupo: "Crédito directo del sistema financiero al sector privado por departamentos - fin de periodo (millones S/)".
Cobertura 2004–2025, frecuencias anual (`...DA`), mensual (`...DM`) y trimestral. Por departamento hay tres series: moneda nacional, moneda extranjera y total. Hay 25 unidades (Lima y Callao separados) más "Total".

Códigos anuales "(total)":

| Código | Unidad | Código | Unidad |
|---|---|---|---|
| RD16127DA | Amazonas | RD16172DA | Loreto |
| RD16130DA | Ancash | RD16175DA | Madre de Dios |
| RD16133DA | Apurímac | RD16178DA | Moquegua |
| RD16136DA | Arequipa | RD16181DA | Pasco |
| RD16139DA | Ayacucho | RD16184DA | Piura |
| RD16142DA | Cajamarca | RD16187DA | Puno |
| RD16145DA | Callao | RD16190DA | San Martín |
| RD16148DA | Cusco | RD16193DA | Tacna |
| RD16151DA | Huancavelica | RD16196DA | Tumbes |
| RD16154DA | Huánuco | RD16199DA | Ucayali |
| RD16157DA | Ica | RD16202DA | Total nacional |
| RD16160DA | Junín | RD16163DA | La Libertad |
| RD16166DA | Lambayeque | RD16169DA | Lima |

Prueba de la API (Amazonas total, millones de S/): 2020 = 750.09, 2021 = 829.04, 2022 = 946.33, 2023 = 1043.38, 2024 = 1076.92.

Los depósitos por departamento también existen (mismo grupo "Sistema financiero").

## Tasas nacionales (mensuales, 1993/2004–2025)
- `PD04722MM`: Tasa de referencia de la política monetaria (6.5 % en ene-2024, 5.0 % en dic-2024).
- `PN07807NM`: Tasa activa TAMN (15.81 % en ene-2024, 14.88 % en dic-2024).

## Pendiente
- Verificar la serie de crédito en dólares si se quiere separar moneda nacional/extranjera.
- Elegir denominador de población: suma de `facpob07` de ENAHO (residentes habituales), declarado en el informe.
