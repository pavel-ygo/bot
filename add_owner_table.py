#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Добавляет в готовую модель лист «Таблица владельца» — воссоздание таблицы
денежных потоков по фото (полумесячные периоды 15.10–28.02, строки расходов,
выплаты Ozon, налог 7%, остаток, блок «Расчет до 30 декабря»).
"""
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

FILE = 'Резерв_ПВЗ_Орск_15.10-25.12.2026.xlsx'
MONEY = '# ##0" ₽"'

C_DARK, C_HEAD, C_INPUT, C_TOTAL, C_NOTE = '1F4E78', 'D9E1F2', 'FFF2CC', 'F2F2F2', '808080'
THIN = Side(style='thin', color='BFBFBF')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
F_TITLE = Font(name='Calibri', size=14, bold=True, color=C_DARK)
F_SEC = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
F_HEAD = Font(name='Calibri', size=10, bold=True)
F_BODY = Font(name='Calibri', size=10)
F_BOLD = Font(name='Calibri', size=10, bold=True)
F_NOTE = Font(name='Calibri', size=9, italic=True, color=C_NOTE)
WRAP = Alignment(vertical='top', wrap_text=True)
CENTER = Alignment(horizontal='center', vertical='center')
RIGHT = Alignment(horizontal='right', vertical='center')

wb = load_workbook(FILE)
if 'Таблица владельца' in wb.sheetnames:
    del wb['Таблица владельца']
ws = wb.create_sheet('Таблица владельца')
wb.move_sheet(ws, offset=-(len(wb.sheetnames) - 1 - wb.sheetnames.index('Расходы бизнеса')))
ws.sheet_properties.tabColor = 'C00000'

widths = {'A': 40, 'L': 16, 'M': 2, 'N': 46, 'O': 16}
for col in 'BCDEFGHIJK':
    widths[col] = 12
for col, w in widths.items():
    ws.column_dimensions[col].width = w

def sec(row, text, last_col=12):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    c = ws.cell(row=row, column=1, value=text)
    c.font = F_SEC
    c.fill = PatternFill('solid', fgColor=C_DARK)
    c.alignment = Alignment(vertical='center')
    ws.row_dimensions[row].height = 20

def put(row, col, value, fmt=MONEY, inp=False, bold=False, note=False, align='r', border=True):
    c = ws.cell(row=row, column=col, value=value)
    c.font = F_NOTE if note else (F_BOLD if bold else F_BODY)
    if fmt:
        c.number_format = fmt
    if inp:
        c.fill = PatternFill('solid', fgColor=C_INPUT)
    if bold:
        c.fill = PatternFill('solid', fgColor=C_TOTAL)
    c.alignment = {'r': RIGHT, 'c': CENTER, 'l': Alignment(vertical='center', wrap_text=True)}[align]
    if border:
        c.border = BORDER
    return c

def note_row(row, text, last_col=12):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    c = ws.cell(row=row, column=1, value=text)
    c.font = F_NOTE
    c.alignment = WRAP
    ws.row_dimensions[row].height = 26

# ---------------------------------------------------------------- заголовок --
ws.merge_cells('A1:L1')
ws['A1'] = 'ТАБЛИЦА ДЕНЕЖНЫХ ПОТОКОВ ПВЗ (воссоздана по фото модели владельца)'
ws['A1'].font = F_TITLE
note_row(2, 'Колонки — полумесячные периоды, дата в шапке = КОНЕЦ периода (30.окт = 15.10–30.10 и т. д.). '
            'Жёлтые ячейки — значения для редактирования, остальное — формулы. '
            'Выплаты Ozon: 25.11 — 110 000 ₽ (октябрь, частичная), 25.12 — 230 000 ₽, 25.01 — 240 000 ₽, 25.02 — 225 000 ₽.')

HDR = 4
PERIODS = ['15.окт', '30.окт', '15.ноя', '30.ноя', '15.дек', '30.дек',
           '15.янв', '30.янв', '15.фев', '28.фев']
put(HDR, 1, 'Статья', fmt=None, bold=True, align='l')
for i, p in enumerate(PERIODS):
    put(HDR, 2 + i, p, fmt=None, bold=True, align='c')
put(HDR, 12, 'Итого за период', fmt=None, bold=True, align='c')
ws.row_dimensions[HDR].height = 22

# ------------------------------------------------------------------- расходы --
# столбцы: B=15.окт(до оформления) C=30.окт D=15.ноя E=30.ноя F=15.дек G=30.дек H=15.янв I=30.янв J=15.фев K=28.фев
MONTHLY_15 = ['C', 'E', 'G', 'I', 'K']   # аренда/коммунальные — платежи 15-го числа
CREDIT = ['D', 'F', 'H', 'J']            # кредит — платежи 4-го числа
ALL = list('CDEFGHIJK')                  # cashback и зарплата — каждое полумесяце

R_RENT, R_ELEC, R_SELL, R_CAM, R_NET, R_CRED, R_ZP, R_ONE = 5, 6, 7, 8, 9, 10, 11, 12
R_TOTP, R_TOTM = 13, 14

rows_def = [
    (R_RENT, 'Аренда', 42000, MONTHLY_15),
    (R_ELEC, 'Электричество', 3000, MONTHLY_15),
    (R_SELL, 'Селлер (cashback)', 15000, ALL),
    (R_CAM, 'Камеры', 2100, MONTHLY_15),
    (R_NET, 'Интернет', 1800, MONTHLY_15),
    (R_CRED, 'Кредит', 34000, CREDIT),
    (R_ZP, 'Зарплата (зп)', 35000, ALL),
]
for r, label, val, cols in rows_def:
    put(r, 1, label, fmt=None, align='l')
    for col in cols:
        put(r, ord(col) - 64, val, inp=True)
    put(r, 12, f'=SUM(B{r}:K{r})', bold=True)

put(R_ONE, 1, 'Разовые траты старта (состав уточнить)', fmt=None, align='l')
put(R_ONE, ord('C') - 64, 30300, inp=True)
put(R_ONE, 12, f'=SUM(B{R_ONE}:K{R_ONE})', bold=True)

put(R_TOTP, 1, 'ИТОГО расходов за период', fmt=None, bold=True, align='l')
for col in 'BCDEFGHIJK':
    put(R_TOTP, ord(col) - 64, f'=SUM({col}{R_RENT}:{col}{R_ONE})', bold=True)
put(R_TOTP, 12, f'=SUM(B{R_TOTP}:K{R_TOTP})', bold=True)

put(R_TOTM, 1, 'ИТОГО за месяц (два полумесяца)', fmt=None, bold=True, align='l')
for col in ['C', 'E', 'G', 'I', 'K']:
    prev = chr(ord(col) - 1)
    put(R_TOTM, ord(col) - 64, f'={prev}{R_TOTP}+{col}{R_TOTP}', bold=True)

note_row(15, 'Первый период (30.окт) = 129 200 ₽: обычные расходы полумесяца 98 900 ₽ + разовые траты старта '
             '30 300 ₽ (взяты из модели владельца — состав подтвердить). Полный месяц = 182 900 ₽ '
             '(42 000 + 3 000 + 30 000 + 2 100 + 1 800 + 34 000 + 70 000).')

# ------------------------------------------------- выплаты, налог, остаток --
sec(17, 'ВЫПЛАТЫ OZON, НАЛОГ И ОСТАТОК')
R_PAY, R_TAX, R_NETPAY, R_BAL, R_CUM = 18, 19, 20, 21, 22
put(R_PAY, 1, 'Выплата Ozon (дата в периоде)', fmt=None, align='l')
for col, val, dt in [('E', 110000, '25.11'), ('G', 230000, '25.12'), ('I', 240000, '25.01'), ('K', 225000, '25.02')]:
    put(R_PAY, ord(col) - 64, val, inp=True)
put(R_PAY, 12, f'=SUM(B{R_PAY}:K{R_PAY})', bold=True)

put(R_TAX, 1, 'Налог 7% от выплаты (модель владельца)', fmt=None, align='l')
for col in ['E', 'G', 'I', 'K']:
    put(R_TAX, ord(col) - 64, f'={col}{R_PAY}*0.07')
put(R_TAX, 12, f'=SUM(B{R_TAX}:K{R_TAX})', bold=True)

put(R_NETPAY, 1, 'Выплата минус налог', fmt=None, align='l')
for col in 'BCDEFGHIJK':
    put(R_NETPAY, ord(col) - 64, f'=IF({col}{R_PAY}=0,0,{col}{R_PAY}-{col}{R_TAX})')
put(R_NETPAY, 12, f'=SUM(B{R_NETPAY}:K{R_NETPAY})', bold=True)

put(R_BAL, 1, 'ОСТАТОК за месяц (как в модели владельца)', fmt=None, bold=True, align='l')
for col in ['C', 'E', 'G', 'I', 'K']:
    put(R_BAL, ord(col) - 64, f'={col}{R_NETPAY}-{col}{R_TOTM}', bold=True)

put(R_CUM, 1, 'Накопительный остаток (доп. строка)', fmt=None, align='l')
for col in 'BCDEFGHIJK':
    put(R_CUM, ord(col) - 64,
        f'=SUM($B${R_NETPAY}:{col}{R_NETPAY})-SUM($B${R_TOTP}:{col}{R_TOTP})')

note_row(23, '«Остаток за месяц» = выплата минус налог минус расходы месяца. «Накопительный остаток» — реальное '
             'сальдо бизнеса с нуля: к 28.02 оно составляет около −112 150 ₽, то есть при заданном графике выплат '
             'бизнесу нужно примерно 112 тыс. ₽ своих денег на весь период; консервативный резерв до 25.12 '
             '(без учёта выплат) — на листе «Итог».')

# --------------------------------------------------------- правый блок -------
sec(4, 'РАСЧЕТ ДО 30 ДЕКАБРЯ', last_col=1) if False else None
ws.merge_cells('N4:O4')
c = ws['N4']
c.value = 'РАСЧЕТ ДО 30 ДЕКАБРЯ (2,5 мес.)'
c.font = F_SEC
c.fill = PatternFill('solid', fgColor=C_DARK)
c.alignment = Alignment(vertical='center')

# ссылки на строки таблицы: 5 аренда, 6 электричество, 7 селлер, 8 камеры,
# 9 интернет, 10 кредит (первый платёж в столбце D), 11 зарплата
BLOCK = [
    ('Аренда (3 платежа)', '=C5*3'),
    ('Электричество (3 мес.)', '=C6*3'),
    ('Селлер / cashback (5 полумесяцев)', '=C7*5'),
    ('Камеры (3 мес.)', '=C8*3'),
    ('Интернет (3 мес.)', '=C9*3'),
    ('Кредит (3 платежа по 34 000)', '=D10*3'),
    ('Зарплата (5 полумесяцев)', '=C11*5'),
]
r = 5
for label, f in BLOCK:
    put(r, 14, label, fmt=None, align='l')
    put(r, 15, f)
    r += 1
put(r, 14, 'ИТОГО РАСХОДОВ до 30 декабря', fmt=None, bold=True, align='l')
put(r, 15, f'=SUM(O5:O{r - 1})', bold=True)
R_BTOT = r
r += 2
put(r, 14, 'Выплата 25.12 (за ноябрь)', fmt=None, align='l')
put(r, 15, f'=G{R_PAY}')
r += 1
put(r, 14, 'минус налог 7%', fmt=None, align='l')
put(r, 15, f'=G{R_PAY}-G{R_NETPAY}')
r += 1
put(r, 14, 'ЕСЛИ ИСПОЛЬЗОВАТЬ ВЫПЛАТУ ЗА ДЕКАБРЬ', fmt=None, bold=True, align='l')
put(r, 15, f'=O{R_BTOT}-G{R_NETPAY}', bold=True)
r += 2
for txt in [
    'Блок воспроизводит расчёт владельца: месячные статьи — 3 платежа, полумесячные (селлер, зп) — 5.',
    'Кредит: фактически до 25.12 платежи 04.11 и 04.12 = 2 × 33 840 = 67 680 ₽; в блоке — 3 платежа (осторожно).',
    'Налог 7% от выплаты — упрощение модели владельца; подробно УСН/АУСН — на листе «Расходы бизнеса».',
]:
    ws.merge_cells(start_row=r, start_column=14, end_row=r, end_column=15)
    c = ws.cell(row=r, column=14, value=txt)
    c.font = F_NOTE
    c.alignment = WRAP
    ws.row_dimensions[r].height = 24
    r += 1

ws.freeze_panes = 'B5'
# порядок листов: Итог, Доходы Ozon, Расходы бизнеса, Таблица владельца, Кредит, Личные финансы, Допущения
order = ['Итог', 'Доходы Ozon', 'Расходы бизнеса', 'Таблица владельца',
         'Кредит', 'Личные финансы', 'Допущения и вопросы']
wb._sheets = [wb[name] for name in order]
wb.calculation.fullCalcOnLoad = True
wb.save(FILE)
print('Лист «Таблица владельца» добавлен в', FILE)
