"""Calculadoras legales deterministas usadas como herramientas del agente.

Un LLM razona bien sobre qué regla aplica, pero la aritmética con fechas y
topes es exactamente donde se equivoca en silencio. Estas funciones hacen el
cálculo con código probado (tests/test_calculators.py) y devuelven también
las reglas y salvedades aplicadas, con su artículo, para que el agente las cite.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date


def _add_months(d: date, months: int) -> date:
    year, month0 = divmod(d.month - 1 + months, 12)
    return date(d.year + year, month0 + 1, min(d.day, 28))


def _months_between(start: date, end: date) -> int:
    """Meses completos entre dos fechas."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


@dataclass
class IndemnizacionResult:
    anos_servicio_computables: int
    dias_indemnizacion: int
    base_calculo_mensual: float
    indemnizacion_anos_servicio: float
    indemnizacion_sustitutiva_aviso: float
    total: float
    reglas: list[str] = field(default_factory=list)
    salvedades: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def calcular_indemnizacion(
    remuneracion_mensual: float,
    fecha_inicio: date,
    fecha_termino: date,
    aviso_con_30_dias: bool,
    valor_uf: float | None = None,
) -> IndemnizacionResult:
    """Indemnización legal por despido por necesidades de la empresa (arts. 161, 162, 163, 172)."""
    if fecha_termino <= fecha_inicio:
        raise ValueError("fecha_termino debe ser posterior a fecha_inicio")
    if remuneracion_mensual <= 0:
        raise ValueError("remuneracion_mensual debe ser positiva")

    reglas, salvedades = [], []
    months = _months_between(fecha_inicio, fecha_termino)
    full_years, extra_months = divmod(months, 12)
    # "fracción superior a seis meses": 6 meses exactos no suman; 6 meses y algunos días, sí.
    leftover_days = (fecha_termino - _add_months(fecha_inicio, months)).days
    fraction_over_six = extra_months > 6 or (extra_months == 6 and leftover_days > 0)

    base = remuneracion_mensual
    if valor_uf:
        tope = 90 * valor_uf
        if base > tope:
            base = tope
            reglas.append(f"art-172: la base de cálculo se limita a 90 UF (${tope:,.0f}).")
    else:
        salvedades.append("art-172: la base tiene tope de 90 UF; no se entregó el valor de la UF para aplicarlo.")

    if months < 12:
        years = 0
        reglas.append("art-163: la indemnización por años de servicio exige que el contrato haya estado vigente un año o más.")
    else:
        years = full_years + (1 if fraction_over_six else 0)
        reglas.append(
            "art-163: 30 días de la última remuneración mensual por cada año de servicio y fracción superior a seis meses."
        )
    days = min(30 * years, 330)
    if 30 * years > 330:
        reglas.append("art-163: límite máximo de 330 días de remuneración (11 años).")

    ias = round(base * days / 30)
    aviso = 0.0 if aviso_con_30_dias else round(base)
    if not aviso_con_30_dias:
        reglas.append(
            "art-161/art-162: sin aviso con 30 días de anticipación corresponde la indemnización sustitutiva "
            "del aviso previo, equivalente a la última remuneración mensual (compatible con la de años de servicio, art-163)."
        )

    salvedades += [
        "Solo aplica si la causal fue necesidades de la empresa o desahucio (art-161); las causales del art-160 no dan indemnización.",
        "Si el contrato o un convenio colectivo pactó una indemnización mayor, rige esa (art-163).",
        "La última remuneración incluye lo que se percibía mensualmente, sin horas extra ni gratificaciones esporádicas; si es variable, se promedian los últimos 3 meses (art-172).",
        "No aplica a trabajadoras/es de casa particular, que tienen indemnización a todo evento (art-163).",
    ]
    return IndemnizacionResult(years, days, round(base), ias, aviso, ias + aviso, reglas, salvedades)


@dataclass
class FeriadoResult:
    tiene_derecho: bool
    dias_habiles_base: int
    dias_progresivos: int
    total_dias_habiles: int
    anos_con_empleador_actual: int
    reglas: list[str] = field(default_factory=list)
    salvedades: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def calcular_feriado(
    fecha_ingreso: date,
    fecha_consulta: date,
    anos_con_empleadores_anteriores: int = 0,
    zona_extrema: bool = False,
) -> FeriadoResult:
    """Días hábiles de feriado anual: base (art. 67) + feriado progresivo (art. 68)."""
    if fecha_consulta < fecha_ingreso:
        raise ValueError("fecha_consulta no puede ser anterior a fecha_ingreso")
    reglas, salvedades = [], []
    years_current = _months_between(fecha_ingreso, fecha_consulta) // 12
    base = 20 if zona_extrema else 15
    reglas.append(
        "art-67: " + ("20 días hábiles en Magallanes, Aysén y Palena." if zona_extrema else "15 días hábiles con más de un año de servicio.")
    )

    if years_current < 1:
        salvedades.append(
            "Aún no cumple un año con el empleador actual: no tiene feriado completo; si el contrato termina antes, "
            "corresponde feriado proporcional (art-73)."
        )
        return FeriadoResult(False, 0, 0, 0, years_current, reglas, salvedades)

    prior = min(max(anos_con_empleadores_anteriores, 0), 10)
    if anos_con_empleadores_anteriores > 10:
        reglas.append("art-68: solo pueden hacerse valer hasta 10 años trabajados para empleadores anteriores.")
    years_to_reach_ten = max(10 - prior, 0)
    new_years = years_current - years_to_reach_ten
    progresivos = max(new_years, 0) // 3
    reglas.append("art-68: con 10 años de trabajo, un día adicional por cada 3 nuevos años trabajados.")
    salvedades += [
        "Se asume la interpretación de la Dirección del Trabajo: los 'tres nuevos años' se cuentan con el empleador actual, después de enterar los 10 años.",
        "Los años con empleadores anteriores deben acreditarse (certificados de cotizaciones).",
        "El sábado se considera inhábil para contar el feriado (art-69).",
    ]
    return FeriadoResult(True, base, progresivos, base + progresivos, years_current, reglas, salvedades)
