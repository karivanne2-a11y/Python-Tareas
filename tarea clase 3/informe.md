# Informe – ¿Ayuda el MCP del INEI?

**Estudiante:** Karen Macedo (@karivanne2-a11y) · Sesión 04 · Data Science con Python

## La pregunta

¿Responde Claude mejor sobre estadísticas peruanas cuando puede consultar los datos del INEI,
en vez de contestar de memoria?

## El experimento

Diez preguntas con la cifra correcta verificada a mano en la web del INEI (`preguntas.csv`,
columnas `verdad` y `fuente_url`). Cada una se le hace a Claude Code dos veces:

- **Sin MCP** — `claude -p` con `--strict-mcp-config` y configuración vacía.
- **Con MCP** — el mismo comando, cargando `.mcp.json` (servidor `inei` y `fetch`).

En ambos casos la instrucción es la misma: responder solo con la cifra, o `null` si no la
sabe con certeza. Una respuesta cuenta como acierto si cae dentro del 2 % de la verdad.
«Dice null» se cuenta aparte de «se equivoca»: no es lo mismo no saber que inventar.

## Resultados

<!-- Pendiente: completar con resultados.csv después de `uv run evaluar.py`. -->

| | Acierta | Se equivoca | Dice null |
|---|---|---|---|
| Sin MCP | | | |
| Con MCP | | | |

![Aciertos con y sin el MCP del INEI](grafico.png)

## Dos cifras verificadas a mano

<!-- Pendiente: elegir dos preguntas del CSV y pegar aquí la cifra, su fuente y qué respondió
     Claude en cada modalidad. -->

| Pregunta | Verdad (fuente) | Sin MCP | Con MCP |
|---|---|---|---|
| | | | |
| | | | |

## Qué acertó, qué no, y por qué

<!-- Pendiente. Guía de lo que conviene mirar en resultados.csv:
     - ¿En qué preguntas el MCP cambió la respuesta y en cuáles no hizo diferencia?
     - ¿Hay casos donde sin MCP inventó una cifra plausible en vez de decir null?
     - ¿Hay casos donde con MCP eligió la serie equivocada? Mira la columna
       `respuesta_bruta` para ver qué código citó.
     - ¿Falló alguna por la detección automática de columnas del CSV del portal? -->

## Límites de este experimento

- Diez preguntas son pocas para distinguir una mejora real del azar; esto describe lo
  observado, no mide significancia.
- El catálogo solo cubre lo que el INEI publica en Datos Abiertos. Lo que vive únicamente en
  Perú en Cifras o SIRTOD queda fuera del alcance del servidor.
- Los CSV del portal no comparten formato: cuando la detección de columnas se equivoca, el
  error es del servidor, no del modelo. Conviene señalar esos casos aparte.
- La tolerancia del 2 % es una decisión mía; con otra holgura el conteo cambia.
