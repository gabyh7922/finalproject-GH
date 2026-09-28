# CAG — salida real (primera prueba, prompt legal_answer v1, claude-opus-5)

**Pregunta:** ¿Cuántos días de vacaciones me corresponden si llevo 2 años trabajando?

**Respuesta corta:** Con 2 años trabajando te corresponden 15 días hábiles de feriado anual con
remuneración íntegra, ya que el derecho nace al cumplir más de un año de servicio. Si trabajas en
las regiones de Magallanes, Aysén o la provincia de Palena, son 20 días hábiles. Los días
adicionales por antigüedad solo empiezan a los 10 años de trabajo.

| Afirmación (resumida) | Cita | Verificación |
|---|---|---|
| Más de un año de servicio → 15 días hábiles pagados | art-67 | ✅ verified |
| Magallanes, Aysén, Palena → 20 días hábiles | art-67 | ✅ verified |
| El sábado se considera inhábil para el feriado | art-69 | ✅ verified |
| Días extra por antigüedad desde 10 años de trabajo | art-68 | ✅ verified |
| El feriado es continuo; se fracciona solo el exceso sobre 10 días | art-70 | ✅ verified |
| No se compensa en dinero mientras dure la relación laboral | art-73 | ✅ verified |

**Uso de tokens:** entrada sin caché 43 · escritura de caché 366.717 · salida 1.220 · latencia 20,5 s.

**Costo:** ~US$3,7 (escritura de caché con TTL de 1h = 2× el precio de entrada).

**Lecciones que cambiaron el diseño:**
1. El contexto ocupaba 367k tokens porque la ruta jerárquica se repetía en cada artículo → ahora
   se escribe una vez por sección.
2. El TTL de 1h duplica el costo de escritura; para ráfagas de evals basta el de 5 min (1,25×).
3. Aun optimizado, CAG paga ~260k tokens por consulta nueva: es el argumento principal para RAG.
