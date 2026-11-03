"""End-to-end coaching workflow; test notes are isolated from user records."""
import json
import os
import tempfile
from pathlib import Path
from streamlit.testing.v1 import AppTest

directory=Path(tempfile.mkdtemp(prefix='matchplan_ui_check_'))
os.environ['MATCHPLAN_SESSION_DIR']=str(directory)

def check(app):
    assert not app.exception,[e.message for e in app.exception]

a=AppTest.from_file('app.py',default_timeout=240).run(); check(a)
assert any(x.value=='Пульт тренера: выбрать, согласовать, проверить' for x in a.subheader)
next(x for x in a.button if x.label=='Собрать единый пакет действий').click().run(); check(a)
assert any('Ваш пакет:' in x.value for x in a.markdown)
next(x for x in a.text_area if x.label=='Заметка к выбранному решению').set_value('Isolated integration test').run(); check(a)
next(x for x in a.button if x.label=='Сохранить выполнение и заметку').click().run(); check(a)
saved=list(directory.glob('*.json')); assert len(saved)==1
record=json.loads(saved[0].read_text(encoding='utf-8'))
assert list(record['decisions'].values())[0]['note']=='Isolated integration test'
a.slider[0].set_value(4500).run(); check(a)
assert any('Пакет требует пересмотра' in x.value for x in a.warning)
next(x for x in a.button if x.label=='Собрать единый пакет действий').click().run(); check(a)
next(x for x in a.button if x.label=='Найти похожие ситуации').click().run(); check(a)
next(x for x in a.radio if x.label=='Отрезок цепочек').set_value('Весь выбранный матч').run(); check(a)
assert next(x for x in a.selectbox if x.label=='Выберите удар для разбора')
next(x for x in a.radio if x.label=='Чьи атаки разобрать').set_value('Соперника').run(); check(a)
assert next(x for x in a.selectbox if x.label=='Выберите удар для разбора')
headings=[x.value for x in a.subheader]
assert headings.index('Прогноз на текущий момент')<headings.index('Текущий прогресс матча')<headings.index('Метрики обучения и проверки моделей')
print('PASS: plan comparison, consistent package, persisted isolated checklist/notes, stale-package warning, historical lookup, both attack chains, forecast order')
print('Isolated test records:',directory)
