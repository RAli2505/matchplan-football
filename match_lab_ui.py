"""Full-name, visible sections for the imported/adapted match analytics."""
import json
import pandas as pd
import streamlit as st
from core import clock_label
from event_adapter import possession_patterns
from expected_threat import ROOT,load_model,surface_for_date,rate_actions
from match_lab import (phase_comparison,phase_advice,network_analysis,network_diagram,
                       progression,arrows,xt_surface_diagram,xt_summary)


@st.cache_data(show_spinner=False)
def cached_xt(stamp,archive_stamp,split_stamp):
    return load_model()


def render_lab(state,tid,game,teams):
    prefix=f'lab_{game["match_id"]}_{tid}'
    from decision_workspace_ui import render_event_analysis
    render_event_analysis(state,tid,prefix)
    st.markdown('### Что изменилось в игре: два соседних отрезка')
    minutes=st.radio('Длительность сравниваемых отрезков',[5,10,15],index=1,horizontal=True,key=prefix+'_minutes')
    opponent=next(t for t in state['players'] if t!=tid)
    ours=phase_comparison(state,tid,minutes); theirs=phase_comparison(state,opponent,minutes)
    if ours['ready']:
        st.caption(f'{ours["period"]}-й тайм · сравниваются равные отрезки по {minutes} мин, границы без пересечения. Перерыв не включён.')
        a,b=st.columns(2)
        with a: st.write('**Мы**'); st.dataframe(pd.DataFrame(ours['rows']),hide_index=True)
        with b: st.write('**Соперник**'); st.dataframe(pd.DataFrame(theirs['rows']),hide_index=True)
        for tip in phase_advice(ours,theirs):
            st.write('**Сигнал:** '+tip['Наблюдение']); st.write('**Задача:** '+tip['Задача']); st.caption(tip['Проверка'])
        st.caption('Пороговые экспертные сигналы. События не доказывают смену указаний тренера.')
    else: st.info(ours['message'])

    st.markdown('### Связи и продвижение: через кого выходит мяч')
    scope=st.radio('Отрезок для связей и продвижения',['Последние 15 минут','Весь выбранный матч'],horizontal=True,key=prefix+'_scope')
    window=900 if scope.startswith('Последние') else 0
    side=st.radio('Команда для анализа связей',['Мы','Соперник'],horizontal=True,key=prefix+'_side')
    chosen=tid if side=='Мы' else opponent
    threshold=st.slider('Минимум передач для отображения связи',1,10,2,key=prefix+'_edge')
    net=network_analysis(state,chosen,window,threshold); moves=progression(state,chosen,window)
    a,b=st.columns(2)
    with a:
        st.markdown(network_diagram(net),unsafe_allow_html=True)
        st.caption('Номер на схеме соответствует строке таблицы. Центр точки — среднее место пасов и приёмов, размер — доля участий; это не расстановка. Направления связей — в таблице.')
        if net['nodes']:
            st.dataframe(pd.DataFrame([{'№':i+1,**{k:n[k] for k in ('Игрок','Отдал','Получил','Партнёров')},'Доля участий':f'{n["Доля участий"]:.1%}'} for i,n in enumerate(net['nodes'])]),hide_index=True)
            st.write('**Чаще других участвовал в успешных передачах:** '+net['nodes'][0]['Игрок'])
    with b:
        st.markdown(arrows(moves),unsafe_allow_html=True)
        st.write(f'**Успешных продвижений на ≥10 единиц поля:** {len(moves)}')
        st.caption('Пасы и ведения с реальными началами и концами. Движения без мяча не показаны. Порог — определение показателя, не качество решения.')
        counts={}
        for row in moves:
            name=row['event'].get('player',{}).get('name','?'); counts[name]=counts.get(name,0)+1
        if counts: st.dataframe(pd.DataFrame([{'Игрок':n,'Продвижений':c} for n,c in sorted(counts.items(),key=lambda x:-x[1])]),hide_index=True)
    with st.expander('Направления и число передач между игроками'):
        if net['edges']: st.dataframe(pd.DataFrame([{k:e[k] for k in ('От','Кому','Передач')} for e in net['edges']]),hide_index=True)
        else: st.info('Нет связей, достигших выбранного порога.')

    st.markdown('### Повторяющиеся эпизоды: от возврата мяча до удара')
    patterns=possession_patterns(state,chosen,window)
    if patterns:
        st.dataframe(pd.DataFrame([{'Возврат мяча':clock_label(p['recovery']),'Вернул':p['recovery'].get('player',{}).get('name','?'),
            'Передач':len(p['passes']),'До удара, сек':p['seconds'],'Бил':p['shot'].get('player',{}).get('name','?'),
            'xG удара':round(p['shot'].get('shot',{}).get('statsbomb_xg',0),3)} for p in patterns]),hide_index=True)
    else: st.info('На этом отрезке цепочка «возврат → успешный пас → удар» за 20 секунд не найдена.')
    st.caption('Только одно известное владение в одном тайме. Потеря, остановка или контроль соперника прерывают цепочку. Не все контратаки размечены как возврат мяча.')

    st.markdown('### xT: какие передачи и ведения увеличили угрозу')
    path=ROOT/'models/expected_threat.json'
    try:
        from core import ARCHIVE
        report=ROOT/'reports/ml_results.json'
        data=cached_xt(path.stat().st_mtime_ns,ARCHIVE.stat().st_mtime_ns,report.stat().st_mtime_ns) if path.exists() else None
        if data is None: st.info('Модель xT ещё не построена: python train_expected_threat.py.'); return
        if (game['competition']['competition_id'],game['season']['season_id'])!=(2,27):
            st.info('Модель xT обучена для АПЛ 2015/16. Перенос на другой турнир не проверен.'); return
        surface=surface_for_date(data,game['match_date'])
        if surface is None:
            st.info('Для даты этого матча ещё нет 20 более ранних обучающих матчей. Значения xT скрыты, чтобы не использовать будущее.'); return
        rows=rate_actions(state,chosen,surface,window)
        st.caption(f'Обучение: {surface["matches"]} матчей по {surface["through_date"]}, строго раньше выбранного матча. Только исходная обучающая часть 70%; валидация и тест не использованы.')
        a,b=st.columns(2)
        with a:
            st.markdown(xt_surface_diagram(surface),unsafe_allow_html=True)
            st.caption('Значения зон — оценка будущего гола в модели владения. xT действия = значение конечной зоны − начальной; это отдельная величина от xG удара.')
        with b:
            best=sorted([r for r in rows if r['xt']>0],key=lambda r:-r['xt'])[:12]
            st.markdown(arrows(best,'xt'),unsafe_allow_html=True)
            st.caption('До 12 продвижений с наибольшим положительным xT. Полная сумма включает и отрицательные изменения; неуспешные передачи не оцениваются как успешные.')
        summary=xt_summary(rows)
        if summary: st.dataframe(pd.DataFrame(summary),hide_index=True)
        st.caption('Адаптация xT socceraction (MIT), открытая игра, сетка 12×8. Частоты голов без сглаживания; малые выборки нестабильны. Это не VAEP и не доказательство пользы замены.')
        exports={'match_id':game['match_id'],'team_id':chosen,'cutoff':state['cutoff'],'window_seconds':window,
                 'phase_ours':ours,'phase_opponent':theirs,'network':net,'xt_training_through':surface['through_date'],
                 'xt_players':summary,'xt_actions':[{'time':clock_label(r['event']),'player':r['event'].get('player',{}).get('name','?'),
                    'start':r['start'],'end':r['end'],'xt':r['xt']} for r in rows]}
        st.download_button('Скачать расширенную аналитику JSON',json.dumps(exports,ensure_ascii=False,indent=2),file_name=f'analytics_{game["match_id"]}_{chosen}.json',mime='application/json',key=prefix+'_download')
    except (ValueError,OSError,KeyError) as exc: st.warning('xT недоступен: '+str(exc))
