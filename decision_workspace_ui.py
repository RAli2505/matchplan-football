"""A single-match coaching workflow; manual choices are separate from observed events."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from decision_support import (POLICIES,compare_plans,build_package,package_changes,checklist_items,save_execution,load_execution)
from decision_history import load_index,find_similar,context_features,ROOT
from attack_chains import attack_chains,chain_diagram
from match_insights import territory,set_piece_summary,coach_report_html
from coaching import review_plan
from event_tactics import action_diagram
from player_insights import player_card,player_map


@st.cache_data(show_spinner=False)
def history_index(stamp,archive_stamp,report_stamp):
    return load_index()


def render_workspace(state,tid,goal,roles,profiles,game,teams,events,lineups,rules,pitch):
    mid=game['match_id']; prefix=f'workspace_{mid}_{tid}'
    st.markdown('<div id="coach-workspace"></div>',unsafe_allow_html=True)
    st.subheader('Пульт тренера: выбрать, согласовать, проверить')
    st.caption('Один матч и одна цель. Сравнение планов описывает экспертные варианты; отдельные вероятности победы после действий не вычислены.')
    comparisons=compare_plans(state,tid,goal,roles)
    for column,plan in zip(st.columns(3),comparisons):
        with column:
            st.markdown('#### '+plan['title'])
            st.write(plan['intent'])
            st.write('**Риск:** '+plan['risk'])
            for caution in plan['cautions']: st.warning(caution)
            st.caption(f'Оценка правил: {plan["expert_score"]:.1f}; это не вероятность успеха.')
    selected=st.radio('Какой план собрать',list(POLICIES),format_func=lambda key:POLICIES[key]['title'],
                      horizontal=True,key=prefix+'_policy')
    options=next(p for p in comparisons if p['key']==selected)['sub_options']
    sub_index=st.selectbox('Замена в пакете',[None,*range(len(options))],
        format_func=lambda i:'Без замены' if i is None else options[i]['out']+' → '+options[i]['in'],
        key=prefix+f'_sub_{selected}_{state["cutoff"]}')
    horizon=st.radio('На сколько минут собрать пакет',[5,10],horizontal=True,key=prefix+'_horizon')
    active_key=prefix+'_package'
    storage=load_execution(mid,tid)
    if active_key not in st.session_state and storage['decisions']:
        st.session_state[active_key]=list(storage['decisions'].values())[-1]['package']
    if st.button('Собрать единый пакет действий',disabled=all(p['finished'] for p in comparisons),key=prefix+'_build'):
        try:
            st.session_state[active_key]=build_package(state,tid,goal,roles,profiles,selected,sub_index,horizon)
        except ValueError as exc: st.error(str(exc))
    package=st.session_state.get(active_key)
    execution=None
    if package:
        st.markdown('### Ваш пакет: '+package['title'])
        st.caption('Создан: '+package['plan']['clock']+' · '+('цель — победить' if package['goal']=='win' else 'цель — не проиграть'))
        changes=package_changes(package,state,tid,goal)
        if changes: st.warning('Пакет требует пересмотра: '+' '.join(changes))
        a,b=st.columns(2,gap='large')
        with a:
            if package['formation']:
                st.write('**Расстановка:** '+package['formation']['formation'])
                st.markdown(pitch({p['id']:p for p in package['formation']['lineup']},state['yellow']),unsafe_allow_html=True)
                st.caption('Совместимость ролей и экспертная поправка +2 за соответствие плану. Это предложение, не выполненное изменение записи.')
            else: st.info('Полная расстановка на 11 игроков не предложена: сохранён фактический доступный состав.')
            if package['substitution']:
                sub=package['substitution']; st.write('**Кандидат на замену:** '+sub['out']+' → '+sub['in'])
                st.caption(sub['reason'])
        with b:
            st.write('**Основная задача:** '+package['task']['title'])
            for i,text in enumerate(package['task']['tasks'],1): st.write(f'{i}. {text}')
            st.markdown(action_diagram(package['task']['key']),unsafe_allow_html=True)
            st.caption('Учебная схема действия; номера — участники примера, не трекинг.')
            st.write('**Почему:** '+package['task']['why'])
            st.write('**Как проверить:** '+package['task']['check'])
        support=package['support']
        st.write('**Надёжность основания:** '+support['level'])
        st.caption(f'Окно {support["observed_seconds"]/60:.1f} мин · событий {support["events"]} · '
                   f'записанных примеров {support["direct_examples"]}. '+support['recheck'])
        with st.expander('Что известно и чего не хватает для решения'):
            for observation in support['observations']: st.write('• '+observation)
            for limitation in support['limits']: st.write('• '+limitation)
            if support['unknown_roles']: st.write('Неизвестные роли: '+', '.join(support['unknown_roles']))
        st.markdown('#### Контроль выполнения тренером')
        previous=storage['decisions'].get(package['id'],{})
        statuses={}
        for item in checklist_items(package):
            choices=['Не начато','Выполняется','Выполнено','Отменено']
            statuses[item['id']]=st.selectbox(item['text'],choices,index=choices.index(previous.get('statuses',{}).get(item['id'],'Не начато')),
                key=prefix+'_'+package['id']+'_'+item['id'])
        note=st.text_area('Заметка к выбранному решению',value=previous.get('note',''),key=prefix+'_'+package['id']+'_note')
        if st.button('Сохранить выполнение и заметку',key=prefix+'_save'):
            storage=save_execution(package,mid,tid,statuses,note)
            st.success('Отметки сохранены локально. Это ручная запись тренера.')
        execution={'statuses':statuses,'note':note}
        st.caption('Статусы не означают, что выбранный план действительно выполнялся в записи StatsBomb.')
        check=review_plan(package['plan'],events,lineups,state['cutoff'],rules)
        if check['ready']:
            st.write('**Что наблюдалось после точки решения**')
            if check.get('task_metrics'): st.dataframe(pd.DataFrame(check['task_metrics']),hide_index=True)
            st.write(f'Наших ударов: {check["ours"]["shots"]}; ударов соперника: {check["theirs"]["shots"]}.')
            if check['triggers']: st.warning('События для пересмотра: '+'; '.join(check['triggers']))
            st.caption('Изменение показателей исторического матча не измеряет причинный эффект выбранного пакета.')
        elif state['cutoff']>=package['plan']['origin']:
            st.caption('Для проверки отрезка продвиньте запись на '+str(check['remaining_seconds']//60)+' мин '+str(check['remaining_seconds']%60)+' сек.')
        st.download_button('Скачать пакет решений JSON',json.dumps({'package':package,'execution':execution},ensure_ascii=False,indent=2),
                           file_name=f'decision_{mid}_{package["id"]}.json',mime='application/json',key=prefix+'_json')
    st.download_button('Скачать автономный отчёт тренера HTML',coach_report_html(state,tid,teams,mid,package,execution),
                       file_name=f'matchplan_{mid}_{tid}.html',mime='text/html',key=prefix+'_html')

    st.markdown('### Похожие ситуации из прошлых матчей')
    st.caption('Только обучающие матчи, завершённые до даты текущего. Одинаковые разница счёта и численный баланс; '
               'близкие минута, недавний xG и входы в штрафную. Результат и действия тренера не используются для ранжирования.')
    history_key=prefix+f'_history_{state["cutoff"]}'
    if st.button('Найти похожие ситуации',key=prefix+'_history_search'):
        try:
            from core import ARCHIVE
            path=ROOT/'reports/decision_history.json'; report_path=ROOT/'reports/ml_results.json'
            if not path.exists(): raise ValueError('Индекс не построен: запустите python decision_history.py.')
            index=history_index(path.stat().st_mtime_ns,ARCHIVE.stat().st_mtime_ns,report_path.stat().st_mtime_ns)
            if (game['competition']['competition_id'],game['season']['season_id'])!=(index['manifest']['competition_id'],index['manifest']['season_id']):
                raise ValueError('Индекс доступен для АПЛ 2015/16; перенос на другой турнир не проверен.')
            st.session_state[history_key]=find_similar(index['rows'],context_features(state,tid),game['match_date'],mid)
        except (OSError,ValueError,KeyError) as exc: st.info(str(exc))
    if history_key in st.session_state:
        examples=st.session_state[history_key]
        if not examples: st.info('Достаточно близких более ранних матчей не найдено. До 10-й минуты поиск не выполняется.')
        else:
            st.dataframe(pd.DataFrame([{'Дата':r['date'],'Команда':r['team'],'Соперник':r['opponent'],'Момент':r['clock'],
                'Счёт тогда':r['score'],'Действия в следующие 10 минут':'; '.join(r['recorded_next_10_minutes']) or 'Замена или числовая смена схемы не записана',
                'Итог':r['final_score']+' · '+r['result'],'Расстояние':r['distance']} for r in examples]),hide_index=True)
            st.caption('Одна строка на матч. Расстояние — экспертная мера сходства, не вероятность. Другие команды и обстоятельства ограничивают перенос.')



def render_event_analysis(state,tid,prefix):
    """Detailed evidence, rendered only in the match-analysis tab."""
    st.markdown('### Цепочки атак: как команда дошла до удара')
    chain_side=st.radio('Чьи атаки разобрать',['Наши','Соперника'],horizontal=True,key=prefix+'_chain_side')
    chain_period=st.radio('Отрезок цепочек',['Последние 15 минут','Весь выбранный матч'],horizontal=True,key=prefix+'_chain_window')
    chains=attack_chains(state,tid,chain_side=='Соперника',900 if chain_period=='Последние 15 минут' else 0)
    if chains:
        chosen=st.selectbox('Выберите удар для разбора',range(len(chains)),
            format_func=lambda i:f'{chains[i]["time"]} · {chains[i]["shooter"]} · xG {chains[i]["xg"]:.2f}'+(' · гол' if chains[i]['goal'] else ''),
            key=prefix+f'_chain_{state["cutoff"]}_{chain_side}_{chain_period}')
        chain=chains[chosen]; a,b=st.columns(2)
        with a: st.markdown(chain_diagram(chain),unsafe_allow_html=True)
        with b:
            st.dataframe(pd.DataFrame([{'№':i+1,**{k:e[k] for k in ('Время','Игрок','Действие')}} for i,e in enumerate(chain['events'])]),hide_index=True)
            st.caption('До 12 записанных действий одного владения за последние 25 секунд до удара. Неизвестные перемещения не дорисовываются.')
            if not chain['possession_known']: st.info('Идентификатор владения отсутствует; показан только сам удар.')
            if chain['truncated']: st.caption('Более ранняя часть цепочки сокращена; показаны последние 12 действий.')
    else: st.info('К выбранной минуте на этом отрезке ударов нет.')

    st.markdown('### Индивидуальный разбор: проверить игрока перед решением')
    player_pool={pid:p['name'] for pid,p in {**state['bench'][tid],**state['players'][tid]}.items()}
    player_pool.update({e['player']['id']:e['player']['name'] for t,e in state['visible'] if t<=state['cutoff'] and e.get('team',{}).get('id')==tid and e.get('player')})
    if player_pool:
        player_id=st.selectbox('Игрок для индивидуального разбора',list(player_pool),format_func=player_pool.get,key=prefix+'_player')
        card=player_card(state,tid,player_id); c=card['counts']; a,b=st.columns(2)
        with a:
            st.dataframe(pd.DataFrame([
                {'Показатель':'Передачи: успешные / все','Значение':f'{c.get("passes_complete",0)} / {c.get("passes",0)}'},
                {'Показатель':'Под давлением: успешные / все','Значение':f'{c.get("pressured_complete",0)} / {c.get("pressured",0)}'},
                {'Показатель':'Продвижения пасом / ведением','Значение':f'{c.get("forward_passes",0)} / {c.get("forward_carries",0)}'},
                {'Показатель':'Передачи под удар','Значение':str(c.get('shot_assists',0))},
                {'Показатель':'Удары / голы','Значение':f'{c.get("shots",0)} / {c.get("goals",0)}'},
                {'Показатель':'xG игрока','Значение':f'{c.get("xg",0):.2f}'},
                {'Показатель':'Потери при отборе / контроле','Значение':str(c.get('recorded_losses',0))}
            ]),hide_index=True)
            if card['yellow']: st.warning('У игрока жёлтая карточка к выбранной минуте.')
            if not card['events']: st.info('Записанных действий к выбранной минуте нет. Это не оценка способности игрока.')
            st.caption('Продвижение здесь — успешный пас или ведение минимум на 10 единиц вперёд по оси поля. Усталость и физическая готовность не измеряются.')
        with b:
            st.markdown(player_map(card),unsafe_allow_html=True)
            st.caption('Точки — события, а не непрерывное расположение. Синие — действия с мячом/давление, красные — записанные потери.')
            with st.expander('Записанные действия выбранного игрока'):
                if card['events']: st.dataframe(pd.DataFrame(card['events']),hide_index=True)
    st.markdown('### Территория и стандартные положения')
    a,b=st.columns(2)
    with a:
        result=territory(state,tid)
        st.write('**Передачи в атакующей трети за 15 минут**')
        st.write(f'Мы: {result["ours"]}; соперник: {result["opponent"]}.')
        st.metric('Доля наших передач в атакующей трети','Нет наблюдений' if result['share'] is None else f'{result["share"]:.0%}')
        st.caption(result['definition'])
    with b:
        st.write('**Удары по типу атаки за текущий матч**')
        pieces=set_piece_summary(state,tid)
        if pieces: st.dataframe(pd.DataFrame(pieces),hide_index=True)
        else: st.caption('Ударов к выбранной минуте нет.')
        st.caption('Тип атаки берётся из разметки StatsBomb; это не доказательство эффективности выбранного розыгрыша.')
