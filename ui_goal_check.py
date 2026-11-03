"""Integration checks for real club goal totals, photo rendering and scope isolation."""
from streamlit.testing.v1 import AppTest
from core import matches

a=AppTest.from_file('app.py',default_timeout=240).run()
assert not a.exception, a.exception
game=next(g for g in matches(2,27) if g['home_team']['home_team_id']==33)
next(x for x in a.selectbox if x.label=='Матч').set_value(game).run()
assert not a.exception,a.exception
assert next(x for x in a.selectbox if x.label=='Наша команда').value==33
assert any('data:image/png;base64,' in x.value for x in a.markdown), 'No local portraits in lineup'
for mode,total in [('Где забиваем','59'),('Где пропускаем','53')]:
    next(x for x in a.radio if x.label=='Вид поля').set_value(mode).run()
    assert not a.exception,a.exception
    next(x for x in a.selectbox if x.label=='Период карты голов').set_value('Весь сезон — послематчевый обзор').run()
    assert not a.exception,a.exception
    assert next(x for x in a.metric if x.label=='Голы').value==total
    assert any('Зоны голов на атакующей половине поля' in x.value for x in a.markdown)
next(x for x in a.selectbox if x.label=='Период карты голов').set_value('Текущий матч до выбранной минуты').run()
assert not a.exception,a.exception
assert next(x for x in a.metric if x.label=='Голы').value=='0'
next(x for x in a.button if x.label=='Финальный свисток').click().run()
assert not a.exception,a.exception
for mode in ['Где забиваем','Где пропускаем']:
    next(x for x in a.radio if x.label=='Вид поля').set_value(mode).run()
    assert not a.exception,a.exception
    assert next(x for x in a.selectbox if x.label=='Период карты голов').value=='Текущий матч до выбранной минуты'
    assert next(x for x in a.metric if x.label=='Голы').value=='2'
    assert not any('не совпало со счётом' in x.value for x in a.warning)
print('PASS: local portraits, Chelsea 59 scored / 53 conceded, zone and goalmouth maps, current-minute isolation')
