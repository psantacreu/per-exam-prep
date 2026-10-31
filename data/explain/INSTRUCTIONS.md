# Explicaciones para el banco de preguntas PER

Cada lote (`data/explain/batches/batch_NN.json`) es una lista de preguntas tipo test del examen
teórico de Patrón de Embarcaciones de Recreo (PER, Catalunya). Cada elemento tiene:

- `key`: identificador (cópialo tal cual en la salida)
- `tema`, `pregunta`, `opciones` (a–d), `correcta` (letra; si hay varias, todas se aceptaron)
- `figura` (opcional): ruta absoluta a un PNG con el dibujo al que se refiere la pregunta.
  Ábrelo con la herramienta Read cuando la pregunta dependa del dibujo.

## Qué escribir

Para cada pregunta, una explicación en **español** de 2 a 4 frases (unas 40–90 palabras) que ayude
a un alumno a entender y recordar la respuesta:

- Di por qué la opción correcta es correcta, con la regla o el concepto de fondo
  (p. ej. regla del RIPA, sistema de balizamiento IALA región A, definiciones de nomenclatura).
- Cuando ayude, indica brevemente por qué falla el distractor más tentador.
- Si existe una regla mnemotécnica conocida, inclúyela.
- No empieces con "La respuesta correcta es…" ni repitas la pregunta; ve directo al porqué.
- Texto plano, sin Markdown.

Preguntas de carta náutica, mareas o cálculos (rumbo, demora, desvío, declinación, distancia,
velocidad, hora de llegada, sonda): no tienes la carta del Estrecho ni el anuario de mareas,
así que **no inventes valores leídos de la carta**. Explica el procedimiento (fórmulas como
Rv = Ra + Ct, Ct = dm + Δ, d = v·t, actualización de la declinación, sonda = sonda carta + altura
de marea, etc.) y, si los datos del enunciado bastan, haz el cálculo y comprueba que da la opción
correcta.

Si crees que la clave oficial (`correcta`) es errónea, no la cambies: explica igualmente la
respuesta dada y añade el campo `duda` con una frase sobre el posible error.

## Salida

Escribe con la herramienta Write un único fichero JSON en
`data/explain/out/batch_NN.json` (mismo número que el lote) con esta forma, cubriendo
**todas** las `key` del lote:

```json
{
  "3f2a9c1b7d0e": {"exp": "Explicación…"},
  "a1b2c3d4e5f6": {"exp": "Explicación…", "duda": "Posible error en la clave: …"}
}
```

Comprueba antes de terminar que el JSON es válido y que no falta ninguna `key` (por ejemplo con
`python3 -c` leyendo ambos ficheros). Responde al final solo con el número de explicaciones escritas
y cuántas tienen `duda`.
