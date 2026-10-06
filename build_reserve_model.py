#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор Excel-модели «Операционный резерв ПВЗ Ozon (Орск), 15.10–25.12.2026».

Все ключевые числа пересчитываются формулами; входные данные (жёлтые ячейки)
можно менять — модель пересчитается. Скрипт также выводит контрольную сверку
с предварительными расчётами владельца.
"""
import math
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------- styles ----
MONEY = '# ##0.00" ₽"'
MONEY0 = '# ##0" ₽"'
PCT1 = '0.0%'
PCT2 = '0.00%'
DATEF = 'DD.MM.YYYY'
NUM0 = '0'
NUM1 = '0.0'

C_DARK = '1F4E78'      # section header
C_HEAD = 'D9E1F2'      # table header
C_INPUT = 'FFF2CC'     # editable input
C_TOTAL = 'F2F2F2'     # totals
C_NOTE = '808080'

THIN = Side(style='thin', color='BFBFBF')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

F_TITLE = Font(name='Calibri', size=14, bold=True, color=C_DARK)
F_SUB = Font(name='Calibri', size=10, italic=True, color=C_NOTE)
F_SEC = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
F_HEAD = Font(name='Calibri', size=10, bold=True)
F_BODY = Font(name='Calibri', size=10)
F_BOLD = Font(name='Calibri', size=10, bold=True)
F_NOTE = Font(name='Calibri', size=9, italic=True, color=C_NOTE)

WRAP = Alignment(vertical='top', wrap_text=True)
LEFT = Alignment(horizontal='left', vertical='center')
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
RIGHT = Alignment(horizontal='right', vertical='center')


def sec(ws, row, text, last_col):
    """Серая синяя полоса-заголовок раздела."""
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    c = ws.cell(row=row, column=1, value=text)
    c.font = F_SEC
    c.fill = PatternFill('solid', fgColor=C_DARK)
    c.alignment = Alignment(vertical='center')
    ws.row_dimensions[row].height = 20


def thead(ws, row, cols):
    """Шапка таблицы: cols = [(col_idx, text), ...]."""
    for ci, t in cols:
        c = ws.cell(row=row, column=ci, value=t)
        c.font = F_HEAD
        c.fill = PatternFill('solid', fgColor=C_HEAD)
        c.alignment = CENTER
        c.border = BORDER
    ws.row_dimensions[row].height = 30


def cell(ws, row, col, value, fmt=None, inp=False, bold=False, note=False,
         align=None, border=True):
    c = ws.cell(row=row, column=col, value=value)
    if note:
        c.font = F_NOTE
    elif bold:
        c.font = F_BOLD
    else:
        c.font = F_BODY
    if fmt:
        c.number_format = fmt
    if inp:
        c.fill = PatternFill('solid', fgColor=C_INPUT)
    if bold:
        c.fill = PatternFill('solid', fgColor=C_TOTAL)
    if align == 'c':
        c.alignment = CENTER
    elif align == 'r':
        c.alignment = RIGHT
    else:
        c.alignment = Alignment(vertical='center', wrap_text=True)
    if border:
        c.border = BORDER
    return c


def note_row(ws, row, text, last_col, chars_per_line=130):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    c = ws.cell(row=row, column=1, value=text)
    c.font = F_NOTE
    c.alignment = WRAP
    lines = max(1, math.ceil(len(text) / chars_per_line))
    ws.row_dimensions[row].height = 13 * lines + 4


def widths(ws, spec):
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


# ================================================================ workbook ===
wb = Workbook()
wb.remove(wb.active)

ws_itog = wb.create_sheet('Итог')
ws_inc = wb.create_sheet('Доходы Ozon')
ws_exp = wb.create_sheet('Расходы бизнеса')
ws_loan = wb.create_sheet('Кредит')
ws_per = wb.create_sheet('Личные финансы')
ws_asm = wb.create_sheet('Допущения и вопросы')

ws_itog.sheet_properties.tabColor = '70AD47'
ws_inc.sheet_properties.tabColor = '4472C4'
ws_exp.sheet_properties.tabColor = '4472C4'
ws_loan.sheet_properties.tabColor = 'ED7D31'
ws_per.sheet_properties.tabColor = '7030A0'
ws_asm.sheet_properties.tabColor = '808080'

RB = "'Расходы бизнеса'"
DO = "'Доходы Ozon'"
KR = "'Кредит'"
LF = "'Личные финансы'"

# ------------------------------------------------------- Доходы Ozon sheet ---
INC_COLS = 6
widths(ws_inc, {'A': 16, 'B': 22, 'C': 18, 'D': 18, 'E': 22, 'F': 12})

ws_inc.merge_cells('A1:F1')
ws_inc['A1'] = 'ВОЗНАГРАЖДЕНИЕ OZON ПО СКРИНШОТАМ ВЛАДЕЛЬЦА, 2026'
ws_inc['A1'].font = F_TITLE
note_row(ws_inc, 2, 'Это начисления в кабинете Ozon, а НЕ подтверждённая чистая прибыль и НЕ банковское '
                    'поступление. Drop-off и «Выдача» уже входят в «Всего» — в модели они не прибавляются '
                    'повторно. «Прочие категории» рассчитаны как разница и подлежат сверке с актами Ozon.',
         INC_COLS)

thead(ws_inc, 4, [(1, 'Месяц'), (2, 'Всего вознаграждение, ₽'), (3, 'Drop-off, ₽'),
                  (4, 'Выдача, ₽'), (5, 'Прочие категории (разница), ₽'), (6, 'Прочие, %')])

MONTHS = [
    ('Январь', 242509.97, 132317.50, 92010.07),
    ('Февраль', 225370.47, 117155.00, 92568.25),
    ('Март', 261274.78, 127570.00, 115251.88),
    ('Апрель', 270698.40, 145642.50, 101878.14),
    ('Май', 318913.63, 181365.00, 110366.03),
    ('Июнь', 251632.32, 114337.50, 106197.69),
    ('Июль', 222467.62, 66895.00, 122142.11),
    ('Август', 213911.06, 59477.50, 126040.26),
    ('Сентябрь', 288142.49, 107135.00, 147097.38),
]
R0 = 5
for i, (m, tot, drop, issue) in enumerate(MONTHS):
    r = R0 + i
    cell(ws_inc, r, 1, m, bold=True)
    cell(ws_inc, r, 2, tot, MONEY, inp=True, align='r')
    cell(ws_inc, r, 3, drop, MONEY, inp=True, align='r')
    cell(ws_inc, r, 4, issue, MONEY, inp=True, align='r')
    cell(ws_inc, r, 5, f'=B{r}-C{r}-D{r}', MONEY, align='r')
    cell(ws_inc, r, 6, f'=IF(B{r}=0,0,E{r}/B{r})', PCT1, align='r')

R_TOT, R_AVG9, R_Q3, R_DQ3 = 14, 15, 16, 17
cell(ws_inc, R_TOT, 1, 'Итого январь–сентябрь', bold=True)
for col in 'BCDE':
    cell(ws_inc, R_TOT, ord(col) - 64, f'=SUM({col}{R0}:{col}{R0 + 8})', MONEY, bold=True, align='r')
cell(ws_inc, R_TOT, 6, f'=E{R_TOT}/B{R_TOT}', PCT1, bold=True, align='r')

cell(ws_inc, R_AVG9, 1, 'Среднее янв–сен, ₽/мес', bold=True)
cell(ws_inc, R_AVG9, 2, f'=B{R_TOT}/9', MONEY, bold=True, align='r')

cell(ws_inc, R_Q3, 1, 'Среднее июль–сентябрь (Q3), ₽/мес', bold=True)
cell(ws_inc, R_Q3, 2, f'=AVERAGE(B{R0 + 6}:B{R0 + 8})', MONEY, bold=True, align='r')
note_row(ws_inc, R_Q3, '', INC_COLS) if False else None

cell(ws_inc, R_DQ3, 1, 'Drop-off Q3, среднее, ₽/мес', bold=True)
cell(ws_inc, R_DQ3, 2, f'=AVERAGE(C{R0 + 6}:C{R0 + 8})', MONEY, bold=True, align='r')

note_row(ws_inc, 18, 'Данные владельца: за август около 5 700 выдач, за сентябрь около 5 800 выдач. '
                     'Точное соответствие «выдач» и ставок — сверить с актами Ozon.', INC_COLS)

sec(ws_inc, 20, 'ПРОВЕРКА МОДЕЛЬНОГО ПОТОКА СЕЛЛЕРОВ', INC_COLS)
cell(ws_inc, 21, 1, 'Модель владельца: 250 товаров × 10 ₽ × 30 дней')
cell(ws_inc, 21, 2, '=250*10*30', MONEY, align='r')
cell(ws_inc, 22, 1, 'Фактический Drop-off Q3 (среднее по скриншотам)')
cell(ws_inc, 22, 2, f'=B{R_DQ3}', MONEY, align='r')
cell(ws_inc, 23, 1, 'Cashback селлерам (1 000 ₽/день, выплата еженедельная)')
cell(ws_inc, 23, 2, 30000, MONEY, inp=True, align='r')
cell(ws_inc, 24, 1, 'Модельный поток до налогов и прочих расходов', bold=True)
cell(ws_inc, 24, 2, '=B21-B23', MONEY, bold=True, align='r')
note_row(ws_inc, 25, '75 000 ₽/мес — это проверка Drop-off, а НЕ дополнительный доход сверх общего '
                     'вознаграждения Ozon. Фактический Drop-off Q3 (~77 836 ₽/мес) близок к модели, но '
                     'объёмы и тарифы нужно сверить. Cashback — один расход; не добавлять вторую такую же '
                     'статью как «логистика/доставка».', INC_COLS)

sec(ws_inc, 27, 'БАЗА ДЛЯ НАЛОГОВОЙ ОЦЕНКИ (предварительная, не подтверждённая)', INC_COLS)
R_BASE_Q3, R_BASE_AVG9 = 28, 29
cell(ws_inc, R_BASE_Q3, 1, 'Q3-среднее — используется в модели', bold=True)
cell(ws_inc, R_BASE_Q3, 2, f'=B{R_Q3}', MONEY, bold=True, align='r')
cell(ws_inc, R_BASE_AVG9, 1, 'Альтернатива — среднее янв–сен')
cell(ws_inc, R_BASE_AVG9, 2, f'=B{R_AVG9}', MONEY, align='r')
note_row(ws_inc, 30, 'Налоговая база определяется фактическими начислениями за период работы с 15.10.2026 и '
                     'правом на вычеты; в модели — модельная оценка на Q3-среднем.', INC_COLS)

sec(ws_inc, 32, 'ВЫПЛАТЫ OZON В ПЕРИОДЕ РЕЗЕРВА', INC_COLS)
R_PART, R_FULL, R_ROUGH = 33, 34, 35
cell(ws_inc, R_PART, 1, 'Частичная выплата за 15–31.10 — ожидается 25.11.2026')
cell(ws_inc, R_PART, 2, 0, MONEY, align='r')
cell(ws_inc, R_PART, 3, 'Сумма неизвестна — в резерв не заложена', note=True)
cell(ws_inc, R_FULL, 1, 'Полная выплата за ноябрь — 25.12.2026')
cell(ws_inc, R_FULL, 2, 0, MONEY, align='r')
cell(ws_inc, R_FULL, 3, 'Первая полная выплата после передачи; день окончания резерва', note=True)
cell(ws_inc, R_ROUGH, 1, 'Грубая оценка октябрьской части (17/30 от Q3-среднего)')
cell(ws_inc, R_ROUGH, 2, f'=B{R_Q3}*17/30', MONEY, align='r')
cell(ws_inc, R_ROUGH, 3, 'Только ориентир: не гарантия и не чистый доход', note=True)
ws_inc.freeze_panes = 'A5'

# ---------------------------------------------------- Расходы бизнеса sheet ---
EXP_COLS = 6
widths(ws_exp, {'A': 54, 'B': 18, 'C': 18, 'D': 18, 'E': 18, 'F': 62})

ws_exp.merge_cells('A1:F1')
ws_exp['A1'] = 'РАСХОДЫ БИЗНЕСА, ПЕРСОНАЛ, НАЛОГИ — 15.10–25.12.2026 (72 ДНЯ)'
ws_exp['A1'].font = F_TITLE
note_row(ws_exp, 2, 'Жёлтые ячейки — входные данные. Пропорция 72/30 = 2,4 условных месяца; денежные '
                    'средства Ozon до 25.12.2026 считаются недоступными (октябрьская частичная выплата '
                    '25.11 неизвестна и не вычитается).', EXP_COLS)

sec(ws_exp, 4, 'ПАРАМЕТРЫ ПЕРИОДА', EXP_COLS)
P_START, P_END, P_DAYS, P_MONTHS, P_BUF, P_CB, P_TOGGLE, P_ALT = 5, 6, 7, 8, 9, 10, 11, 12
cell(ws_exp, P_START, 1, 'Дата начала расходов «на себя»')
cell(ws_exp, P_START, 2, date(2026, 10, 15), DATEF, inp=True, align='c')
cell(ws_exp, P_END, 1, 'Дата первой полной выплаты Ozon')
cell(ws_exp, P_END, 2, date(2026, 12, 25), DATEF, inp=True, align='c')
cell(ws_exp, P_DAYS, 1, 'Календарных дней в периоде', bold=True)
cell(ws_exp, P_DAYS, 2, '=B6-B5+1', NUM0, bold=True, align='c')
cell(ws_exp, P_MONTHS, 1, 'Условных месяцев (дней / 30)')
cell(ws_exp, P_MONTHS, 2, '=B7/30', NUM1, align='c')
cell(ws_exp, P_BUF, 1, 'Дополнительный буфер (добавить один раз), ₽')
cell(ws_exp, P_BUF, 2, 50000, MONEY0, inp=True, align='r')
cell(ws_exp, P_CB, 1, 'Cashback селлерам, ₽/день')
cell(ws_exp, P_CB, 2, 1000, MONEY0, inp=True, align='r')
cell(ws_exp, P_TOGGLE, 1, 'Уменьшать УСН на взносы за сотрудников (1 = да, 0 = нет)')
cell(ws_exp, P_TOGGLE, 2, 1, NUM0, inp=True, align='c')
cell(ws_exp, P_TOGGLE, 6, 'Уточнить право у бухгалтера: собственных взносов не хватает для лимита 50%', note=True)
cell(ws_exp, P_ALT, 1, 'Альт. ориентир взносов, ₽/мес на сотрудника (для проверки)')
cell(ws_exp, P_ALT, 2, 8100, MONEY0, inp=True, align='r')
cell(ws_exp, P_ALT, 6, 'Ранее встречавшийся ориентир 8 100 ₽ на сотрудника — см. проверку ниже', note=True)

sec(ws_exp, 14, '1. РЕГУЛЯРНЫЕ РАСХОДЫ (без персонала)', EXP_COLS)
thead(ws_exp, 15, [(1, 'Статья'), (2, '₽/мес (30 дн)'), (3, '₽ за 72 дня'), (6, 'Примечание')])
R_RENT, R_ELEC, R_CB, R_NET, R_CAM, R_OTH, R_REGT = 16, 17, 18, 19, 20, 21, 22
cell(ws_exp, R_RENT, 1, 'Аренда помещения ПВЗ')
cell(ws_exp, R_RENT, 2, 42000, MONEY, inp=True, align='r')
cell(ws_exp, R_RENT, 3, f'=B{R_RENT}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, R_RENT, 6, 'Даты платежей аренды уточнить: может требоваться полный месяц', note=True)
cell(ws_exp, R_ELEC, 1, 'Электричество')
cell(ws_exp, R_ELEC, 2, 3000, MONEY, inp=True, align='r')
cell(ws_exp, R_ELEC, 3, f'=B{R_ELEC}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, R_ELEC, 6, '«До 3 000 ₽» — в расчёте 3 000 ₽', note=True)
cell(ws_exp, R_CB, 1, 'Cashback селлерам')
cell(ws_exp, R_CB, 2, f'=$B${P_CB}*30', MONEY, align='r')
cell(ws_exp, R_CB, 3, f'=$B${P_CB}*$B${P_DAYS}', MONEY, align='r')
cell(ws_exp, R_CB, 6, '1 000 ₽/день, выплата еженедельная; за 72 дня — 72 000 ₽. Один расход, не дублировать', note=True)
cell(ws_exp, R_NET, 1, 'Интернет')
cell(ws_exp, R_NET, 2, 1800, MONEY, inp=True, align='r')
cell(ws_exp, R_NET, 3, f'=B{R_NET}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, R_CAM, 1, 'Камеры')
cell(ws_exp, R_CAM, 2, 2100, MONEY, inp=True, align='r')
cell(ws_exp, R_CAM, 3, f'=B{R_CAM}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, R_OTH, 1, 'Прочие траты (ремонт, расходники, бухгалтерия и т. п.)')
cell(ws_exp, R_OTH, 2, 0, MONEY, inp=True, align='r')
cell(ws_exp, R_OTH, 3, f'=B{R_OTH}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, R_OTH, 6, 'Владельцем не подтверждены — редактируемая строка, по умолчанию 0', note=True)
cell(ws_exp, R_REGT, 1, 'Итого регулярные расходы', bold=True)
cell(ws_exp, R_REGT, 2, f'=SUM(B{R_RENT}:B{R_OTH})', MONEY, bold=True, align='r')
cell(ws_exp, R_REGT, 3, f'=SUM(C{R_RENT}:C{R_OTH})', MONEY, bold=True, align='r')

sec(ws_exp, 24, '2. ПЕРСОНАЛ (2 сотрудника, оформлены официально)', EXP_COLS)
thead(ws_exp, 25, [(1, 'Статья'), (2, '₽/мес'), (3, '₽ за 72 дня'), (6, 'Примечание')])
P_N, P_NET1, P_NETT, P_GROSS, P_NDFL, P_CONTRIB, P_TRAUMA, P_FOTT, P_AUSN = 26, 27, 28, 29, 30, 31, 32, 33, 34
cell(ws_exp, P_N, 1, 'Сотрудников, чел.')
cell(ws_exp, P_N, 2, 2, NUM0, inp=True, align='c')
cell(ws_exp, P_NET1, 1, 'Зарплата на руки на человека, ₽/мес')
cell(ws_exp, P_NET1, 2, 27000, MONEY, inp=True, align='r')
cell(ws_exp, P_NET1, 6, '2 000 ₽ за смену уже включены в 27 000 ₽ — отдельно не прибавляем', note=True)
cell(ws_exp, P_NETT, 1, 'ФОТ на руки всего')
cell(ws_exp, P_NETT, 2, f'=B{P_N}*B{P_NET1}', MONEY, align='r')
cell(ws_exp, P_GROSS, 1, 'Gross ФОТ (с НДФЛ 13%)')
cell(ws_exp, P_GROSS, 2, f'=B{P_NETT}/(1-0.13)', MONEY, align='r')
cell(ws_exp, P_NDFL, 1, 'НДФЛ 13% (удерживается из gross)')
cell(ws_exp, P_NDFL, 2, f'=B{P_GROSS}-B{P_NETT}', MONEY, align='r')
cell(ws_exp, P_NDFL, 6, 'Уже внутри gross — не добавляем к расходам второй раз', note=True)
cell(ws_exp, P_CONTRIB, 1, 'Страховые взносы работодателя 30%')
cell(ws_exp, P_CONTRIB, 2, f'=B{P_GROSS}*0.3', MONEY, align='r')
cell(ws_exp, P_CONTRIB, 6, 'Ставку подтвердить у бухгалтера; на АУСН тариф 0% (см. ниже)', note=True)
cell(ws_exp, P_TRAUMA, 1, 'Травматизм сотрудников (300 ₽/чел.)')
cell(ws_exp, P_TRAUMA, 2, f'=B{P_N}*300', MONEY, align='r')
cell(ws_exp, P_TRAUMA, 6, 'Ориентир — подтвердить класс профриска; на АУСН — фиксированный ВНиМ ниже', note=True)
cell(ws_exp, P_FOTT, 1, 'Итого полная стоимость ФОТ (УСН)', bold=True)
cell(ws_exp, P_FOTT, 2, f'=B{P_GROSS}+B{P_CONTRIB}+B{P_TRAUMA}', MONEY, bold=True, align='r')
cell(ws_exp, P_FOTT, 3, f'=B{P_FOTT}*$B${P_MONTHS}', MONEY, bold=True, align='r')
cell(ws_exp, P_AUSN, 1, 'Персонал на АУСН (только gross)')
cell(ws_exp, P_AUSN, 2, f'=B{P_GROSS}', MONEY, align='r')
cell(ws_exp, P_AUSN, 3, f'=B{P_AUSN}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, P_AUSN, 6, 'На АУСН страховые взносы за сотрудников 0% (ч. 1 ст. 18 ФЗ № 17-ФЗ)', note=True)
note_row(ws_exp, 35, 'Незарегистрированных сотрудников в модели нет: оба сотрудника оформлены официально, '
                     'НДФЛ удерживается из gross.', EXP_COLS)

sec(ws_exp, 36, '3. НАЛОГИ И ВЗНОСЫ — СРАВНЕНИЕ РЕЖИМОВ', EXP_COLS)
thead(ws_exp, 37, [(1, 'Статья'), (2, 'УСН 6%'), (3, 'АУСН 8%'), (6, 'Примечание')])
T_BASE, T_RATE, T_TAX0, T_FIX, T_ONE, T_EMP, T_CAP, T_RED, T_TAX, T_VNIM, T_TOT = 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48
cell(ws_exp, T_BASE, 1, 'Налоговая база (модель), ₽/мес')
cell(ws_exp, T_BASE, 2, f'={DO}!B{R_BASE_Q3}', MONEY, align='r')
cell(ws_exp, T_BASE, 3, f'={DO}!B{R_BASE_Q3}', MONEY, align='r')
cell(ws_exp, T_BASE, 6, 'Q3-среднее вознаграждения; предварительная оценка, не подтверждённая база', note=True)
cell(ws_exp, T_RATE, 1, 'Ставка налога')
cell(ws_exp, T_RATE, 2, 0.06, PCT1, inp=True, align='c')
cell(ws_exp, T_RATE, 3, 0.08, PCT1, inp=True, align='c')
cell(ws_exp, T_TAX0, 1, 'Налог до уменьшения')
cell(ws_exp, T_TAX0, 2, f'=B{T_BASE}*B{T_RATE}', MONEY, align='r')
cell(ws_exp, T_TAX0, 3, f'=C{T_BASE}*C{T_RATE}', MONEY, align='r')
cell(ws_exp, T_FIX, 1, 'Собственные взносы ИП — фиксированные (57 390 ₽/год)')
cell(ws_exp, T_FIX, 2, 4782.50, MONEY, inp=True, align='r')
cell(ws_exp, T_FIX, 3, 0, MONEY, align='r')
cell(ws_exp, T_FIX, 6, 'На АУСН ИП освобождён от фиксированных взносов «за себя»', note=True)
cell(ws_exp, T_ONE, 1, 'Собственные взносы ИП — 1% свыше 300 000 ₽/год')
cell(ws_exp, T_ONE, 2, 2165.07, MONEY, inp=True, align='r')
cell(ws_exp, T_ONE, 3, 0, MONEY, align='r')
cell(ws_exp, T_ONE,  6, '(2 898 085 − 300 000) × 1% / 12; на АУСН 1% не платится', note=True)
cell(ws_exp, T_EMP, 1, 'Взносы за сотрудников (30% + травматизм)')
cell(ws_exp, T_EMP, 2, f'=B{P_CONTRIB}+B{P_TRAUMA}', MONEY, align='r')
cell(ws_exp, T_EMP, 3, 0, MONEY, align='r')
cell(ws_exp, T_EMP, 6, 'На АУСН тариф 0% (ч. 1 ст. 18 ФЗ № 17-ФЗ) — взносов за персонал нет', note=True)
cell(ws_exp, T_CAP, 1, 'Лимит уменьшения налога (50%)')
cell(ws_exp, T_CAP, 2, f'=B{T_TAX0}*0.5', MONEY, align='r')
cell(ws_exp, T_CAP, 3, f'=C{T_TAX0}*0.5', MONEY, align='r')
cell(ws_exp, T_CAP, 6, 'На АУСН уменьшения налога взносами не предусмотрено', note=True)
cell(ws_exp, T_RED, 1, 'Фактическое уменьшение налога')
cell(ws_exp, T_RED, 2, f'=MIN(B{T_FIX}+B{T_ONE}+IF($B${P_TOGGLE}=1,B{T_EMP},0),B{T_CAP})', MONEY, align='r')
cell(ws_exp, T_RED, 3, 0, MONEY, align='r')
cell(ws_exp, T_TAX, 1, 'Налог к уплате', bold=True)
cell(ws_exp, T_TAX, 2, f'=B{T_TAX0}-B{T_RED}', MONEY, bold=True, align='r')
cell(ws_exp, T_TAX, 3, f'=C{T_TAX0}-C{T_RED}', MONEY, bold=True, align='r')
cell(ws_exp, T_VNIM, 1, 'ВНиМ ИП на АУСН (фиксированный, 2 959 ₽/год)')
cell(ws_exp, T_VNIM, 2, 0, MONEY, align='r')
cell(ws_exp, T_VNIM, 3, 246.58, MONEY, inp=True, align='r')
cell(ws_exp, T_VNIM, 6, 'Платится только при наличии сотрудников; на УСН ВНиМ — в строках 31–32 выше', note=True)
cell(ws_exp, T_TOT, 1, 'Итого налоги и взносы ИП', bold=True)
cell(ws_exp, T_TOT, 2, f'=B{T_TAX}+B{T_FIX}+B{T_ONE}', MONEY, bold=True, align='r')
cell(ws_exp, T_TOT, 3, f'=C{T_TAX}+C{T_FIX}+C{T_ONE}+C{T_VNIM}', MONEY, bold=True, align='r')

sec(ws_exp, 50, '4. ИТОГО ОТТОК БИЗНЕСА', EXP_COLS)
thead(ws_exp, 51, [(1, 'Статья'), (2, 'УСН, ₽/мес'), (3, 'АУСН, ₽/мес'),
                   (4, 'УСН, ₽ за 72 дня'), (5, 'АУСН, ₽ за 72 дня'), (6, 'Примечание')])
S_REG, S_PERS, S_TAX, S_OWN, S_VNIM, S_TOT, S_CAUT = 52, 53, 54, 55, 56, 57, 58
cell(ws_exp, S_REG, 1, 'Регулярные расходы')
cell(ws_exp, S_REG, 2, f'=B{R_REGT}', MONEY, align='r')
cell(ws_exp, S_REG, 3, f'=B{R_REGT}', MONEY, align='r')
cell(ws_exp, S_REG, 4, f'=C{R_REGT}', MONEY, align='r')
cell(ws_exp, S_REG, 5, f'=C{R_REGT}', MONEY, align='r')
cell(ws_exp, S_PERS, 1, 'Персонал (полная стоимость)')
cell(ws_exp, S_PERS, 2, f'=B{P_FOTT}', MONEY, align='r')
cell(ws_exp, S_PERS, 3, f'=B{P_AUSN}', MONEY, align='r')
cell(ws_exp, S_PERS, 4, f'=C{P_FOTT}', MONEY, align='r')
cell(ws_exp, S_PERS, 5, f'=C{P_AUSN}', MONEY, align='r')
cell(ws_exp, S_TAX, 1, 'Налог к уплате')
cell(ws_exp, S_TAX, 2, f'=B{T_TAX}', MONEY, align='r')
cell(ws_exp, S_TAX, 3, f'=C{T_TAX}', MONEY, align='r')
cell(ws_exp, S_TAX, 4, f'=B{S_TAX}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, S_TAX, 5, f'=C{S_TAX}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, S_OWN, 1, 'Взносы ИП за себя (фиксированные + 1%)')
cell(ws_exp, S_OWN, 2, f'=B{T_FIX}+B{T_ONE}', MONEY, align='r')
cell(ws_exp, S_OWN, 3, f'=C{T_FIX}+C{T_ONE}', MONEY, align='r')
cell(ws_exp, S_OWN, 4, f'=B{S_OWN}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, S_OWN, 5, f'=C{S_OWN}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, S_VNIM, 1, 'ВНиМ ИП (фиксированный на АУСН)')
cell(ws_exp, S_VNIM, 2, f'=B{T_VNIM}', MONEY, align='r')
cell(ws_exp, S_VNIM, 3, f'=C{T_VNIM}', MONEY, align='r')
cell(ws_exp, S_VNIM, 4, f'=B{S_VNIM}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, S_VNIM, 5, f'=C{S_VNIM}*$B${P_MONTHS}', MONEY, align='r')
cell(ws_exp, S_TOT, 1, 'ИТОГО ОТТОК БИЗНЕСА', bold=True)
for col in 'BCDE':
    ci = ord(col) - 64
    cell(ws_exp, S_TOT, ci, f'=SUM({col}{S_REG}:{col}{S_VNIM})', MONEY, bold=True, align='r')
cell(ws_exp, S_CAUT, 1, 'Осторожный вариант: 3 полных месяца, cashback — за 72 факт. дня', bold=True)
cell(ws_exp, S_CAUT, 4, f'=(B{S_TOT}-$B${P_CB}*30)*3+$B${P_CB}*$B${P_DAYS}', MONEY, bold=True, align='r')
cell(ws_exp, S_CAUT, 5, f'=(C{S_TOT}-$B${P_CB}*30)*3+$B${P_CB}*$B${P_DAYS}', MONEY, bold=True, align='r')
cell(ws_exp, S_CAUT, 6, 'Если аренда, зарплаты и счета оплачиваются полными месячными суммами', note=True)
ws_exp.freeze_panes = 'A4'

sec(ws_exp, 60, '5. ПРОВЕРКА И ЧУВСТВИТЕЛЬНОСТЬ', EXP_COLS)
thead(ws_exp, 61, [(1, 'Показатель'), (2, 'Предвар. расчёт владельца'), (3, 'Эта модель'), (4, 'Δ, ₽'), (6, 'Комментарий')])
V1, V2, V3, V4, V5, V6 = 62, 63, 64, 65, 66, 67
cell(ws_exp, V1, 1, 'УСН, ₽/мес')
cell(ws_exp, V1, 2, 174382.44, MONEY, align='r')
cell(ws_exp, V1, 3, f'=B{S_TOT}', MONEY, align='r')
cell(ws_exp, V1, 4, f'=C{V1}-B{V1}', MONEY, align='r')
cell(ws_exp, V1, 6, 'Совпадает (разница — округление)', note=True)
cell(ws_exp, V2, 1, 'АУСН, ₽/мес')
cell(ws_exp, V2, 2, 160536.11, MONEY, align='r')
cell(ws_exp, V2, 3, f'=C{S_TOT}', MONEY, align='r')
cell(ws_exp, V2, 4, f'=C{V2}-B{V2}', MONEY, align='r')
cell(ws_exp, V2, 6, 'Совпадает (разница — округление)', note=True)
cell(ws_exp, V3, 1, 'УСН, ₽ за 72 дня')
cell(ws_exp, V3, 2, 418517.86, MONEY, align='r')
cell(ws_exp, V3, 3, f'=D{S_TOT}', MONEY, align='r')
cell(ws_exp, V3, 4, f'=C{V3}-B{V3}', MONEY, align='r')
cell(ws_exp, V4, 1, 'АУСН, ₽ за 72 дня')
cell(ws_exp, V4, 2, 385286.66, MONEY, align='r')
cell(ws_exp, V4, 3, f'=E{S_TOT}', MONEY, align='r')
cell(ws_exp, V4, 4, f'=C{V4}-B{V4}', MONEY, align='r')
cell(ws_exp, V5, 1, 'Резерв УСН (+ 2 платежа по кредиту + буфер 50 000)', bold=True)
cell(ws_exp, V5, 2, 536197.86, MONEY, align='r')
cell(ws_exp, V5, 3, f'=D{S_TOT}+{KR}!B19+$B${P_BUF}', MONEY, bold=True, align='r')
cell(ws_exp, V5, 4, f'=C{V5}-B{V5}', MONEY, align='r')
cell(ws_exp, V5, 6, 'Предварительный итог владельца — 536 198 ₽', note=True)
cell(ws_exp, V6, 1, 'Резерв АУСН (+ 2 платежа по кредиту + буфер 50 000)', bold=True)
cell(ws_exp, V6, 2, 502966.66, MONEY, align='r')
cell(ws_exp, V6, 3, f'=E{S_TOT}+{KR}!B19+$B${P_BUF}', MONEY, bold=True, align='r')
cell(ws_exp, V6, 4, f'=C{V6}-B{V6}', MONEY, align='r')
cell(ws_exp, V6, 6, 'Предварительный итог владельца — 502 967 ₽', note=True)

cell(ws_exp, 69, 1, 'Если в уменьшение УСН идут ТОЛЬКО собственные взносы (B11 = 0): налог / резерв')
cell(ws_exp, 69, 2, f'=B{T_TAX0}-MIN(B{T_FIX}+B{T_ONE},B{T_CAP})', MONEY, align='r')
cell(ws_exp, 69, 3, f'=(B{R_REGT}+B{P_FOTT}+(B{T_TAX0}-MIN(B{T_FIX}+B{T_ONE},B{T_CAP}))+B{T_FIX}+B{T_ONE})*$B${P_MONTHS}+{KR}!B19+$B${P_BUF}', MONEY, align='r')
cell(ws_exp, 69, 6, 'Разница с базовым случаем — около +714 ₽ за 72 дня', note=True)
cell(ws_exp, 70, 1, 'Если взносы за сотрудников = 8 100 ₽/чел. (B12): отток ₽/мес / резерв')
cell(ws_exp, 70, 2, f'=B{R_REGT}+B{P_GROSS}+$B${P_ALT}*B{P_N}+(B{T_TAX0}-B{T_RED})+B{T_FIX}+B{T_ONE}', MONEY, align='r')
cell(ws_exp, 70, 3, f'=B70*$B${P_MONTHS}+{KR}!B19+$B${P_BUF}', MONEY, align='r')
cell(ws_exp, 70, 6, 'Ориентир, который встречался ранее; ставку подтвердить у бухгалтера', note=True)
note_row(ws_exp, 72, 'Модель воспроизводит предварительные расчёты владельца с точностью до округления. '
                     'АУСН дешевле УСН на сумму экономии взносов за персонал и взносов ИП «за себя» '
                     'минус более высокая ставка налога. Полный список допущений — лист «Допущения и вопросы».',
         EXP_COLS)

# --------------------------------------------------------------- Кредит sheet ---
LOAN_COLS = 4
widths(ws_loan, {'A': 52, 'B': 20, 'C': 20, 'D': 24})

ws_loan.merge_cells('A1:D1')
ws_loan['A1'] = 'КРЕДИТ НА РЕФИНАНСИРОВАНИЕ (по документам банка)'
ws_loan['A1'].font = F_TITLE
note_row(ws_loan, 2, 'В прежнем сообщении называлась сумма ~950 000 ₽; в документах банка — 923 000 ₽. '
                     'Ниже — параметры из графиков банка.', LOAN_COLS)

sec(ws_loan, 4, 'ПАРАМЕТРЫ', LOAN_COLS)
L_SUM, L_N, L_PAY, L_LAST, L_FIRST, L_RATE, L_PSK, L_OVER, L_PEN, L_RATE2 = 5, 6, 7, 8, 9, 10, 11, 12, 13, 14
cell(ws_loan, L_SUM, 1, 'Сумма кредита, ₽')
cell(ws_loan, L_SUM, 2, 923000, MONEY0, inp=True, align='r')
cell(ws_loan, L_N, 1, 'Количество платежей')
cell(ws_loan, L_N, 2, 59, NUM0, inp=True, align='c')
cell(ws_loan, L_PAY, 1, 'Регулярный платёж, ₽')
cell(ws_loan, L_PAY, 2, 33840, MONEY, inp=True, align='r')
cell(ws_loan, L_LAST, 1, 'Последний платёж, ₽')
cell(ws_loan, L_LAST, 2, 31083.47, MONEY, inp=True, align='r')
cell(ws_loan, L_FIRST, 1, 'Дата первого платежа')
cell(ws_loan, L_FIRST, 2, date(2026, 11, 4), DATEF, inp=True, align='c')
cell(ws_loan, L_FIRST, 4, 'Далее — 4-го числа ежемесячно', note=True)
cell(ws_loan, L_RATE, 1, 'Ставка по графику, % годовых')
cell(ws_loan, L_RATE, 2, 0.365, PCT1, inp=True, align='c')
cell(ws_loan, L_PSK, 1, 'ПСК, %')
cell(ws_loan, L_PSK, 2, 0.36481, PCT2, inp=True, align='c')
cell(ws_loan, L_OVER, 1, 'Реальная переплата (из графика банка), % годовых')
cell(ws_loan, L_OVER, 2, 0.2359, PCT1, inp=True, align='c')
cell(ws_loan, L_PEN, 1, 'Штраф за просрочку, % в день')
cell(ws_loan, L_PEN, 2, 0.001, PCT1, inp=True, align='c')
cell(ws_loan, L_RATE2, 1, 'Ставка при невыполнении цели рефинансирования, %')
cell(ws_loan, L_RATE2, 2, 0.565, PCT1, inp=True, align='c')
cell(ws_loan, L_RATE2, 4, 'Базовый диапазон 21,9–39,9% + надбавка 20 п. п.', note=True)

sec(ws_loan, 16, 'ПЛАТЕЖИ В ПЕРИОДЕ РЕЗЕРВА 15.10–25.12.2026', LOAN_COLS)
PP1, PP2, PPT = 17, 18, 19
cell(ws_loan, PP1, 1, '04.11.2026 — платёж 1')
cell(ws_loan, PP1, 2, f'=$B${L_PAY}', MONEY, align='r')
cell(ws_loan, PP2, 1, '04.12.2026 — платёж 2')
cell(ws_loan, PP2, 2, f'=$B${L_PAY}', MONEY, align='r')
cell(ws_loan, PPT, 1, 'Итого платежей до выплаты 25.12.2026', bold=True)
cell(ws_loan, PPT, 2, f'=SUM(B{PP1}:B{PP2})', MONEY, bold=True, align='r')

sec(ws_loan, 21, 'РЕФИНАНСИРОВАНИЕ — СВОБОДНЫЕ СРЕДСТВА', LOAN_COLS)
RF1, RF2, RFF = 22, 23, 24
cell(ws_loan, RF1, 1, 'Остаток долга № 1 (из документов), ₽')
cell(ws_loan, RF1, 2, 143323.53, MONEY, inp=True, align='r')
cell(ws_loan, RF2, 1, 'Остаток долга № 2 (из документов), ₽')
cell(ws_loan, RF2, 2, 50000, MONEY, inp=True, align='r')
cell(ws_loan, RFF, 1, 'Оценка свободных средств после закрытия долгов, ₽', bold=True)
cell(ws_loan, RFF, 2, f'=B{L_SUM}-B{RF1}-B{RF2}', MONEY, bold=True, align='r')
note_row(ws_loan, 25, 'Фактические суммы закрытия долгов и реально свободные деньги (с учётом возможных '
                      'комиссий, страхования, порядка зачисления) необходимо подтвердить в банке. Не считать '
                      'автоматически все 923 000 ₽ свободными на покупку ПВЗ.', LOAN_COLS)
note_row(ws_loan, 26, 'Старый автокредит 16 500 ₽/мес, возможно, является одним из рефинансируемых долгов — '
                      'не учитывать старый и новый платёж одновременно без подтверждения состава '
                      'рефинансирования.', LOAN_COLS)

sec(ws_loan, 28, 'ГРАФИК ПЛАТЕЖЕЙ (59 платежей)', LOAN_COLS)
thead(ws_loan, 29, [(1, '№'), (2, 'Дата'), (3, 'Платёж, ₽'), (4, 'В периоде резерва?')])
SCH0 = 30
first_date = date(2026, 11, 4)
for i in range(59):
    r = SCH0 + i
    y = first_date.year + (first_date.month - 1 + i) // 12
    m = (first_date.month - 1 + i) % 12 + 1
    d = date(y, m, 4)
    amt = 31083.47 if i == 58 else 33840
    cell(ws_loan, r, 1, i + 1, NUM0, align='c')
    cell(ws_loan, r, 2, d, DATEF, align='c')
    cell(ws_loan, r, 3, amt, MONEY, align='r')
    cell(ws_loan, r, 4, 'да' if d <= date(2026, 12, 25) else 'нет', align='c')
SCH_TOT, SCH_INT = SCH0 + 59, SCH0 + 60
cell(ws_loan, SCH_TOT, 1, 'Всего выплат по графику, ₽', bold=True)
cell(ws_loan, SCH_TOT, 3, f'=SUM(C{SCH0}:C{SCH0 + 58})', MONEY, bold=True, align='r')
cell(ws_loan, SCH_INT, 1, 'В т. ч. проценты, ₽', bold=True)
cell(ws_loan, SCH_INT, 3, f'=C{SCH_TOT}-B{L_SUM}', MONEY, bold=True, align='r')
note_row(ws_loan, SCH_INT + 2, 'Даты платежей проставлены по графику банка (4-е число). Платёж 04.01.2027 '
                               'уже выходит за период резерва и в операционный резерв до 25.12.2026 не '
                               'включён.', LOAN_COLS)
ws_loan.freeze_panes = 'A4'

# ------------------------------------------------------ Личные финансы sheet ---
PER_COLS = 4
widths(ws_per, {'A': 52, 'B': 18, 'C': 20, 'D': 56})

ws_per.merge_cells('A1:D1')
ws_per['A1'] = 'ЛИЧНЫЕ ПЛАТЕЖИ (ОТДЕЛЬНО ОТ БИЗНЕСА) — 15.10–25.12.2026'
ws_per['A1'].font = F_TITLE
note_row(ws_per, 2, 'Личный блок показан отдельно: средства бизнес-резерва на личные расходы не '
                    'планируются. Основную работу на заводе сохраняем.', PER_COLS)

sec(ws_per, 4, 'ЛИЧНЫЕ РАСХОДЫ', PER_COLS)
thead(ws_per, 5, [(1, 'Статья'), (2, '₽/мес'), (3, '₽ за 72 дня'), (4, 'Примечание')])
L_RENT, L_CAR, L_TOT = 6, 7, 8
cell(ws_per, L_RENT, 1, 'Аренда квартиры')
cell(ws_per, L_RENT, 2, 20000, MONEY, inp=True, align='r')
cell(ws_per, L_RENT, 3, f'=B{L_RENT}*{RB}!$B${P_MONTHS}', MONEY, align='r')
cell(ws_per, L_CAR, 1, 'Старый автокредит')
cell(ws_per, L_CAR, 2, 16500, MONEY, inp=True, align='r')
cell(ws_per, L_CAR, 3, f'=B{L_CAR}*{RB}!$B${P_MONTHS}', MONEY, align='r')
cell(ws_per, L_CAR, 4, 'Может быть рефинансирован — тогда платёж внутри нового кредита', note=True)
cell(ws_per, L_TOT, 1, 'Итого личные расходы', bold=True)
cell(ws_per, L_TOT, 2, f'=SUM(B{L_RENT}:B{L_CAR})', MONEY, bold=True, align='r')
cell(ws_per, L_TOT, 3, f'=SUM(C{L_RENT}:C{L_CAR})', MONEY, bold=True, align='r')

sec(ws_per, 10, 'ИСТОЧНИК ПОКРЫТИЯ — ЗАРПЛАТА НА ЗАВОДЕ', PER_COLS)
S_REF, S_MIN, S_MAX, S_BAL = 11, 12, 13, 15
cell(ws_per, S_REF, 1, 'Зарплата (ориентир 120 000 ₽/мес)')
cell(ws_per, S_REF, 2, 120000, MONEY, inp=True, align='r')
cell(ws_per, S_REF, 3, f'=B{S_REF}*{RB}!$B${P_MONTHS}', MONEY, align='r')
cell(ws_per, S_MIN, 1, 'Минимум (110 000 ₽/мес)')
cell(ws_per, S_MIN, 2, 110000, MONEY, inp=True, align='r')
cell(ws_per, S_MIN, 3, f'=B{S_MIN}*{RB}!$B${P_MONTHS}', MONEY, align='r')
cell(ws_per, S_MAX, 1, 'Максимум (130 000 ₽/мес)')
cell(ws_per, S_MAX, 2, 130000, MONEY, inp=True, align='r')
cell(ws_per, S_MAX, 3, f'=B{S_MAX}*{RB}!$B${P_MONTHS}', MONEY, align='r')
cell(ws_per, S_BAL, 1, 'Сальдо личного блока (зарплата − личные расходы)', bold=True)
cell(ws_per, S_BAL, 3, f'=C{S_REF}-C{L_TOT}', MONEY, bold=True, align='r')
cell(ws_per, S_BAL, 4, 'Личные расходы покрыты зарплатой завода; при этом основную работу сохраняем', note=True)
note_row(ws_per, 17, 'Если старый автокредит будет рефинансирован в новый кредит, его платёж 16 500 ₽/мес '
                     'исчезнет из личного блока, а сумма долга войдёт в 923 000 ₽ — не учитывать дважды.',
         PER_COLS)

# -------------------------------------------------------------- Итог sheet ---
IT_COLS = 4
widths(ws_itog, {'A': 56, 'B': 20, 'C': 20, 'D': 64})
ws_itog.sheet_view.showGridLines = False

ws_itog.merge_cells('A1:D1')
ws_itog['A1'] = 'ОПЕРАЦИОННЫЙ РЕЗЕРВ ПВЗ OZON — ОРСК, 15.10–25.12.2026'
ws_itog['A1'].font = F_TITLE
note_row(ws_itog, 2, 'Период резерва: 15.10.2026 — 25.12.2026 включительно (72 календарных дня). '
                     'Консервативно: деньги Ozon до 25.12.2026 недоступны, октябрьская частичная выплата '
                     '25.11 неизвестна и не вычитается. Жёлтые ячейки — входные данные, белые — формулы.',
         IT_COLS, chars_per_line=140)

sec(ws_itog, 5, 'КЛЮЧЕВЫЕ ДАТЫ', IT_COLS)
KEY_DATES = [
    (date(2026, 10, 15), 'Оформление ПВЗ и начало расходов «на себя»'),
    (date(2026, 11, 4), 'Платёж по новому кредиту № 1 — 33 840 ₽'),
    (date(2026, 11, 25), 'Частичная выплата Ozon за октябрь — сумма НЕИЗВЕСТНА, в резерв не заложена'),
    (date(2026, 12, 4), 'Платёж по новому кредиту № 2 — 33 840 ₽'),
    (date(2026, 12, 25), 'Первая полная выплата Ozon (за ноябрь) — конец периода резерва'),
    (date(2026, 12, 31), 'Срок уплаты фиксированных взносов ИП за 2026 г. (при УСН) — дату уточнить'),
]
for i, (d, txt) in enumerate(KEY_DATES):
    r = 6 + i
    cell(ws_itog, r, 1, d, DATEF, align='c', bold=True)
    ws_itog.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
    c = ws_itog.cell(row=r, column=2, value=txt)
    c.font = F_BODY
    c.alignment = Alignment(vertical='center', wrap_text=True)
    for ci in range(2, 5):
        ws_itog.cell(row=r, column=ci).border = BORDER

sec(ws_itog, 13, '1. БИЗНЕС-РЕЗЕРВ ПВЗ (деньги бизнеса)', IT_COLS)
thead(ws_itog, 14, [(1, 'Статья'), (2, 'УСН 6%'), (3, 'АУСН 8%'), (4, 'Примечание')])
I_REG, I_LOAN, I_BUF, I_TOT, I_CAUT = 15, 16, 17, 18, 19
cell(ws_itog, I_REG, 1, 'Расходы ПВЗ за 72 дня (аренда, электричество, cashback, интернет, камеры, персонал, налоги и взносы)')
cell(ws_itog, I_REG, 2, f'={RB}!D{S_TOT}', MONEY, align='r')
cell(ws_itog, I_REG, 3, f'={RB}!E{S_TOT}', MONEY, align='r')
cell(ws_itog, I_REG, 4, 'Детализация — лист «Расходы бизнеса»', note=True)
cell(ws_itog, I_LOAN, 1, 'Платежи по новому кредиту (04.11 и 04.12 = 2 × 33 840 ₽)')
cell(ws_itog, I_LOAN, 2, f'={KR}!B{PPT}', MONEY, align='r')
cell(ws_itog, I_LOAN, 3, f'={KR}!B{PPT}', MONEY, align='r')
cell(ws_itog, I_LOAN, 4, 'Кредит 923 000 ₽, 59 платежей — лист «Кредит»', note=True)
cell(ws_itog, I_BUF, 1, 'Дополнительный буфер (добавить один раз)')
cell(ws_itog, I_BUF, 2, f'={RB}!B{P_BUF}', MONEY, align='r')
cell(ws_itog, I_BUF, 3, f'={RB}!B{P_BUF}', MONEY, align='r')
cell(ws_itog, I_TOT, 1, 'ИТОГО ОПЕРАЦИОННЫЙ РЕЗЕРВ', bold=True)
cell(ws_itog, I_TOT, 2, f'=SUM(B{I_REG}:B{I_BUF})', MONEY, bold=True, align='r')
cell(ws_itog, I_TOT, 3, f'=SUM(C{I_REG}:C{I_BUF})', MONEY, bold=True, align='r')
cell(ws_itog, I_TOT, 4, 'БЕЗ цены покупки ПВЗ и личных расходов', note=True)
cell(ws_itog, I_CAUT, 1, 'Осторожный вариант: 3 полных месяца расходов, cashback — за 72 факт. дня')
cell(ws_itog, I_CAUT, 2, f'={RB}!D{S_CAUT}+{KR}!B{PPT}+{RB}!B{P_BUF}', MONEY, align='r')
cell(ws_itog, I_CAUT, 3, f'={RB}!E{S_CAUT}+{KR}!B{PPT}+{RB}!B{P_BUF}', MONEY, align='r')
cell(ws_itog, I_CAUT, 4, 'Если аренда/зарплаты/счета оплачиваются полными месячными суммами', note=True)

sec(ws_itog, 21, '2. ПОСТУПЛЕНИЯ OZON В ПЕРИОДЕ (в резерв консервативно не заложены)', IT_COLS)
I_FULL, I_PART, I_ROUGH = 22, 23, 24
cell(ws_itog, I_FULL, 1, 'Полная выплата Ozon 25.12.2026 (за ноябрь)')
cell(ws_itog, I_FULL, 2, 0, MONEY, align='r')
cell(ws_itog, I_FULL, 3, 0, MONEY, align='r')
cell(ws_itog, I_FULL, 4, 'Первая полная выплата после передачи; день окончания резерва', note=True)
cell(ws_itog, I_PART, 1, 'Частичная выплата Ozon 25.11.2026')
cell(ws_itog, I_PART, 2, 0, MONEY, align='r')
cell(ws_itog, I_PART, 3, 0, MONEY, align='r')
cell(ws_itog, I_PART, 4, 'Сумма неизвестна — не вычитается из резерва до подтверждения', note=True)
cell(ws_itog, I_ROUGH, 1, 'Грубая оценка октябрьской части (17/30 от Q3-среднего)')
cell(ws_itog, I_ROUGH, 2, f'={DO}!B{R_ROUGH}', MONEY, align='r')
cell(ws_itog, I_ROUGH, 4, 'Только ориентир начисленного вознаграждения: не гарантия и не чистый доход', note=True)
note_row(ws_itog, 25, 'Вознаграждение Ozon по скриншотам — начисления в кабинете, а НЕ подтверждённая чистая '
                      'прибыль. Drop-off и «Выдача» уже входят в общее вознаграждение и в модели не '
                      'добавляются повторно.', IT_COLS, chars_per_line=140)

sec(ws_itog, 27, '3. ЛИЧНЫЕ ПЛАТЕЖИ (отдельно от бизнеса)', IT_COLS)
I_LRENT, I_LCAR, I_LTOT, I_SAL, I_BAL = 28, 29, 30, 31, 32
cell(ws_itog, I_LRENT, 1, 'Аренда квартиры (20 000 ₽/мес × 2,4)')
cell(ws_itog, I_LRENT, 2, f'={LF}!C{L_RENT}', MONEY, align='r')
cell(ws_itog, I_LCAR, 1, 'Старый автокредит (16 500 ₽/мес × 2,4)')
cell(ws_itog, I_LCAR, 2, f'={LF}!C{L_CAR}', MONEY, align='r')
cell(ws_itog, I_LTOT, 1, 'Итого личные расходы за 72 дня', bold=True)
cell(ws_itog, I_LTOT, 2, f'=SUM(B{I_LRENT}:B{I_LCAR})', MONEY, bold=True, align='r')
cell(ws_itog, I_SAL, 1, 'Зарплата на заводе (источник покрытия, ориентир 120 000 ₽/мес × 2,4)')
cell(ws_itog, I_SAL, 2, f'={LF}!C{S_REF}', MONEY, align='r')
cell(ws_itog, I_SAL, 4, 'Диапазон 264 000–312 000 ₽ за период (110–130 тыс./мес)', note=True)
cell(ws_itog, I_BAL, 1, 'Сальдо личного блока', bold=True)
cell(ws_itog, I_BAL, 2, f'=B{I_SAL}-B{I_LTOT}', MONEY, bold=True, align='r')
cell(ws_itog, I_BAL, 4, 'Личное — отдельно от бизнеса; основную работу сохраняем', note=True)

sec(ws_itog, 34, '4. ЦЕНА ПОКУПКИ ПВЗ (отдельно, НЕ входит в операционный резерв)', IT_COLS)
I_PR1, I_PR2, I_PR3, I_PR4 = 35, 36, 37, 38
cell(ws_itog, I_PR1, 1, 'Диапазон оценки')
cell(ws_itog, I_PR1, 2, '650 000 — 700 000 ₽', align='r')
cell(ws_itog, I_PR1, 4, 'Цена не согласована', note=True)
cell(ws_itog, I_PR2, 1, 'Расчётный ориентир')
cell(ws_itog, I_PR2, 2, 675000, MONEY0, inp=True, align='r')
cell(ws_itog, I_PR2, 4, 'Только ориентир для расчётов', note=True)
cell(ws_itog, I_PR3, 1, 'Кредит на рефинансирование (по документам)')
cell(ws_itog, I_PR3, 2, f'={KR}!B{L_SUM}', MONEY0, align='r')
cell(ws_itog, I_PR3, 4, '59 платежей по 33 840 ₽, последний 31 083,47 ₽', note=True)
cell(ws_itog, I_PR4, 1, 'Оценка свободных средств после закрытия долгов (143 323,53 + 50 000)', bold=True)
cell(ws_itog, I_PR4, 2, f'={KR}!B{RFF}', MONEY, bold=True, align='r')
cell(ws_itog, I_PR4, 4, 'Подтвердить фактические суммы закрытия в банке; не считать все 923 000 ₽ свободными автоматически', note=True)

sec(ws_itog, 40, '5. ГЛАВНЫЕ ДОПУЩЕНИЯ (полный список — лист «Допущения и вопросы»)', IT_COLS)
BULLETS = [
    '• Резерв рассчитан консервативно: поступления Ozon до 25.12.2026 не учитываются; октябрьская частичная выплата 25.11 неизвестна.',
    '• УСН 6% и АУСН 8% посчитаны на одной базе — Q3-среднем вознаграждении 241 507,06 ₽/мес (предварительная оценка, не подтверждённая налоговая база).',
    '• АУСН: тариф страховых взносов за сотрудников 0%, ИП освобождён от фиксированных взносов и 1% свыше 300 000 ₽ (ФЗ № 17-ФЗ); сохраняется фиксированный ВНиМ 2 959 ₽/год = 246,58 ₽/мес. Оренбургская область в эксперименте АУСН с 01.01.2025; режим экспериментальный (до 31.12.2027) — проверить условия: доход ≤ 60 млн ₽, сотрудников ≤ 5, уполномоченный банк, виды деятельности, запрет уходить с режима 12 месяцев.',
    '• УСН: уменьшение налога взносами ограничено 50% (7 245,20 ₽/мес); право включить в уменьшение взносы за сотрудников уточнить у бухгалтера (переключатель B11 на листе «Расходы бизнеса»).',
    '• «Прочие категории» вознаграждения (229 473,93 ₽ за 9 мес.), ставки взносов 30% и травматизма, даты фактической уплаты налогов — сверить с актами Ozon и бухгалтером.',
    '• Ориентир для планирования: около 600–650 тыс. ₽ резерва (перекрывает осторожный вариант по обоим режимам) без цены покупки ПВЗ, личных расходов и старого автокредита.',
]
for i, b in enumerate(BULLETS):
    r = 41 + i
    note_row(ws_itog, r, b, IT_COLS, chars_per_line=140)

# ------------------------------------------------- Допущения и вопросы sheet ---
widths(ws_asm, {'A': 5, 'B': 150})
ws_asm.sheet_view.showGridLines = False
ws_asm.merge_cells('A1:B1')
ws_asm['A1'] = 'ДОПУЩЕНИЯ, НЕИЗВЕСТНЫЕ СУММЫ И ВОПРОСЫ ДЛЯ ПРОВЕРКИ'
ws_asm['A1'].font = F_TITLE
note_row(ws_asm, 2, 'Модель построена на данных владельца (скриншоты вознаграждения Ozon за янв–сен 2026, '
                    'вводные по расходам, документам банка). Все суммы — ориентировочные модельные '
                    'начисления, не подтверждённые фактические платежи и не налоговая консультация.',
         2, chars_per_line=145)

ASSUMPTIONS = [
    'Вознаграждение Ozon по скриншотам — начисления в кабинете, НЕ подтверждённая чистая прибыль и НЕ банковское поступление. Drop-off и «Выдача» уже входят в «Всего» и в модели не прибавляются повторно.',
    '«Прочие категории» (229 473,93 ₽ за 9 мес.) рассчитаны как разница — сверить с актами Ozon.',
    'Налоговая база — модельная: Q3-среднее 241 507,06 ₽/мес (альтернатива — среднее янв–сен 254 991,19 ₽/мес). Фактическая база зависит от начислений за период работы с 15.10.2026.',
    'УСН 6%: уменьшение налога страховыми взносами ограничено 50% (7 245,20 ₽/мес). Собственных взносов ИП (6 947,57 ₽/мес) не хватает для полного уменьшения — в модели взносы за сотрудников включены в уменьшение (переключатель B11). Право на такое уменьшение уточнить у бухгалтера; без него налог 7 542,83 ₽/мес, резерв +714 ₽.',
    'Ставка страховых взносов 30% и травматизм 300 ₽/чел./мес — ориентиры (ранее встречался ориентир 8 100 ₽ на сотрудника). Подтвердить у бухгалтера; на листе «Расходы бизнеса» есть проверка чувствительности.',
    'АУСН 8% (по открытым источникам 2026 г.): тариф страховых взносов за сотрудников 0% (ч. 1 ст. 18 ФЗ № 17-ФЗ); ИП освобождён от фиксированных взносов «за себя» (57 390 ₽/год) и от 1% свыше 300 000 ₽; сохраняется фиксированный ВНиМ 2 959 ₽/год = 246,58 ₽/мес (платится только при наличии сотрудников). Уменьшения налога взносами на АУСН нет.',
    'АУСН — экспериментальный режим (действует до 31.12.2027). Оренбургская область присоединилась с 01.01.2025 (Закон Оренбургской области от 29.11.2024 № 1292/547-VII-ОЗ). Проверить: лимит дохода ≤ 60 млн ₽/год, число сотрудников ≤ 5, расчёты через уполномоченный банк, допустимость вида деятельности/схемы с Ozon, невозможность добровольно уйти с режима в течение 12 месяцев.',
    'Даты фактической уплаты налогов и взносов уточнить (фиксированные взносы ИП — до 31.12.2026); в модели — помесячный эквивалент.',
    'Октябрьская частичная выплата 25.11.2026 — сумма неизвестна, в резерв не заложена. Грубая оценка 136 853,81 ₽ (17/30 от Q3-среднего) — только ориентир: не гарантия и не чистый доход.',
    'Cashback 1 000 ₽/день (72 000 ₽ за период) — один расход; не дублировать как отдельную логистику/доставку.',
    'Прочие траты (ремонт, расходники, бухгалтерия и т. п.) владельцем не подтверждены — редактируемая строка на листе «Расходы бизнеса», по умолчанию 0 ₽.',
    'Аренда, зарплаты и счета могут требовать оплаты полными месячными суммами — уточнить даты платежей; для этого в модели есть «осторожный вариант» (3 полных месяца).',
    'Кредит: фактические суммы закрытия долгов (143 323,53 ₽ и 50 000 ₽) и реально свободные деньги подтвердить в банке; не считать все 923 000 ₽ свободными автоматически. Старый автокредит 16 500 ₽/мес, возможно, рефинансируется — не учитывать старый и новый платёж одновременно без подтверждения.',
    'Цена ПВЗ 650 000–700 000 ₽ (675 000 ₽ — расчётный ориентир, не согласована) — не входит в операционный резерв и показана отдельно.',
    'Личные расходы (аренда квартиры 20 000 ₽/мес, старый автокредит 16 500 ₽/мес) показаны отдельным блоком; зарплата на заводе 110–130 тыс. ₽/мес продолжается (ориентир 120 тыс. ₽).',
    'Drop-off: модель 250 товаров × 10 ₽ × 30 дней = 75 000 ₽/мес против фактических 77 835,83 ₽/мес за Q3 — сверить объёмы и тарифы; за август ~5 700 выдач, за сентябрь ~5 800.',
]
r = 4
for i, a in enumerate(ASSUMPTIONS, 1):
    cell(ws_asm, r, 1, i, NUM0, align='c', bold=True, border=False)
    c = ws_asm.cell(row=r, column=2, value=a)
    c.font = F_BODY
    c.alignment = WRAP
    c.border = BORDER
    ws_asm.row_dimensions[r].height = 13 * max(1, math.ceil(len(a) / 140)) + 4
    r += 1

r += 1
sec(ws_asm, r, 'ИСТОЧНИКИ (проверка режима АУСН и параметров 2026 г.)', 2)
SOURCES = [
    'АУСН: 0% ставка страховых взносов, освобождение ИП от фиксированных взносов и 1% — https://www.v2b.ru/articles/strahovye-vznosy-i-ndfl-na-ausn-v-2026-godu/ ; https://www.klerk.ru/blogs/astral/634402/',
    'ВНиМ на АУСН 2 959 ₽/год = 246,58 ₽/мес (2026) — https://www.moedelo.org/club/article-knowledge/vznosy-na-travmatizm-na-ausn-kak-platit-i-cto-delat-esli-net-rabotnikov',
    'Оренбургская область в эксперименте АУСН с 01.01.2025 — https://vkirove.ru/news/2025/12/12/v_kakikh_regionakh_rf_deystvuet_ausn_v_2026_godu.html',
    'Условия АУСН (доход ≤ 60 млн ₽, сотрудников ≤ 5, уполномоченный банк) — https://pay.yandex.ru/blog/articles/kak-rabotat-na-ausn-v-2026-godu',
    'Фиксированные взносы ИП 2026 = 57 390 ₽, 1% свыше 300 000 ₽ — https://www.moedelo.org/club/article-knowledge/ip-i-strahovye-vznosy-v-2026-godu-skolko-platit-cto-izmenilos-i-kak-ne-pereplatit ; https://www.klerk.ru/blogs/moedelo/663649/',
]
r += 1
for i, s in enumerate(SOURCES, 1):
    cell(ws_asm, r, 1, i, NUM0, align='c', bold=True, border=False)
    c = ws_asm.cell(row=r, column=2, value=s)
    c.font = F_NOTE
    c.alignment = WRAP
    ws_asm.row_dimensions[r].height = 13 * max(1, math.ceil(len(s) / 140)) + 4
    r += 1

# --------------------------------------------------------------- проверка ----
def verify():
    q3 = (222467.62 + 213911.06 + 288142.49) / 3
    days, months = 72, 2.4
    gross = 54000 / 0.87
    payroll = gross + gross * 0.3 + 600
    reg = 42000 + 3000 + 30000 + 1800 + 2100
    # УСН
    tax0 = q3 * 0.06
    own = 4782.50 + 2165.07
    emp = gross * 0.3 + 600
    red = min(own + emp, tax0 * 0.5)
    usn_m = reg + payroll + (tax0 - red) + own
    usn_72 = usn_m * months
    usn_res = usn_72 + 67680 + 50000
    usn_caut = (usn_m - 30000) * 3 + 72000 + 67680 + 50000
    # АУСН
    ausn_m = reg + gross + q3 * 0.08 + 246.58
    ausn_72 = ausn_m * months
    ausn_res = ausn_72 + 67680 + 50000
    ausn_caut = (ausn_m - 30000) * 3 + 72000 + 67680 + 50000
    checks = [
        ('Q3-среднее', q3, 241507.06),
        ('УСН ₽/мес', usn_m, 174382.44),
        ('АУСН ₽/мес', ausn_m, 160536.11),
        ('УСН ₽/72 дня', usn_72, 418517.86),
        ('АУСН ₽/72 дня', ausn_72, 385286.66),
        ('Резерв УСН (итого)', usn_res, 536197.86),
        ('Резерв АУСН (итого)', ausn_res, 502966.66),
        ('Осторожный УСН', usn_caut, 622827.32),
        ('Осторожный АУСН', ausn_caut, 581288.33),
    ]
    print('%-24s %15s %15s %8s' % ('Показатель', 'Модель', 'Владелец', 'Статус'))
    ok = True
    for name, got, exp in checks:
        good = abs(got - exp) < 0.5
        ok = ok and good
        print('%-24s %15.2f %15.2f %8s' % (name, got, exp, 'OK' if good else 'РАЗНИЦА'))
    print('\nВсе сверки с предварительным расчётом владельца:', 'СОВПАДАЮТ' if ok else 'ЕСТЬ РАСХОЖДЕНИЯ')


OUT = 'Резерв_ПВЗ_Орск_15.10-25.12.2026.xlsx'
wb.calculation.fullCalcOnLoad = True
wb.save(OUT)
print(f'Сохранено: {OUT}')
verify()
