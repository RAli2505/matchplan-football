"""Exercise real-date xT, both teams, windows and network filters in isolation."""
from streamlit.testing.v1 import AppTest

source='''
import streamlit as st
from core import matches,match_data,timeline,snapshot,competition_rules
from match_lab_ui import render_lab
games=matches(2,27)
game=st.selectbox('Тестовый матч',[games[0],games[-1]],format_func=lambda g:g['match_date'])
events,lineups=match_data(game['match_id'])
teams={x['team_id']:x['team_name'] for x in lineups}
cutoff=max(t for t,e in timeline(events))
state=snapshot(events,lineups,cutoff,competition_rules(2,27))
render_lab(state,next(iter(teams)),game,teams)
'''
a=AppTest.from_string(source,default_timeout=180).run()
def check(): assert not a.exception,[x.message for x in a.exception]
check()
assert any('ещё нет 20 более ранних' in x.value for x in a.info)
a.selectbox[0].select_index(1).run(); check()
assert any('266 матчей по 2016-02-27' in x.value for x in a.caption)
assert len(a.dataframe)>2
next(x for x in a.radio if x.label=='Команда для анализа связей').set_value('Соперник').run(); check()
next(x for x in a.radio if x.label=='Отрезок для связей и продвижения').set_value('Весь выбранный матч').run(); check()
next(x for x in a.slider if x.label=='Минимум передач для отображения связи').set_value(5).run(); check()
next(x for x in a.radio if x.label=='Длительность сравниваемых отрезков').set_value(5).run(); check()
assert any('xT зон' in x.value for x in a.markdown)
assert any('xT сумма' in list(x.value.columns) for x in a.dataframe)
print('PASS: early-date xT blocked, later-date train-only xT shown; both sides, full match, equal windows, network threshold, player values')
