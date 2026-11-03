"""Headless interaction checks using Streamlit's supported testing API."""
from streamlit.testing.v1 import AppTest


def check(app):
    assert not app.exception, [e.message for e in app.exception]


app = AppTest.from_file('app.py', default_timeout=240).run()
check(app)
assert app.tabs[0].label == 'Решение сейчас'
assert [t.label for t in app.tabs] == ['Решение сейчас', 'Состав и подготовка', 'Проверить сценарий',
    'Сравнить цели', 'Журнал и отчёт', 'Прогноз и метрики', 'О данных']
assert any(x.value == '2. Схема действий и поведение в фазах игры' for x in app.subheader)
assert any(x.value == '3. Задачи игрокам текущего состава' for x in app.subheader)
assert not any('Схема выполнения задачи на поле' == x.label for x in app.expander)
headings=[x.value for x in app.subheader]
assert headings.index('Прогноз на текущий момент') < headings.index('Текущий прогресс матча') < headings.index('Метрики обучения и проверки моделей')
for mode in ('Сеть передач', 'Где забиваем', 'Где пропускаем', 'Состав'):
    next(x for x in app.radio if x.label == 'Вид поля').set_value(mode).run()
    check(app)
next(x for x in app.selectbox if x.label == 'Быстрый сценарий').set_value('Пропустили гол').run()
check(app)
assert next(x for x in app.number_input if x.label == 'Голы соперника в сценарии').value == 1
next(x for x in app.selectbox if x.label == 'Быстрый сценарий').set_value('Свободный выбор').run()
check(app)
app.slider[0].set_value(4500).run()
check(app)
next(x for x in app.button if x.label == 'Зафиксировать план на этот отрезок').click().run()
check(app)
app.slider[0].set_value(4800).run()
check(app)
assert any('Зафиксировано:' in x.value for x in app.markdown)
next(x for x in app.button if x.label == 'Подобрать совместимую схему для текущих игроков').click().run()
check(app)
next(x for x in app.radio if x.label == 'Цель на матч').set_value('Не проиграть').run()
check(app)
app.button[0].click().run()
check(app)
app.multiselect[0].set_value([app.multiselect[0].options[0]]).run()
check(app)
from core import matches
test_game = matches(2, 27)[-1]
next(x for x in app.selectbox if x.label == 'Матч').set_value(test_game).run()
check(app)
app.slider[0].set_value(4500).run()
check(app)
assert next(x for x in app.selectbox if x.label == 'Модель прогноза')
next(x for x in app.selectbox if x.label == 'Модель прогноза').set_value('LSTM').run()
check(app)
next(x for x in app.button if x.label == 'Рассчитать отдельный сценарий').click().run()
check(app)
next(x for x in app.button if x.label == 'Сравнить подсказки с реальными заменами').click().run()
check(app)
print('PASS: short-plan freeze/review, compatible formation, decision-first navigation, quick goal scenario, startup, replay, target switch, rewind, prematch exclusion, held-out match, six-model inference, LSTM switch, scenario, coach comparison')
