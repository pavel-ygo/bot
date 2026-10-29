#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Добавляет лист «Второй ПВЗ (оценка)»: экономика точки с привозом 100–120 товаров/день
(на базе фактических данных действующего ПВЗ владельца) и ориентир цены покупки.
"""
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

FILE = 'Резерв_ПВЗ_Орск_15.10-25.12.2026.xlsx'
MONEY = '# ##0.00" ₽"'
MONEY0 = '# ##0" ₽"'
NUM0 = '0'
NUM1 = '0.0'

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
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
RIGHT = Alignment(horizontal='right', vertical='center')

wb = load_workbook(FILE)
if 'Второй ПВЗ (оценка)' in wb.sheetnames:
    del wb['Второй ПВЗ (оценка)']
ws = wb.create_sheet('Второй ПВЗ (оценка)')
ws.sheet_properties.tabColor = '7030A0'

for col, w in {'A': 46, 'B': 17, 'C': 17, 'D': 17, 'E': 17, 'F': 62}.items():
    ws.column_dimensions[col].width = w


def sec(row, text, last_col=6):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    c = ws.cell(row=row, column=1, value=text)
    c.font = F_SEC
    c.fill = PatternFill('solid', fgColor=C_DARK)
    c.alignment = Alignment(vertical='center')
    ws.row_dimensions[row].height = 20


def put(row, col, value, fmt=MONEY, inp=False, bold=False, note=False, align='r'):
    c = ws.cell(row=row, column=col, value=value)
    c.font = F_NOTE if note else (F_BOLD if bold else F_BODY)
    if fmt:
        c.number_format = fmt
    if inp:
        c.fill = PatternFill('solid', fgColor=C_INPUT)
    if bold:
        c.fill = PatternFill('solid', fgColor=C_TOTAL)
    c.alignment = {'r': RIGHT, 'c': CENTER, 'l': Alignment(vertical='center', wrap_text=True)}[align]
    c.border = BORDER
    return c


def note_row(row, text, last_col=6):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    c = ws.cell(row=row, column=1, value=text)
    c.font = F_NOTE
    c.alignment = WRAP
    ws.row_dimensions[row].height = 26


ws.merge_cells('A1:F1')
ws['A1'] = 'ОЦЕНКА ВТОРОГО ПВЗ (привоз 100–120 товаров/день)'
ws['A1'].font = F_TITLE
note_row(2, 'Расчёт — экстраполяция экономики вашего ПВЗ на меньший объём: ставки и структура расходов взяты '
            'из ваших данных, объём и часть статей расходов масштабируются. Жёлтые ячейки — ввод. '
            'Это модель для переговоров, не факт: реальные цифры берутся из кабинета Ozon владельца точки.')

# ------------------------------------------------------- объём и доходы ------
sec(4, '1. ОБЪЁМ И ВОЗНАГРАЖДЕНИЕ (масштаб от вашего ПВЗ)')
put(5, 1, 'Показатель', fmt=None, bold=True, align='l')
put(5, 2, 'Значение', fmt=None, bold=True, align='c')
put(5, 6, 'Примечание', fmt=None, bold=True, align='l')
R_ITEMS, R_TD, R_KI, R_TV, R_DROP, R_ISS, R_ISSR, R_OTH, R_REM = 6, 7, 8, 9, 10, 11, 12, 13, 14
put(R_ITEMS, 1, 'Привоз, товаров/день', align='l')
put(R_ITEMS, 2, 110, NUM0, inp=True, align='c')
put(R_ITEMS, 6, 'У вашего ПВЗ ~250/день; у рассматриваемой точки 100–120', note=True)
put(R_TD, 1, 'Тариф drop-off, ₽/товар', align='l')
put(R_TD, 2, 10, MONEY, inp=True)
put(R_TD, 6, 'Ваша модель: 250 × 10 ₽ × 30 = 75 000 ₽; факт Q3 = 77 836 ₽ (≈10,4 ₽/товар)', note=True)
put(R_KI, 1, 'Выдач на 1 привезённый товар', align='l')
put(R_KI, 2, 0.77, '0.00', inp=True, align='c')
put(R_KI, 6, 'У вас: ~5 700–5 800 выдач при ~7 500 привозов в месяц', note=True)
put(R_TV, 1, 'Тариф выдачи, ₽ за выдачу', align='l')
put(R_TV, 2, 22.91, MONEY, inp=True)
put(R_TV, 6, 'Факт Q3: 131 760 ₽ / 5 750 выдач', note=True)
put(R_DROP, 1, 'Drop-off, ₽/мес', align='l')
put(R_DROP, 2, f'=B{R_ITEMS}*30*B{R_TD}')
put(R_ISS, 1, 'Выдач, шт/мес', align='l')
put(R_ISS, 2, f'=B{R_ITEMS}*30*B{R_KI}', NUM0)
put(R_ISSR, 1, 'Выдача, ₽/мес', align='l')
put(R_ISSR, 2, f'=B{R_ISS}*B{R_TV}')
put(R_OTH, 1, 'Прочие категории, ₽/мес', align='l')
put(R_OTH, 2, f'=B{R_ITEMS}/250*31911.31')
put(R_OTH, 6, 'Пропорционально объёму (Q3 у вас: 31 911 ₽/мес; сверить с актами)', note=True)
put(R_REM, 1, 'ВОЗНАГРАЖДЕНИЕ, ₽/мес', bold=True, align='l')
put(R_REM, 2, f'=B{R_DROP}+B{R_ISSR}+B{R_OTH}', bold=True)
put(R_REM, 6, 'Проверка: 241 507 ₽ × (110/250) ≈ 106 263 ₽', note=True)

# ------------------------------------------------------------- расходы -------
sec(16, '2. РАСХОДЫ ТОЧКИ (ввод)')
R_RENT, R_ELEC, R_NET, R_CAM, R_CB, R_N, R_SAL = 17, 18, 19, 20, 21, 22, 23
put(R_RENT, 1, 'Аренда, ₽/мес', align='l')
put(R_RENT, 2, 30000, MONEY0, inp=True)
put(R_RENT, 6, 'У вас 42 000; у маленькой точки обычно меньше — уточнить по договору', note=True)
put(R_ELEC, 1, 'Электричество, ₽/мес', align='l')
put(R_ELEC, 2, 2500, MONEY0, inp=True)
put(R_NET, 1, 'Интернет, ₽/мес', align='l')
put(R_NET, 2, 1800, MONEY0, inp=True)
put(R_CAM, 1, 'Камеры, ₽/мес', align='l')
put(R_CAM, 2, 2100, MONEY0, inp=True)
put(R_CB, 1, 'Cashback селлерам, ₽/мес', align='l')
put(R_CB, 2, f'=B{R_ITEMS}/250*1000*30', MONEY0)
put(R_CB, 6, 'Масштабируется от объёма: 1 000 ₽/день у вас при 250 привозов (здесь 440 ₽/день × 30)', note=True)
put(R_N, 1, 'Сотрудников, чел.', align='l')
put(R_N, 2, 1, NUM0, inp=True, align='c')
put(R_N, 6, 'Ключевой параметр: при 100–120 привозов/день точка тянет одного сотрудника', note=True)
put(R_SAL, 1, 'Зарплата на руки, ₽/мес на человека', align='l')
put(R_SAL, 2, 27000, MONEY0, inp=True)

# ------------------------------------------------------------- персонал ------
sec(25, '3. ПЕРСОНАЛ')
R_GROSS, R_CONTRIB, R_TRAUMA, R_FOT, R_FOTA = 26, 27, 28, 29, 30
put(R_GROSS, 1, 'Gross ФОТ (с НДФЛ 13%)', align='l')
put(R_GROSS, 2, f'=B{R_N}*B{R_SAL}/(1-0.13)')
put(R_CONTRIB, 1, 'Страховые взносы 30%', align='l')
put(R_CONTRIB, 2, f'=B{R_GROSS}*0.3')
put(R_TRAUMA, 1, 'Травматизм (300 ₽/чел.)', align='l')
put(R_TRAUMA, 2, f'=B{R_N}*300', MONEY0)
put(R_FOT, 1, 'Полная стоимость ФОТ (УСН)', align='l')
put(R_FOT, 2, f'=B{R_GROSS}+B{R_CONTRIB}+B{R_TRAUMA}', bold=True)
put(R_FOTA, 1, 'Персонал на АУСН (только gross)', align='l')
put(R_FOTA, 2, f'=B{R_GROSS}')
put(R_FOTA, 6, 'На АУСН взносы за сотрудников 0% — для маленькой точки это решающая экономия', note=True)

# --------------------------------------------------------------- налоги ------
sec(32, '4. НАЛОГИ И ВЗНОСЫ ИП (точка отдельным ИП)')
put(33, 2, 'АУСН 8%', fmt=None, bold=True, align='c')
put(33, 3, 'УСН 6%', fmt=None, bold=True, align='c')
put(33, 6, 'Примечание', fmt=None, bold=True, align='l')
R_RATE, R_TAX, R_RED, R_VNIM, R_TOTTAX = 34, 35, 36, 37, 38
put(R_RATE, 1, 'Ставка налога', align='l')
put(R_RATE, 2, 0.08, '0.0%', inp=True, align='c')
put(R_RATE, 3, 0.06, '0.0%', inp=True, align='c')
put(R_TAX, 1, 'Налог до уменьшения', align='l')
put(R_TAX, 2, f'=$B${R_REM}*B{R_RATE}')
put(R_TAX, 3, f'=$B${R_REM}*C{R_RATE}')
put(R_RED, 1, 'Уменьшение налога взносами (≤50%)', align='l')
put(R_RED, 3, f'=MIN(4782.5+($B${R_REM}*12-300000)*0.01/12+B{R_CONTRIB}+B{R_TRAUMA},C{R_TAX}*0.5)')
put(R_RED, 6, 'Свои взносы (4 782,50 + 1%) + взносы за сотрудника; лимит 50%', note=True)
put(R_VNIM, 1, 'ВНиМ ИП (АУСН, 2 959 ₽/год)', align='l')
put(R_VNIM, 2, 246.58, MONEY, inp=True)
put(R_VNIM, 3, 0, MONEY)
put(R_TOTTAX, 1, 'Итого налоги и взносы ИП, ₽/мес', bold=True, align='l')
put(R_TOTTAX, 2, f'=B{R_TAX}+B{R_VNIM}', bold=True)
put(R_TOTTAX, 3, f'=C{R_TAX}-C{R_RED}+4782.5+($B${R_REM}*12-300000)*0.01/12', bold=True)
put(R_TOTTAX, 6, 'УСН: налог после уменьшения + фиксвзносы 4 782,50 + 1% свыше 300 000 ₽', note=True)

# ------------------------------------------------- итого и прибыль (матрица) --
sec(40, '5. ИТОГО: ПРИБЫЛЬ ТОЧКИ ПРИ РАЗНЫХ УСЛОВИЯХ')
put(41, 1, 'Показатель', fmt=None, bold=True, align='l')
for ci, h in [(2, 'АУСН, 1 сотрудник'), (3, 'УСН, 1 сотрудник'), (4, 'АУСН, 2 сотрудника'), (5, 'УСН, 2 сотрудника')]:
    put(41, ci, h, fmt=None, bold=True, align='c')
M_FIX, M_PERS, M_TAX, M_TOT, M_REM, M_PROF = 42, 43, 44, 45, 46, 47
put(M_FIX, 1, 'Постоянные расходы (аренда, камеры, интернет, свет, cashback)', align='l')
for ci in range(2, 6):
    put(M_FIX, ci, f'=SUM(B{R_RENT}:B{R_CB})')
put(M_PERS, 1, 'Персонал', align='l')
put(M_PERS, 2, f'=B{R_FOTA}')
put(M_PERS, 3, f'=B{R_FOT}')
put(M_PERS, 4, f'=B{R_FOTA}/B{R_N}*2')
put(M_PERS, 5, f'=B{R_FOT}/B{R_N}*2')
put(M_TAX, 1, 'Налоги и взносы ИП', align='l')
put(M_TAX, 2, f'=B{R_TOTTAX}')
put(M_TAX, 3, f'=C{R_TOTTAX}')
put(M_TAX, 4, f'=B{R_TOTTAX}')
put(M_TAX, 5, f'=C{R_TOTTAX}')
put(M_TOT, 1, 'ИТОГО расходов, ₽/мес', bold=True, align='l')
for ci in range(2, 6):
    col = chr(64 + ci)
    put(M_TOT, ci, f'={col}{M_FIX}+{col}{M_PERS}+{col}{M_TAX}', bold=True)
put(M_REM, 1, 'Вознаграждение Ozon, ₽/мес', align='l')
for ci in range(2, 6):
    put(M_REM, ci, f'=$B${R_REM}')
put(M_PROF, 1, 'ПРИБЫЛЬ, ₽/мес', bold=True, align='l')
for ci in range(2, 6):
    col = chr(64 + ci)
    put(M_PROF, ci, f'={col}{M_REM}-{col}{M_TOT}', bold=True)

# ----------------------------------------------------------- оценка цены -----
sec(49, '6. ОРИЕНТИР ЦЕНЫ ПОКУПКИ')
P_MULT, P_MULTP, P_12, P_18 = 50, 51, 52, 53
put(P_MULT, 1, 'Мультипликатор вашей сделки (мес. вознаграждения)', align='l')
put(P_MULT, 2, 2.8, '0.0', inp=True, align='c')
put(P_MULT, 6, '675 000 ₽ / 241 507 ₽ = 2,8 мес. вознаграждения', note=True)
put(P_MULTP, 1, 'Цена по мультипликатору (2,8 × вознаграждение)', align='l')
put(P_MULTP, 2, f'=B{R_REM}*B{P_MULT}', MONEY0)
put(P_12, 1, 'Цена по прибыли, 12 мес. (АУСН, 1 сотрудник)', align='l')
put(P_12, 2, f'=B{M_PROF}*12', MONEY0)
put(P_18, 1, 'Цена по прибыли, 18 мес. (АУСН, 1 сотрудник)', align='l')
put(P_18, 2, f'=B{M_PROF}*18', MONEY0)
ws.merge_cells('A55:F55')
c = ws['A55']
c.value = 'ВЫВОД: ориентир цены ≈ 150 000 – 300 000 ₽ — только при 1 сотруднике и АУСН и подтверждённых цифрах кабинета. При двух сотрудниках точка убыточна — покупать нельзя (цена = стоимость оборудования).'
c.font = F_BOLD
c.fill = PatternFill('solid', fgColor=C_TOTAL)
c.alignment = Alignment(vertical='center', wrap_text=True)
ws.row_dimensions[55].height = 30

# --------------------------------------------------------- стресс-тест -------
sec(57, '7. СТРЕСС-ТЕСТ: МИНУС 30% ОБЪЁМА (72 привоза/день)')
S_REM, S_COST, S_PROF = 58, 59, 60
put(S_REM, 1, 'Вознаграждение, ₽/мес', align='l')
put(S_REM, 2, f'=B{R_REM}*0.7')
put(S_COST, 1, 'Расходы (АУСН, 1 сотрудник; cashback тоже падает)', align='l')
put(S_COST, 2, f'=B{R_RENT}+B{R_ELEC}+B{R_NET}+B{R_CAM}+B{R_CB}*0.7+B{R_FOTA}+B{R_TAX}*0.7+B{R_VNIM}')
put(S_PROF, 1, 'Прибыль, ₽/мес', bold=True, align='l')
put(S_PROF, 2, f'=B{S_REM}-B{S_COST}', bold=True)
put(S_PROF, 6, 'У вашего ПВЗ drop-off за год был от 59 477 до 181 365 ₽/мес — сезонность реальна', note=True)

# ------------------------------------------------------------- проверки ------
sec(62, '8. ЧТО ПРОВЕРИТЬ ПЕРЕД ПОКУПКОЙ (может собрать жена, работая там)')
CHECKS = [
    'Скриншоты вознаграждения из кабинета Ozon за 6–12 месяцев: не среднее, а тренд и сезонность.',
    'Фактическое число выдач и привозов в день, количество активных селлеров, долги по cashback (типичная скрытая ответственность при покупке ПВЗ).',
    'Договор аренды: срок, ставка, долги; рейтинг и штрафы в кабинете Ozon; состояние оборудования (стеллажи, ПК, сканеры, камеры).',
    'Почему продают и на каких условиях передаётся договор с Ozon — только официальная переоформка, не «теневая» передача.',
    'Можно ли одному ИП держать два ПВЗ — уточнить у менеджера Ozon; на одном ИП фиксированные взносы одни (экономия ~4 783 ₽/мес на второй точке).',
    'АУСН для второй точки критичен: экономия взносов за персонал ~9 600 ₽/мес — именно она превращает минус в плюс при одном сотруднике.',
    'Резерв: вторая точка на старте тоже требует денег (ориентировочно 150–250 тыс. ₽) — они конкурируют с резервом первой точки и платежами по кредиту 923 000 ₽.',
    'Альтернатива без риска: жена работает там за 27 000 ₽/мес, собирает реальные цифры 2–3 месяца — и тогда торг с фактами, а не со словами продавца.',
]
r = 63
for i, t in enumerate(CHECKS, 1):
    put(r, 1, f'{i}. {t}', fmt=None, note=True, align='l', )
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    ws.cell(row=r, column=1).alignment = WRAP
    ws.row_dimensions[r].height = 26
    r += 1

ws.freeze_panes = 'A4'

# ссылка на лист с «Итог»
ws_itog = wb['Итог']
ws_itog.merge_cells('A47:D47')
c = ws_itog['A47']
c.value = ('• Оценка покупки второго ПВЗ (100–120 привозов/день) и ориентир его цены — отдельный лист '
           '«Второй ПВЗ (оценка)».')
c.font = F_NOTE
c.alignment = WRAP
ws_itog.row_dimensions[47].height = 24

order = ['Итог', 'Доходы Ozon', 'Расходы бизнеса', 'Таблица владельца', 'Кредит',
         'Личные финансы', 'Второй ПВЗ (оценка)', 'Допущения и вопросы']
wb._sheets = [wb[n] for n in order]
wb.calculation.fullCalcOnLoad = True
wb.save(FILE)
print('Лист «Второй ПВЗ (оценка)» добавлен в', FILE)
