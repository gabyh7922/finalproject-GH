from datetime import date

import pytest

from app.agent.calculators import calcular_feriado, calcular_indemnizacion


def test_indemnizacion_six_years_with_notice():
    r = calcular_indemnizacion(1_000_000, date(2019, 3, 1), date(2025, 3, 1), aviso_con_30_dias=True)
    assert (r.anos_servicio_computables, r.dias_indemnizacion) == (6, 180)
    assert r.indemnizacion_anos_servicio == 6_000_000
    assert r.indemnizacion_sustitutiva_aviso == 0


def test_fraction_over_six_months_counts_as_a_year_but_exactly_six_does_not():
    over = calcular_indemnizacion(900_000, date(2020, 1, 1), date(2023, 7, 15), True)
    exact = calcular_indemnizacion(900_000, date(2020, 1, 1), date(2023, 7, 1), True)
    assert over.anos_servicio_computables == 4
    assert exact.anos_servicio_computables == 3


def test_less_than_a_year_has_no_severance_but_keeps_notice_pay():
    r = calcular_indemnizacion(800_000, date(2025, 1, 1), date(2025, 10, 1), aviso_con_30_dias=False)
    assert r.indemnizacion_anos_servicio == 0
    assert r.indemnizacion_sustitutiva_aviso == 800_000


def test_caps_330_days_and_90_uf():
    r = calcular_indemnizacion(5_000_000, date(2005, 1, 1), date(2025, 1, 1), True, valor_uf=39_000)
    assert r.dias_indemnizacion == 330
    assert r.base_calculo_mensual == 90 * 39_000
    assert r.indemnizacion_anos_servicio == 11 * 90 * 39_000


def test_invalid_dates_raise():
    with pytest.raises(ValueError):
        calcular_indemnizacion(1, date(2025, 1, 1), date(2024, 1, 1), True)


def test_feriado_base_and_first_year():
    assert calcular_feriado(date(2023, 1, 10), date(2025, 1, 10)).total_dias_habiles == 15
    assert calcular_feriado(date(2023, 1, 10), date(2025, 1, 10), zona_extrema=True).total_dias_habiles == 20
    first_year = calcular_feriado(date(2025, 3, 1), date(2025, 10, 1))
    assert not first_year.tiene_derecho and first_year.total_dias_habiles == 0


def test_feriado_progresivo():
    # 13 años con el mismo empleador: 10 + 3 nuevos -> 1 día adicional
    assert calcular_feriado(date(2012, 1, 1), date(2025, 1, 1)).dias_progresivos == 1
    # 10 años anteriores acreditados + 6 con el actual -> 2 días
    assert calcular_feriado(date(2019, 1, 1), date(2025, 1, 1), anos_con_empleadores_anteriores=10).dias_progresivos == 2
    # solo se pueden hacer valer 10 años anteriores
    assert calcular_feriado(date(2022, 1, 1), date(2025, 1, 1), anos_con_empleadores_anteriores=25).dias_progresivos == 1
