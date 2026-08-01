"""Расчёты, на которых держатся проектные решения Nagi.

Запуск: python3 docs/decisions/cost_and_power.py

Числа из этого скрипта приведены в docs/decisions/core-design-decisions.md.
Файл существует, чтобы допущения об издержках нельзя было поменять молча:
при изменении тарифа, размера портфеля или спреда пересчитайте и обновите
документ. Позже это должно стать тестом.
"""

import math

# --- Параметры, зафиксированные владельцем 2026-08-01 ----------------------
PORTFOLIO = 500_000          # расчётный размер портфеля, ₽
POSITION_PCT = 0.05          # типовой размер позиции, доля портфеля

# Издержки на одну сторону сделки = комиссия + полспреда + проскальзывание.
# Комиссии требуют перепроверки на уровне L0: источники расходятся.
COST_PER_SIDE = {
    "Инвестор 0.30%": 0.0030 + 0.0015 + 0.0005,
    "Трейдер 0.05%": 0.0005 + 0.0015 + 0.0005,
    "Крупный портфель 0.04%": 0.0004 + 0.0008 + 0.0003,
}

NDFL = 0.13                  # ставка НДФЛ на инвестдоход, требует перепроверки
LDV_YEARS = 3                # срок владения для льготы долгосрочного владения


def turnover_drag(annual_turnover: float, cost_per_side: float) -> float:
    """Годовая потеря доходности от оборота.

    annual_turnover — односторонний оборот за год как доля портфеля
    (1.0 означает, что за год куплено и продано на стоимость портфеля).
    """
    return annual_turnover * cost_per_side


def trades_per_month(annual_turnover: float,
                     portfolio: float = PORTFOLIO,
                     position_pct: float = POSITION_PCT) -> float:
    """Сколько сделок в месяц соответствует заданному бюджету оборота."""
    trade_size = portfolio * position_pct
    return annual_turnover * portfolio / trade_size / 12


def years_to_significance(sharpe: float, t_crit: float = 2.0) -> float:
    """Сколько лет наблюдений нужно, чтобы отличить Шарп от нуля.

    Основано на стандартной ошибке коэффициента Шарпа (Lo, 2002) для
    месячных доходностей: SE(SR_год) = sqrt((1 + SR^2/24) / T_лет).
    Отсюда T = t^2 * (1 + SR^2/24) / SR^2.
    """
    return t_crit ** 2 * (1 + sharpe ** 2 / 24) / sharpe ** 2


def paired_difference_sharpe(delta_alpha: float,
                             sigma: float,
                             correlation: float) -> float:
    """Шарп ряда разницы доходностей двух стратегий.

    Если две стратегии живут на одних ценах и денежных потоках, сравнивать
    надо ряд разницы: sigma_d = sigma * sqrt(2 * (1 - rho)).
    Чем сильнее стратегии различаются, тем ХУЖЕ разрешающая способность.
    """
    sigma_diff = sigma * math.sqrt(2 * (1 - correlation))
    return delta_alpha / sigma_diff


def effective_commission(trade_size: float,
                         rate: float = 0.003,
                         minimum: float = 0.0) -> float:
    """Эффективная ставка комиссии с учётом фиксированного минимума.

    При портфеле 500 тыс ₽ размер сделки мал, и минимум, если он есть,
    бьёт сильнее процентной ставки. Наличие минимума — гейт уровня L0.
    """
    return max(trade_size * rate, minimum) / trade_size


def early_sale_tax_cost(position_value: float, gain_pct: float) -> float:
    """Скрытая цена продажи до истечения срока ЛДВ.

    Продажа раньше LDV_YEARS лет означает уплату НДФЛ с прибыли, которого
    при удержании не было бы. По выросшей позиции это на порядок больше
    брокерской комиссии.
    """
    return position_value * gain_pct * NDFL


def ldv_limit(years_held: int) -> float:
    """Лимит освобождаемой прибыли по ЛДВ: 3 млн ₽ за каждый полный год.

    Требует перепроверки актуальности на уровне L0.
    """
    return 3_000_000 * years_held


def _report() -> None:
    line = "-" * 74

    print("Бюджет оборота -> число сделок в месяц")
    print(f"{'оборот/год':>11} | {'сделок/мес':>11} | " +
          " | ".join(f"{n:>10}" for n in COST_PER_SIDE))
    print(line)
    for turnover in (0.5, 1.0, 2.0, 4.0, 6.0):
        drags = " | ".join(
            f"{turnover_drag(turnover, c) * 100:>9.2f}%"
            for c in COST_PER_SIDE.values()
        )
        print(f"{turnover * 100:>9.0f}% | {trades_per_month(turnover):>11.1f} | {drags}")

    print("\nЛет наблюдений до статистической значимости")
    print(f"{'Шарп':>6} | {'t=2 (95%)':>12} | {'t=3 (перебор)':>15}")
    print(line)
    for sharpe in (0.3, 0.5, 0.75, 1.0):
        print(f"{sharpe:>6.2f} | {years_to_significance(sharpe, 2):>9.1f} лет"
              f" | {years_to_significance(sharpe, 3):>12.1f} лет")

    print("\nПарное сравнение: разница альфы 2 п.п., волатильность 20%")
    print(f"{'corr(A,B)':>10} | {'Шарп разницы':>14} | {'лет до t=2':>13}")
    print(line)
    for rho in (0.90, 0.95, 0.99, 0.995):
        srd = paired_difference_sharpe(0.02, 0.20, rho)
        print(f"{rho:>10.3f} | {srd:>14.3f} | {years_to_significance(srd):>10.1f} лет")

    print("\nЭффект минимальной комиссии")
    print(f"{'размер сделки':>14} | {'без минимума':>13} | {'минимум 50₽':>13}"
          f" | {'минимум 100₽':>14}")
    print(line)
    for size in (5_000, 10_000, 25_000, 50_000):
        print(f"{size:>11,} ₽ | {effective_commission(size) * 100:>12.2f}%"
              f" | {effective_commission(size, minimum=50) * 100:>12.2f}%"
              f" | {effective_commission(size, minimum=100) * 100:>13.2f}%")

    print(f"\nЦена продажи до {LDV_YEARS} лет владения, позиция"
          f" {PORTFOLIO * POSITION_PCT:,.0f} ₽")
    print(f"{'прибыль':>9} | {'налог':>11} | {'% от позиции':>14}")
    print(line)
    position = PORTFOLIO * POSITION_PCT
    for gain in (0.10, 0.25, 0.50, 1.00):
        tax = early_sale_tax_cost(position, gain)
        print(f"{gain * 100:>8.0f}% | {tax:>9,.0f} ₽ | {tax / position * 100:>13.1f}%")

    print(f"\nЛимит ЛДВ за {LDV_YEARS} года: {ldv_limit(LDV_YEARS):,.0f} ₽ прибыли."
          f" Портфель {PORTFOLIO:,} ₽ — лимит не связывает.")


if __name__ == "__main__":
    _report()
