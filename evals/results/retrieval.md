# Evaluación de recuperación — 34 preguntas del golden set (k=5)

| Config | Búsqueda | Reranking | hit@5 | recall@5 | MRR@5 | Latencia p50 (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| A | Vectorial | No | 0.94 | 0.87 | 0.74 | 12 |
| B | Híbrida | No | 0.79 | 0.72 | 0.62 | 21 |
| C | Vectorial | Sí (50) | 0.94 | 0.84 | 0.67 | 11125 |
| D | Híbrida | Sí (50) | 0.88 | 0.78 | 0.64 | 13989 |
| E | Híbrida | Sí (20) | 0.91 | 0.82 | 0.69 | 5743 |

## MRR@5 por pregunta

| Pregunta | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Q01 ¿Cuántos días de vacaciones me corresponden al año? | 0.25 | 1.00 | 0.50 | 0.50 | 0.50 |
| Q02 Llevo 13 años trabajando, ¿me dan más días de vacaciones por | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 |
| Q03 ¿Puedo dividir mis vacaciones en varias partes o juntar las  | 1.00 | 0.25 | 1.00 | 1.00 | 1.00 |
| Q04 ¿Mi jefe me puede pagar las vacaciones en plata en vez de dá | 0.50 | 0.00 | 0.20 | 0.00 | 0.25 |
| Q05 ¿Cuántas horas a la semana es lo máximo que me pueden hacer  | 0.33 | 0.00 | 0.33 | 0.33 | 0.33 |
| Q06 ¿Cuántas horas extra puedo hacer al día y cuánto me las tien | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q07 ¿Tengo derecho a un tiempo para almorzar en el trabajo? | 0.33 | 0.00 | 0.00 | 0.00 | 0.00 |
| Q08 ¿Me pueden obligar a trabajar los domingos? | 0.50 | 1.00 | 0.20 | 0.20 | 0.20 |
| Q09 Empecé a trabajar hace tres semanas y todavía no me hacen fi | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q10 ¿Cuánto puede durar como máximo un contrato a plazo fijo? | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q11 ¿Cada cuánto tiempo me tienen que pagar el sueldo? | 1.00 | 0.00 | 0.25 | 0.25 | 0.33 |
| Q12 ¿Qué descuentos me pueden hacer del sueldo? | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |
| Q13 ¿Qué es la gratificación y cuánto me corresponde? | 0.50 | 0.25 | 0.25 | 0.25 | 0.33 |
| Q14 Falleció mi papá, ¿cuántos días de permiso me dan en el trab | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q15 Me voy a casar, ¿tengo días libres pagados? | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q16 Me echaron por necesidades de la empresa después de 6 años,  | 1.00 | 1.00 | 0.33 | 0.33 | 0.50 |
| Q17 ¿Me tienen que avisar con anticipación antes de despedirme? | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q18 ¿Por qué razones me pueden despedir sin pagarme nada de inde | 0.00 | 0.00 | 1.00 | 0.50 | 1.00 |
| Q19 ¿Qué tiene que decir la carta de despido y cuándo me la tien | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q20 Quiero renunciar, ¿con cuánta anticipación tengo que avisar? | 0.00 | 0.00 | 0.20 | 0.00 | 0.00 |
| Q21 Me despidieron injustamente, ¿hasta cuándo tengo plazo para  | 0.50 | 0.33 | 0.50 | 0.50 | 0.50 |
| Q22 ¿El finiquito tiene que ser firmado ante un ministro de fe? | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q23 Estoy embarazada, ¿me pueden despedir? | 0.50 | 0.25 | 0.25 | 0.25 | 0.33 |
| Q24 ¿Cuántas semanas dura el prenatal y el postnatal? | 0.25 | 0.20 | 0.33 | 0.33 | 0.33 |
| Q25 ¿Qué es el postnatal parental y cuánto dura? | 1.00 | 1.00 | 0.50 | 0.50 | 0.50 |
| Q26 ¿La empresa está obligada a darme sala cuna para mi hijo? | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q27 ¿Tengo derecho a salir del trabajo para darle leche a mi gua | 1.00 | 1.00 | 0.50 | 0.50 | 1.00 |
| Q28 Hago teletrabajo, ¿mi jefe me puede escribir a cualquier hor | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q29 Mi jefe me humilla y me hostiga todos los días, ¿eso es acos | 0.50 | 0.50 | 1.00 | 1.00 | 1.00 |
| Q30 ¿Cuánto tiempo tengo para reclamar derechos laborales que no | 1.00 | 0.25 | 1.00 | 1.00 | 1.00 |
| Q31 ¿Cuántos trabajadores se necesitan para formar un sindicato  | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q32 Si estamos en huelga, ¿la empresa puede contratar a otros pa | 1.00 | 1.00 | 0.33 | 0.33 | 0.50 |
| Q33 Soy nana puertas afuera, ¿cuántas horas puedo trabajar a la  | 1.00 | 0.50 | 0.00 | 0.00 | 0.00 |
| Q34 ¿El empleador tiene la obligación de protegerme de accidente | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 |
