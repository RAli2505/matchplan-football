from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from core import (ARCHIVE, PLANS, TEAM_ID, card, clock_label, decision_log, historical_roles,
                  historical_profiles, propose_lineup, match_data, matches, metrics, recommend, role_group, snapshot, timeline)
from tactics import formation_options, opponent_profile, tactical_details, scenario_state
from core import competition_rules
from coaching import tactical_options, freeze_plan, review_plan, formation_choice
from tactical_playbook import detailed_instructions
from field_views import portrait, pass_network, goal_map
from fifa_reference import compare_substitutions
from event_tactics import recent_changes, action_diagram
from deep_tactics import diagnose, diagnostic_map
from decision_workspace_ui import render_workspace
from match_lab_ui import render_lab
from goal_dashboard import season_records, records_from_events, select_records, zone_map, goalmouth, match_goal_map
from goal_pitch import vertical_goal_view

st.set_page_config(page_title='MatchPlan • тренерская доска', page_icon='⚽', layout='wide')
st.markdown('<style>' + (Path(__file__).parent / 'assets/matchplan.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def catalog(competition=2, season=27):
    return matches(competition, season)


@st.cache_data(show_spinner=False, max_entries=80)
def load(mid, preprocessing_version='2.0-validation'):
    return match_data(mid)


@st.cache_data(show_spinner='Собираю удары команды за сезон…')
def club_shots(competition, season, tid):
    return season_records(catalog(competition, season), tid)


@st.cache_data(show_spinner='Строю профили по предыдущим матчам…')
def prior_roles(date, competition, season, team_ids):
    earlier = [load(m['match_id'])[0] for m in catalog(competition, season) if m['match_date'] < date
               and (m['home_team']['home_team_id'] in team_ids or m['away_team']['away_team_id'] in team_ids)]
    recent_roles, recent_profiles = historical_roles(earlier), historical_profiles(earlier)
    past_path = Path(__file__).parent / 'reports' / 'history_profiles.json'
    if (competition, season) == (2, 27) and past_path.exists():
        past = json.loads(past_path.read_text(encoding='utf-8'))
        if past['latest_date'] < date:
            combined_roles = {int(pid): role for pid, role in past['roles'].items()}
            combined_roles.update(recent_roles)  # Prefer evidence from the newer season.
            combined_profiles = {int(pid): dict(values, historical_matches=values['matches'])
                                 for pid, values in past['profiles'].items()}
            for pid, values in recent_profiles.items():
                total = combined_profiles.setdefault(pid, {})
                for key, value in values.items():
                    total[key] = total.get(key, 0) + value
            recent_roles, recent_profiles = combined_roles, combined_profiles
    return recent_roles, recent_profiles, len(earlier), {tid: opponent_profile(earlier, tid) for tid in team_ids}


@st.cache_data(show_spinner=False)
def rank_formations(initial, tid, roles, profiles, unavailable, goal, opponent):
    return formation_options(initial, tid, roles, profiles, unavailable, goal, opponent)


@st.cache_data(show_spinner=False)
def ml_report(stamp):
    path = Path(__file__).parent / 'reports' / 'ml_results.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def probability_view(probabilities):
    for col, title, probability in zip(st.columns(3), ['Победа', 'Ничья', 'Поражение'],
                                     [probabilities[2], probabilities[1], probabilities[0]]):
        col.metric(title, f'{probability:.1%}')


def esc(value):
    return html.escape(str(value))


def position_label(value):
    return {'Goalkeeper':'вратарь', 'Right Back':'правый защитник', 'Left Back':'левый защитник',
            'Right Center Back':'правый центральный защитник', 'Center Back':'центральный защитник',
            'Left Center Back':'левый центральный защитник', 'Right Wing Back':'правый латераль',
            'Left Wing Back':'левый латераль', 'Right Defensive Midfield':'правый опорный полузащитник',
            'Center Defensive Midfield':'опорный полузащитник', 'Left Defensive Midfield':'левый опорный полузащитник',
            'Right Midfield':'правый полузащитник', 'Left Midfield':'левый полузащитник',
            'Right Center Midfield':'правый центральный полузащитник', 'Center Midfield':'центральный полузащитник',
            'Left Center Midfield':'левый центральный полузащитник', 'Right Wing':'правый вингер',
            'Left Wing':'левый вингер', 'Right Attacking Midfield':'правый атакующий полузащитник',
            'Center Attacking Midfield':'атакующий полузащитник', 'Left Attacking Midfield':'левый атакующий полузащитник',
            'Right Center Forward':'правый нападающий', 'Center Forward':'центральный нападающий',
            'Left Center Forward':'левый нападающий', 'Secondary Striker':'оттянутый нападающий'}.get(value,value)


def pitch(players, yellow):
    # Nominal role locations, not tracking positions.
    coordinates = {
        1: (50, 90), 2: (86, 72), 3: (70, 76), 4: (50, 76), 5: (30, 76), 6: (14, 72),
        7: (90, 56), 8: (10, 56), 9: (68, 59), 10: (50, 60), 11: (32, 59),
        12: (87, 43), 13: (68, 45), 14: (50, 45), 15: (32, 45), 16: (13, 43),
        17: (88, 25), 18: (68, 29), 19: (50, 28), 20: (32, 29), 21: (12, 25),
        22: (68, 13), 23: (50, 13), 24: (32, 13), 25: (50, 22)}
    names = ['Goalkeeper', 'Right Back', 'Right Center Back', 'Center Back', 'Left Center Back', 'Left Back',
             'Right Wing Back', 'Left Wing Back', 'Right Defensive Midfield', 'Center Defensive Midfield',
             'Left Defensive Midfield', 'Right Midfield', 'Right Center Midfield', 'Center Midfield',
             'Left Center Midfield', 'Left Midfield', 'Right Wing', 'Right Attacking Midfield',
             'Center Attacking Midfield', 'Left Attacking Midfield', 'Left Wing', 'Right Center Forward',
             'Center Forward', 'Left Center Forward', 'Secondary Striker']
    pos = {name: coordinates[i + 1] for i, name in enumerate(names)}
    dots = []
    for i, p in enumerate(players.values()):
        x, y = pos.get(p['position'], (15 + i % 4 * 23, 40 + i // 4 * 15))
        x, y = x * 5, y * 5
        name = p['name'].split()[-1]
        dots.append(f'<circle cx="{x}" cy="{y}" r="15" fill="#f4f7fb" stroke="#172d48" stroke-width="2"/>'
                    f'<text x="{x}" y="{y+5}" text-anchor="middle" fill="#172d48" font-size="13" font-weight="bold">{esc(p["number"])}</text>'
                    f'<text x="{x}" y="{y+30}" text-anchor="middle" fill="white" font-size="12">{esc(name)}</text>')
        if p['id'] in yellow:
            dots.append(f'<rect x="{x+13}" y="{y-16}" width="8" height="12" fill="#ffcf55"/>')
        photo = portrait(p['id'])
        if photo:
            dots.append(f'<circle cx="{x}" cy="{y-6}" r="23" fill="#eaf0f5"/>'
                        f'<image href="{photo}" x="{x-24}" y="{y-31}" width="48" height="48"/>'
                        f'<text x="{x+23}" y="{y+17}" text-anchor="middle" fill="white" font-size="12">{esc(p["number"])}</text>')
    return ('<svg role="img" aria-label="Состав по номинальным позициям" viewBox="0 0 500 520" width="100%" xmlns="http://www.w3.org/2000/svg">'
            '<rect width="500" height="520" rx="12" fill="#247567"/>'
            '<path d="M20 20H480V500H20ZM20 260H480 M130 20V100H370V20 M130 500V420H370V500" fill="none" stroke="#a6c8b9" stroke-width="2"/>'
            '<circle cx="250" cy="260" r="58" fill="none" stroke="#a6c8b9" stroke-width="2"/>' + ''.join(dots) + '</svg>')


st.title('MatchPlan')
st.write('Выберите матч и цель слева. Ниже — рекомендуемые действия и их причины.')
if not ARCHIVE.exists():
    st.error(f'Не найден архив: {ARCHIVE}. Поместите open-data-master.zip рядом с папкой MatchPlan.')
    st.stop()

with st.sidebar:
    dataset_name = st.selectbox('Турнир и сезон', ['Premier League 2015/16 · 380 матчей', 'Байер 2023/24 · 34 матча'])
    competition, season = (2, 27) if dataset_name.startswith('Premier') else (9, 281)
try:
    games = catalog(competition, season)
except (ValueError, OSError) as exc:
    st.error(f'Не удалось прочитать датасет: {exc}')
    st.stop()

with st.sidebar:
    st.header('Подготовка к матчу')
    game = st.selectbox('Матч', games, key=f'match_{competition}_{season}', format_func=lambda m:
        f'{m["match_date"]} | {m["home_team"]["home_team_name"]} — {m["away_team"]["away_team_name"]}')
    teams = {game['home_team']['home_team_id']: game['home_team']['home_team_name'],
             game['away_team']['away_team_id']: game['away_team']['away_team_name']}
    tid = st.selectbox('Наша команда', list(teams), index=list(teams).index(TEAM_ID) if TEAM_ID in teams else 0,
                       format_func=teams.get, key=f'team_{game["match_id"]}')
    target = st.radio('Цель на матч', ['Победить', 'Не проиграть'])
    goal = 'win' if target == 'Победить' else 'draw'
    st.caption('«Не проиграть» включает победу и ничью. Цель оценивается за основное время.')
    st.divider()
    st.caption('StatsBomb Open Data · ' + dataset_name + '\n\nИсторическое воспроизведение; подключения к прямому эфиру нет.')

try:
    events, lineups = load(game['match_id'])
except (ValueError, KeyError, OSError) as exc:
    st.error(f'Проверка данных матча не пройдена: {exc}. Проверьте архив и отчёт обработки данных.')
    st.stop()
timed = timeline(events)
roles, profiles, previous_count, team_history = prior_roles(game['match_date'], competition, season, tuple(teams))
rules = competition_rules(competition, season)
initial = snapshot(events, lineups, 0, rules=rules)
squad = {**initial['players'][tid], **initial['bench'][tid]}
with st.sidebar:
    unavailable = st.multiselect('Кто не может играть', list(squad),
                                 format_func=lambda pid: squad[pid]['name'], key=f'unavailable_{game["match_id"]}_{tid}')
    st.caption('Исключения влияют на предложенные стартовые 11. Историческая запись остаётся фактической.')
max_tick = int(max(t for t, _ in timed)) + 1
mid = game['match_id']
slider_key = f'time_{mid}'
if slider_key not in st.session_state:
    st.session_state[slider_key] = 0


def jump(value):
    st.session_state[slider_key] = min(max_tick, max(0, value))


with st.container():
    controls = st.columns([1, 1, 1, 1, 2])
    controls[0].button('До матча', on_click=jump, args=(0,), width='stretch')
    half = next((int(t) for t, e in timed if e['period'] == 2), max_tick)
    controls[1].button('2-й тайм', on_click=jump, args=(half,), width='stretch')
    controls[2].button('+5 минут', on_click=jump, args=(st.session_state[slider_key] + 300,), width='stretch')
    controls[3].button('Финальный свисток', on_click=jump, args=(max_tick,), width='stretch')
    important = [(t, e) for t, e in timed if e['type']['name'] in ('Substitution', 'Own Goal Against') or
                 e['type']['name'] == 'Shot' and e.get('shot', {}).get('outcome', {}).get('name') == 'Goal' or card(e) in ('Red Card', 'Second Yellow')]
    with controls[4]:
        selected_event = st.selectbox('Перейти к событию', [None] + list(range(len(important))),
            format_func=lambda i: 'Выберите событие' if i is None else
            f'{clock_label(important[i][1])} | {important[i][1]["type"]["name"]}', label_visibility='collapsed')
        if st.button('Показать событие', disabled=selected_event is None, width='stretch'):
            jump(int(important[selected_event][0]) + 1)
            st.rerun()
    cutoff = st.slider('Выберите момент матча', 0, max_tick, key=slider_key,
                       help='Шкала хранит секунды записи с добавленным временем. Игровое время показано под счётом; для перехода используйте кнопки выше.')

state = snapshot(events, lineups, cutoff, rules=rules)
opp = next(k for k in teams if k != tid)
rec = recommend(state, tid, goal, roles)
log = decision_log(events, lineups, cutoff, tid, goal, roles, rules=rules)
effective = log[-1]['key'] if log and not rec['finished'] else rec['plan']
if effective != rec['plan']:
    # Keep every action and substitution consistent with the retained plan.
    rec = recommend(state, tid, goal, roles, plan_override=effective)
    rec['held'] = True
st.markdown(f'<div class="scoreboard"><div class="team">{esc(teams[tid])}</div>'
            f'<div class="score">{state["goals"][tid]} : {state["goals"][opp]}</div>'
            f'<div class="team right">{esc(teams[opp])}</div></div>', unsafe_allow_html=True)
st.caption(('До начала матча' if cutoff == 0 else clock_label(state['last'])) + f' · Цель: {target.lower()}')
if not rec['finished']:
    st.markdown(f'<div class="decision"><h2>Сейчас: {esc(PLANS[effective].lower())} план</h2>'
                f'<p>{esc(rec["objective"])}</p></div>', unsafe_allow_html=True)
    if cutoff == 0:
        st.info('До начала матча: выберите стартовых игроков во вкладке «Состав и подготовка». Чтобы посмотреть события игры, выберите минуту или нажмите «2-й тайм».')

board, prematch, scenario, comparison, journal, match_lab, analytics, method = st.tabs(
    ['Решение сейчас', 'Состав и подготовка', 'Проверить сценарий', 'Сравнить цели', 'Журнал и отчёт', 'Разбор игры и продвижения', 'Прогноз и метрики', 'О данных'])

with match_lab:
    st.subheader('Разбор игры и продвижения')
    st.write('Здесь — подробные основания для решения: цепочки атак, индивидуальные показатели, изменения игры, сеть передач и xT. Выбрать план и отметить выполнение можно во вкладке «Решение сейчас».')
    render_lab(state,tid,game,teams)
with prematch:
    st.subheader('Предложенные стартовые 11')
    st.write('Сравниваем схемы и находим лучшее назначение доступных игроков на роли для каждой схемы. '
             'Приоритет — совместимость роли и история участия; цель и профиль соперника дают прозрачные небольшие поправки.')
    ranked = rank_formations(initial, tid, roles, profiles, tuple(unavailable), goal, team_history[opp])
    best = ranked[0]
    st.success(f'Предлагаемая схема: {best["formation"]}. '
               + ('Все роли заполнены.' if best['gaps'] == 0 else f'Не подтверждено ролей: {best["gaps"]}.'))
    with st.expander('Сравнить схемы и посмотреть оценки'):
        st.dataframe(pd.DataFrame([{'Схема': x['formation'], 'Не хватает игроков': x['gaps'], 'Совместимость': x['fit'],
                                   'Оценка варианта': x['score']} for x in ranked]), hide_index=True, width='stretch')
    selected_formation = st.selectbox('Схема для просмотра', list(range(len(ranked))),
                                     format_func=lambda i: ranked[i]['formation'], key=f'formation_{mid}_{tid}_{goal}')
    option = ranked[selected_formation]
    proposed = option['lineup']
    st.caption(option['rationale'] + ' Баллы не являются вероятностями. Рекомендуется первый вариант с минимумом пробелов.')
    a, b = st.columns([1, 1.25], gap='large')
    with a:
        st.markdown(pitch({p['id']: p for p in proposed}, set()), unsafe_allow_html=True)
    with b:
        profile_rows = []
        for player in proposed:
            history = profiles.get(player['id'], {})
            appearances = history.get('matches', 0)
            profile_rows.append({'Игрок': player['name'], 'Роль': player['position'],
                'Предыдущие матчи': appearances, 'Старты': history.get('starts', 0),
                'Из прошлых сезонов': history.get('historical_matches', 0),
                'Удары / матч': round(history.get('shots', 0) / appearances, 2) if appearances else None,
                'Продвигающие передачи / матч': round(history.get('progressive_passes', 0) / appearances, 2) if appearances else None,
                'Основание выбора': player['evidence']})
        st.dataframe(pd.DataFrame(profile_rows),
                     hide_index=True, width='stretch')
        st.caption('Игровые показатели рассчитаны только по матчам до выбранной даты и описывают прошлую активность, а не общий уровень игрока.')
        if any(p['id'] < 0 for p in proposed):
            st.warning('Полный состав не подтверждён: для части ролей недостаточно доступных игроков или истории. Требуется решение тренера.')
        if previous_count == 0:
            st.info('В текущем сезоне ещё нет предыдущих матчей этих команд. Для части игроков может быть доступна '
                    'история прошлых сезонов; остальные назначения опираются на подтверждённые стартовые роли.')
        st.caption('Назначение игроков для каждой схемы оптимизируется динамическим программированием. '
                   'Оптимум относится к заданным оценкам совместимости, а не к результату матча.')
        pre = recommend(initial, tid, goal, roles)
        st.write('**План на начало:** ' + PLANS[pre['plan']])
        st.write(pre['attack'])
        st.write(pre['defense'])
        opponent_data = team_history[opp]
        st.write(f'**Соперник: {teams[opp]}** — доступно {opponent_data["matches"]} предыдущих матчей (последние пять в наборе).')
        if opponent_data['matches']:
            st.write(f'Средний xG: {opponent_data["xg_per_match"]:.2f}; допущенный: {opponent_data["xg_against_per_match"]:.2f}.')
        else:
            st.info('Предыдущих наблюдений соперника нет: уверенный исторический профиль построить нельзя.')
with board:
    st.caption('Здесь — выбор и выполнение действий. Подробная сеть передач, цепочки атак, карточки игроков и xT находятся во вкладке «Разбор игры и продвижения».')
    st.markdown('**Перейти к разделу:** [Пульт тренера](#coach-workspace) · [Тактика](#tactical-plan) · [Схема действий](#action-scheme) · '
                '[Задачи игрокам](#player-tasks) · [Расстановка](#team-formation)')
    left, right = st.columns([1.3, 1], gap='large')
    with left:
        formation = state['formation'].get(tid, '?')
        st.subheader('Поле и события')
        field_mode = st.radio('Вид поля', ['Состав', 'Где забиваем', 'Где пропускаем'],
                              horizontal=True, key=f'field_view_{mid}_{tid}')
        if field_mode == 'Состав':
            st.write(f'**Текущая схема: {"–".join(formation)}**')
            st.markdown(pitch(state['players'][tid], state['yellow']), unsafe_allow_html=True)
            photo_count = sum(bool(portrait(pid)) for pid in state['players'][tid])
            st.caption(f'Фото: {photo_count}/{len(state["players"][tid])} игроков · EA / TheSportsDB. '
                       'Фото служат оформлением; могут отличаться от формы сезона 2015/16. Роли — из событий матча.')
            with st.expander('Карточки футболистов с фотографиями'):
                photo_columns = st.columns(3)
                for index, player in enumerate(state['players'][tid].values()):
                    with photo_columns[index % 3]:
                        face = portrait(player['id'])
                        if face:
                            st.image(face, width=90)
                        st.write(f'{player["number"]}. {player["name"]}')
                        if not face:
                            st.caption('Подтверждённого фото нет')
        else:
            conceded = field_mode == 'Где пропускаем'
            st.subheader('Голы соперника в наши ворота' if conceded else 'Наши голы в ворота соперника')
            scope = st.selectbox('Период карты голов', ['Текущий матч до выбранной минуты',
                'Весь сезон — послематчевый обзор', 'Предыдущие 5 матчей'], key=f'goal_scope_v3_{mid}_{tid}')
            if scope == 'Текущий матч до выбранной минуты':
                shot_records = records_from_events([e for _, e in state['visible']], mid, game['match_date'])
                st.write(f'**{teams[tid]} {state["goals"][tid]} : {state["goals"][opp]} {teams[opp]}**')
                st.caption('Текущий матч · ' + ('до начала матча' if cutoff == 0 else clock_label(state['last']))
                           + '. Более поздние события скрыты.')
            else:
                shot_records = club_shots(competition, season, tid)
                if scope == 'Предыдущие 5 матчей':
                    older = [g for g in catalog(competition, season) if g['match_date'] < game['match_date']
                        and tid in (g['home_team']['home_team_id'], g['away_team']['away_team_id'])][-5:]
                    older_ids = {g['match_id'] for g in older}
                    shot_records = [r for r in shot_records if r['match_id'] in older_ids]
                    st.caption(f'До даты выбранного матча: {len(older)} завершённых матчей.')
                else:
                    st.info('Обзор всего завершённого сезона, включая матчи после выбранной даты. '
                            'Используется только для этой карты и не передаётся в прогноз или рекомендации.')
            play_filter = 'Все ситуации' if scope == 'Текущий матч до выбранной минуты' else st.selectbox(
                'Ситуации для карты', ['Все ситуации', 'Открытая игра', 'Стандарты и пенальти'], key=f'goal_play_{mid}_{tid}')
            selected_shots = select_records(shot_records, tid, conceded, play_filter)
            actual_shots = [r for r in selected_shots if not r['own_goal']]
            n_goals = sum(r['goal'] for r in actual_shots)
            own_goals = sum(r['own_goal'] for r in selected_shots)
            goal_stats = st.columns(3)
            goal_stats[0].metric('Голы', n_goals+own_goals)
            goal_stats[1].metric('Удары', len(actual_shots))
            goal_stats[2].metric('xG этого матча' if scope == 'Текущий матч до выбранной минуты' else 'xG за выбранный период',
                                 f'{sum(r["xg"] for r in actual_shots):.2f}')
            show_all = st.checkbox('Показать также остальные удары', key=f'goal_all_v2_{mid}_{tid}')
            map_display = st.radio('Что показать на карте', ['Зоны и xG', 'Удары', 'Голы и события'], horizontal=True,
                                  key=f'goal_display_{mid}_{tid}')
            is_current = scope == 'Текущий матч до выбранной минуты'
            drawing, zone_rows = vertical_goal_view(selected_shots, conceded, 'zones')
            if map_display == 'Зоны и xG':
                st.markdown(drawing, unsafe_allow_html=True)
                st.write('**Крупное число — xG ударов в зоне за этот матч до выбранной минуты.**' if is_current
                         else '**Крупное число — суммарный xG ударов в зоне за выбранный период.**')
                st.caption('Ниже указаны голы и удары. Более яркая зона — больше xG в выбранном периоде. '
                           'Гол может быть забит при низком xG; автоголы собственного xG не имеют.')
                outside = [row for row in zone_rows if row['Зона'] in ('Со своей половины', 'Без координат') and row['Удары']]
                if outside:
                    st.caption('Не показаны на половине поля: ' + '; '.join(
                        f'{row["Зона"]}: {row["Удары"]} уд., xG {row["xG"]:.2f}' for row in outside))
            elif map_display == 'Удары':
                shot_drawing, _ = vertical_goal_view(selected_shots, conceded, 'shots')
                st.markdown(shot_drawing, unsafe_allow_html=True)
                st.write('**Заполненный круг — гол · Контур — другой удар · Ромб — автогол**')
                st.caption('Размер круга отражает xG. Наведите на точку для имени, минуты и значения. '
                           + ('Наши ворота внизу.' if conceded else 'Ворота соперника вверху.')
                           + ' Правая сторона картинки — наш правый фланг. Дальние удары со своей половины не показаны.')
            elif is_current:
                drawing, current_goals, missing_locations = match_goal_map(selected_shots, tid, conceded, show_all, teams[tid], teams[opp])
                drawing, _ = vertical_goal_view(selected_shots, conceded, 'goals', show_all)
                st.markdown(drawing, unsafe_allow_html=True)
                st.write('**Круг — гол с удара · Ромб — автогол**')
                st.caption('Номера на поле соответствуют строкам таблицы. Ворота соперника вверху, наши — внизу; наш правый фланг справа.')
                with st.expander('Как читать карту'):
                    st.write('Вертикальная половина поля: наши удары направлены вверх, удары соперника — вниз. '
                             'Для удобства оба тайма приведены к одной ориентации. Точка показывает место удара, '
                             'ромб — место события автогола после преобразования координат. Полёт мяча не восстанавливается.')
                if current_goals:
                    st.dataframe(pd.DataFrame(current_goals), hide_index=True)
                else:
                    st.info('Соперник ещё не забил к выбранной минуте.' if conceded else 'Наша команда ещё не забила к выбранной минуте.')
                if missing_locations:
                    st.info(f'Голов без координат: {missing_locations}. Они учтены в числе голов и таблице, но точка на поле не придумана.')
                expected_goals = state['goals'][opp if conceded else tid]
                if n_goals + own_goals != expected_goals:
                    st.warning('Число голов на карте не совпало со счётом. Требуется проверка событий этого матча.')
            else:
                event_map, event_rows, event_missing = match_goal_map(selected_shots, tid, conceded, show_all, teams[tid], teams[opp])
                event_map, _ = vertical_goal_view(selected_shots, conceded, 'goals', show_all)
                st.markdown(event_map, unsafe_allow_html=True)
                st.caption('Круг — результативный удар, ромб — автогол. Ворота соперника вверху, наши внизу. Номера связаны с таблицей событий.')
                with st.expander('События на карте'):
                    if event_rows:
                        st.dataframe(pd.DataFrame(event_rows), hide_index=True)
                    if event_missing:
                        st.caption(f'Голов без координат: {event_missing}; точка на поле не отображается.')
            with st.expander('Куда забиты голы в створ ворот'):
                mouth, mapped = goalmouth(selected_shots)
                st.markdown(mouth, unsafe_allow_html=True)
                st.caption(f'Голов с известной трёхмерной конечной координатой: {mapped} из {n_goals}. Вид со стороны бьющего.')
            with st.expander('Цифры по зонам и авторы голов'):
                st.dataframe(pd.DataFrame(zone_rows), hide_index=True)
                scorers = [{'Дата': r['date'], 'Игрок': r['player'], 'Минута': r['minute'], 'xG': round(r['xg'],3)}
                           for r in actual_shots if r['goal']]
                if scorers:
                    st.dataframe(pd.DataFrame(scorers), hide_index=True)
            if not actual_shots:
                st.info('В выбранном периоде нет ударов. Выберите обзор сезона или другой период.')
            if own_goals:
                st.caption(f'Автоголы: {own_goals}. '
                           + ('На поле обозначены ромбом, если есть координаты.' if scope == 'Текущий матч до выбранной минуты'
                              else 'Включены в число голов, но не в карту результативных ударов.'))
        with st.expander(f'Доступные запасные: {len(state["bench"][tid])}'):
            rows = [{'Игрок': p['name'], '№': p['number'], 'Роль по прошлым матчам': roles.get(pid, 'Недостаточно данных')}
                    for pid, p in state['bench'][tid].items()]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        windows_label = f' · игровые окна: {len(state["windows"][tid])}/{rules["window_limit"]}' if rules['window_limit'] is not None else ''
        st.caption(f'Замены: {state["subs"][tid]}/{rules["sub_limit"]}{windows_label} · удаления: {state["red"][tid]}')
    with right:
        if rec['finished']:
            st.success('Матч завершён. Доступен разбор принятых рекомендаций.')
        else:
            st.subheader('Что сделать сейчас')
            for index, action in enumerate(rec['actions'], 1):
                st.write(f'**{index}.** {action}')
            st.write('**Почему это предлагается**')
            for reason in rec['evidence']:
                st.write('• ' + reason)
            st.info('**Компромисс:** ' + rec['risk'])
            details = tactical_details(state, tid, effective, team_history[opp])
            with st.expander('Подробные наблюдения за соперником'):
                for action in details['actions']:
                    st.write('• ' + action)
            with st.expander('Другой вариант и условия пересмотра'):
                st.write(f'Ближайший вариант: **{PLANS[rec["alternative"]]}**. {rec["recommendation_strength"]}.')
                st.caption('Перевес означает разницу экспертных оценок. Это не вероятность успеха.')
                st.write(rec['review'])
                st.write('Темп: ' + details['tempo'])
            if rec.get('held'):
                st.caption('Сработал порог переключения: изменение оценки слишком мало для перестройки.')
            if rec['sub']:
                st.write('**Варианты замены — выберите один**')
                st.caption('Это альтернативы одной замене. Игроки могут повторяться между вариантами.')
                for i, sub in enumerate(rec['sub_options'], 1):
                    with st.expander(f'{i}. {sub["out"]} → {sub["in"]}', expanded=i == 1):
                        st.write(sub['reason'])
                        history = profiles.get(sub['in_id'], {})
                        st.write(f'История запасного до матча: {history.get("matches", 0)} матчей, '
                                 f'{history.get("starts", 0)} стартов. Подтверждённая роль: {sub["position"]}.')
                        st.caption('Точная позиция совпадает.' if sub['exact_role'] else
                                   'Риск: совпадает только группа ролей; нужна корректировка позиции.')
                with st.expander('Дополнить сравнение оценками FIFA 16'):
                    st.caption('Дополнительный игровой справочник: позиции, рабочая нога и оценки симулятора. '
                               'Это не реальная форма или усталость. Дата снимка CSV не подтверждена, '
                               'поэтому эти оценки не участвуют в основном историческом прогнозе и выборе замен.')
                    st.dataframe(pd.DataFrame(compare_substitutions(rec['sub_options'], effective)), hide_index=True)
                    st.caption('Экспертные веса индекса: атака — удар 35%, пас 25%, дриблинг 20%, скорость 20%; '
                               'баланс — пас 35%, защита 25%, дриблинг 20%, физика 20%; '
                               'осторожный — защита 50%, физика 30%, пас 20%. '
                               'Более высокий индекс — повод проверить вариант, а не доказательство лучшего результата.')
            elif not rec['subs_allowed']:
                st.write('Лимит замен или игровых окон исчерпан.')
            else:
                st.caption('Конкретная замена не подтверждена: нет подходящей роли по прошлым матчам или ещё рано для плановой замены.')
        st.subheader('Последние 15 минут')
        ours, theirs = metrics(state, tid), metrics(state, opp)
        st.dataframe(pd.DataFrame([
            {'Показатель':'Качество моментов (xG)', 'Мы':f'{ours["xg"]:.2f}', 'Соперник':f'{theirs["xg"]:.2f}'},
            {'Показатель':'Удары', 'Мы':str(ours['shots']), 'Соперник':str(theirs['shots'])},
            {'Показатель':'Входы в штрафную', 'Мы':str(ours['box_entries']), 'Соперник':str(theirs['box_entries'])}
        ]), hide_index=True, width='stretch')
        with st.expander('Что означает xG'):
            st.write('xG описывает качество уже выполненных ударов, а не шанс победы. '
                     'Сравниваются последние 15 минут; в начале матча доступный отрезок короче.')

    render_workspace(state,tid,goal,roles,profiles,game,teams,events,lineups,rules,pitch)
    st.subheader('Что показали события: основания для тактики')
    st.caption('Один выбранный матч, последние 15 минут до выбранного момента. Данные остальных матчей сюда не подмешиваются.')
    diagnosis_ours, diagnosis_theirs = diagnose(state, tid), diagnose(state, opp)
    diag_table, diag_map = st.columns(2, gap='large')
    with diag_table:
        dc, oc = diagnosis_ours['counts'], diagnosis_theirs['counts']
        def fraction(values, success, total):
            return f'{values.get(success,0)} из {values.get(total,0)}'
        st.dataframe(pd.DataFrame([
            {'Эпизод':'Пасы под давлением', 'Мы':fraction(dc,'pressured_complete','pressured_passes'),
             'Соперник':fraction(oc,'pressured_complete','pressured_passes')},
            {'Эпизод':'Неудачные обводки','Мы':fraction(dc,'dribbles_failed','dribbles'),
             'Соперник':fraction(oc,'dribbles_failed','dribbles')},
            {'Эпизод':'Пасы назад от лицевой','Мы':fraction(dc,'cutbacks_complete','cutbacks'),
             'Соперник':fraction(oc,'cutbacks_complete','cutbacks')},
            {'Эпизод':'Разрезающие передачи','Мы':fraction(dc,'through_complete','through_balls'),
             'Соперник':fraction(oc,'through_complete','through_balls')},
            {'Эпизод':'Удары соперника после потерь','Мы':str(dc.get('shots_after_loss',0)),
             'Соперник':str(oc.get('shots_after_loss',0))}
        ]), hide_index=True, width='stretch')
        st.caption('Для передач: успешные из всех. Для обводок: неудачные из всех. '
                   'Последняя строка — удары другой команды после потерь указанной команды.')
        st.write('**Кто создаёт удары у соперника**')
        if diagnosis_theirs['creators']:
            st.dataframe(pd.DataFrame(diagnosis_theirs['creators']), hide_index=True, width='stretch')
        else:
            st.caption('За этот отрезок нет подтверждённых связей «передача → удар».')
        with st.expander('Потери и последовавшие удары соперника'):
            if diagnosis_ours['episodes']:
                st.dataframe(pd.DataFrame(diagnosis_ours['episodes']), hide_index=True)
            else:
                st.write('Подходящих последовательностей не зарегистрировано.')
            st.caption('Удар в течение 12 секунд после потери — наблюдаемая последовательность, а не доказанная причина. '
                       'Эпизод прерывается при остановке игры или подтверждённом возврате нашего контроля.')
    with diag_map:
        diagnostic_side = st.radio('Чьи эпизоды показать', ['Наши','Соперника'], horizontal=True, key=f'diag_side_{mid}_{tid}')
        category = st.selectbox('Тип эпизодов', ['Передачи под давлением','Обводки','Пасы назад от лицевой',
            'Разрезающие передачи','Передачи под удар'], key=f'diag_type_{mid}_{tid}')
        prefixes={'Передачи под давлением':'Передача под', 'Обводки':'Обводка:',
                  'Пасы назад от лицевой':'Пас назад', 'Разрезающие передачи':'Разрезающая', 'Передачи под удар':'Передача с подтверждённым'}
        diagnostic_report = diagnosis_ours if diagnostic_side == 'Наши' else diagnosis_theirs
        st.markdown(diagnostic_map(diagnostic_report, diagnostic_side=='Соперника', prefixes[category]), unsafe_allow_html=True)
        st.caption('Точки — места записанных событий. Мы атакуем вправо, соперник — влево. '
                   'Отсутствие отметки давления не доказывает, что давления не было.')
    st.markdown('<div id="tactical-plan"></div>', unsafe_allow_html=True)
    st.subheader('1. Тактика и план на следующие 5–10 минут')
    st.caption('Три подхода задают общий риск. Ниже — конкретные задачи внутри этого подхода. '
               'Они основаны на экспертных правилах и наблюдаемых событиях.')
    options = tactical_options(state, tid, goal)
    with st.expander('Сигналы StatsBomb и приоритет задач'):
        signal_rows = [{'Задача': o['title'], 'Условия выполнены': 'да' if o['available'] else 'нет',
                        'Основание': o['why']} for o in options]
        st.dataframe(pd.DataFrame(signal_rows), hide_index=True)
        st.caption('Приоритет новых задач задаётся экспертными правилами. Это не вероятность успеха и не результат обучения модели.')
    with st.expander('Что изменилось за последние 5 минут'):
        changes = recent_changes(state, tid)
        if changes:
            st.dataframe(pd.DataFrame(changes), hide_index=True)
            st.caption('Два соседних непересекающихся отрезка по 5 игровых минут. Изменение счётчиков не доказывает эффект тактики.')
        else:
            st.info('Для сравнения нужно не менее 10 минут записи.')
    default = next((i for key in ('flank', 'transition', 'width', 'control', 'center')
                    for i, o in enumerate(options) if o['key'] == key and o['available']), 0)
    triggered = [(i, o) for i, o in enumerate(options) if o['available'] and o.get('priority', 0) >= 60]
    if triggered:
        default = max(triggered, key=lambda item: item[1]['priority'])[0]
    selected_tactic = st.selectbox('Тактическая задача', range(len(options)), index=default,
        format_func=lambda i: options[i]['title'] + ('' if options[i]['available'] else ' — условия не подтверждены'),
        key=f'tactic_{mid}_{tid}_{goal}_{cutoff}')
    tactic = options[selected_tactic]
    st.write('**Основание:** ' + tactic['why'])
    st.write('**Кому:** ' + tactic['roles'])
    for task in tactic['tasks']:
        st.write('• ' + task)
    st.info('Риск: ' + tactic['risk'])
    if tactic.get('sample_note'):
        st.caption(tactic['sample_note'])
    st.markdown('<div id="action-scheme"></div>', unsafe_allow_html=True)
    st.subheader('2. Схема действий и поведение в фазах игры')
    diagram_column, phases_column = st.columns(2, gap='large')
    detail = detailed_instructions(state, tid, tactic)
    with diagram_column:
        st.markdown(action_diagram(tactic['key']), unsafe_allow_html=True)
        st.caption('Учебная иллюстрация: номера обозначают участников примера, стрелки — предполагаемые действия. '
                   'Это не фактические позиции игроков, не трекинг и не прогноз движения. Конкретные исполнители — в подробном плане.')
    with phases_column:
        if not tactic['available']:
            st.warning('Условия этой задачи сейчас не подтверждены. Инструкции доступны для разбора, но план нельзя зафиксировать.')
        for phase, instruction in detail['phases'].items():
            st.write('**' + phase + ':** ' + instruction)
    st.markdown('<div id="player-tasks"></div>', unsafe_allow_html=True)
    st.subheader('3. Задачи игрокам текущего состава')
    if detail['assignments']:
        st.markdown('\n'.join('- **' + person['Игрок'] + '** (' + position_label(person['Подтверждённая позиция'])
                              + '): ' + person['Задача'] for person in detail['assignments']))
    else:
        st.info('Подтверждённых ролей для распределения задачи недостаточно.')
    st.write('**Как проверить:** ' + tactic['check'])
    st.warning(detail['stop'])
    with st.expander('События, на которых основан план, и ограничения данных'):
        if detail['events']:
            st.dataframe(pd.DataFrame(detail['events']), hide_index=True)
            st.caption('Это наблюдения для проверки ситуации; отдельное событие само по себе не доказывает необходимость тактики.')
        else:
            st.caption('Подходящих событий за последние 15 минут нет.')
        st.caption(detail['limits'])
    horizon = st.radio('Через сколько игровых минут проверить', [5, 10], horizontal=True,
                        key=f'horizon_{mid}_{tid}')
    plan_key = f'coaching_plan_{mid}_{tid}_{goal}'
    if st.button('Зафиксировать план на этот отрезок', disabled=not tactic['available'] or cutoff == 0 or rec['finished']):
        st.session_state[plan_key] = freeze_plan(state, tid, goal, tactic, horizon)
    if plan_key in st.session_state:
        saved_plan = st.session_state[plan_key]
        st.write(f'**Зафиксировано:** {saved_plan["tactic"]["title"]}, {saved_plan["clock"]}; '
                 f'отрезок {saved_plan["horizon"]} минут. {saved_plan["tactic"]["check"]}')
        review = review_plan(saved_plan, events, lineups, cutoff, rules)
        if not review['ready']:
            if review.get('ended_early'):
                st.info('Матч завершился до конца запланированного отрезка. Полная проверка не выполнена.')
            else:
                st.caption(f'Продвиньте запись: до конца отрезка осталось {review["remaining_seconds"] // 60} мин '
                           f'{review["remaining_seconds"] % 60} сек. Будущие события пока не оцениваются.')
        else:
            if review['comparable']:
                if review.get('task_metrics'):
                    st.write('**Проверка показателей выбранной задачи**')
                    st.dataframe(pd.DataFrame(review['task_metrics']), hide_index=True)
                st.dataframe(pd.DataFrame([
                    {'Показатель': 'Входы соперника в штрафную / мин',
                     'До плана': round(review['before_entries_per_minute'], 2),
                     'После плана': round(review['after_entries_per_minute'], 2)},
                    {'Показатель': 'Наши удары / мин',
                     'До плана': round(saved_plan['baseline_ours']['shots'] / (saved_plan['baseline_seconds'] / 60), 2),
                     'После плана': round(review['ours']['shots'] / saved_plan['horizon'], 2)}]), hide_index=True)
                st.write('Входы соперника стали реже.' if review['fewer_opponent_entries'] else
                         'Снижения частоты входов соперника не наблюдается.')
                st.write('Наши удары на отрезке: ' + str(review['ours']['shots']))
            else:
                st.info('Перед планом меньше 5 минут наблюдений: надёжно сравнить частоты нельзя.')
            if review['triggers']:
                st.warning('На отрезке были события, требующие пересмотра: ' + '; '.join(review['triggers']))
            st.caption('Это изменение показателей исторической записи. Выполнение выбранного плана не наблюдается; '
                       'причинный эффект тактики не измерен.')
    st.markdown('<div id="team-formation"></div>', unsafe_allow_html=True)
    st.subheader('4. Расстановка и роли игроков на поле')
    with st.container(border=True):
        st.write('Можно проверить 4-3-3, 4-2-3-1, 3-4-2-1, 4-4-2, 4-1-4-1, 3-5-2, 3-4-3, 4-5-1, 5-4-1, 4-3-1-2, 4-3-2-1, 5-3-2, 4-2-2-2 и 3-4-1-2. '
                 'В игровом варианте участвуют только игроки, уже находящиеся на поле.')
        if st.button('Подобрать совместимую схему для текущих игроков'):
            choice = formation_choice(state, tid, roles, profiles, goal)
            if choice:
                st.write('**Предложение по совместимости:** ' + choice['formation'])
                st.markdown(pitch({p['id']: p for p in choice['lineup']}, state['yellow']), unsafe_allow_html=True)
                st.dataframe(pd.DataFrame([{'Игрок': p['name'], 'Роль в предложении': p['position'],
                                           'Основание': p['evidence']} for p in choice['lineup']]), hide_index=True)
                st.caption('Минимум 2 балла перевеса требуется для смены текущей схемы. '
                           'Оценка совместимости не измеряет результативность схемы.')
            else:
                st.info('Полная схема на 11 игроков сейчас не подтверждена. Сначала восстановите доступные роли.')

with scenario:
    st.subheader('Отдельный сценарий на выбранной минуте')
    st.write('Измените счёт или доступность игроков. Запись матча и её журнал останутся фактическими. '
             'Недавняя статистика сохраняется из выбранного момента; это проверка чувствительности, а не симулятор будущего.')
    scenario_preset = st.selectbox('Быстрый сценарий', ['Свободный выбор', 'Пропустили гол', 'Забили гол', 'Удаление игрока'],
                                   key=f'scenario_preset_{mid}_{tid}')
    preset_gf, preset_ga = state['goals'][tid], state['goals'][opp]
    if scenario_preset == 'Пропустили гол': preset_ga += 1
    elif scenario_preset == 'Забили гол': preset_gf += 1
    with st.form(f'scenario_{mid}_{tid}'):
        x, y = st.columns(2)
        gf = x.number_input('Наши голы в сценарии', 0, 20, preset_gf, key=f'scenario_gf_{mid}_{tid}_{scenario_preset}')
        ga = y.number_input('Голы соперника в сценарии', 0, 20, preset_ga, key=f'scenario_ga_{mid}_{tid}_{scenario_preset}')
        injured = st.multiselect('Временно покинули поле / травмированы', list(state['players'][tid]),
                                 format_func=lambda pid: state['players'][tid][pid]['name'])
        sent_off = st.selectbox('Игрок удалён (для сценария удаления)', [None, *state['players'][tid]],
                                format_func=lambda pid: 'Не выбрано' if pid is None else state['players'][tid][pid]['name'])
        unavailable_reserves = st.multiselect('Недоступны со скамейки', list(state['bench'][tid]),
                                               format_func=lambda pid: state['bench'][tid][pid]['name'])
        apply_scenario = st.form_submit_button('Рассчитать отдельный сценарий')
    if apply_scenario:
        custom = scenario_state(state, tid, gf, ga, [pid for pid in injured if pid != sent_off], unavailable_reserves,
                                [sent_off] if scenario_preset == 'Удаление игрока' and sent_off is not None else ())
        r = recommend(custom, tid, goal, roles)
        if injured:
            st.warning('Игрок покинул поле. Требуется оценить возможность срочной замены; плановое ожидание до 60-й минуты здесь неприменимо.')
        if scenario_preset == 'Удаление игрока' and sent_off is not None:
            st.warning(f'Сценарий удаления: {state["players"][tid][sent_off]["name"]} удалён, команда играет в меньшинстве.')
        st.write('**План:** ' + PLANS[r['plan']])
        st.write(r['attack']); st.write(r['defense'])
        for action in tactical_details(custom, tid, r['plan'], team_history[opp])['actions']:
            st.write('• ' + action)
        if injured and r['subs_allowed']:
            for out in injured:
                role = state['players'][tid][out]['position']
                available = [p['name'] for pid, p in custom['bench'][tid].items()
                             if role_group(roles.get(pid, '')) == role_group(role)]
                st.write(f'**На роль {state["players"][tid][out]["name"]}:** ' +
                         (', '.join(available) if available else 'нет подтверждённых кандидатов; решение тренера.'))
        if not r['subs_allowed']: st.info('Лимит замен или окон исчерпан.')

with analytics:
    forecast_panel = st.container()
    with forecast_panel:
        st.subheader('Прогноз на текущий момент')
    with st.container():
        st.subheader('Текущий прогресс матча')
        st.write(f'**{teams[tid]} {state["goals"][tid]} : {state["goals"][opp]} {teams[opp]}** · '
                 + ('до начала матча' if cutoff == 0 else clock_label(state['last'])))
        st.write('**Как меняется накопленный xG**')
        xs = [{'Секунда записи': 0, teams[tid]: 0., teams[opp]: 0.}]
        total_xg = {tid: 0., opp: 0.}
        for t, e in state['visible']:
            if e['type']['name'] == 'Shot':
                side = e['team']['id']
                total_xg[side] += e['shot'].get('statsbomb_xg', 0.)
                xs.append({'Секунда записи': t, teams[tid]: total_xg[tid], teams[opp]: total_xg[opp]})
        st.line_chart(pd.DataFrame(xs).set_index('Секунда записи'))
        st.caption('Только уже произошедшие удары. xG не является счётом и не гарантирует будущие голы.')
    report_path = Path(__file__).parent / 'reports' / 'ml_results.json'
    ml = ml_report(report_path.stat().st_mtime_ns if report_path.exists() else 0)
    if ml is None:
        st.info('Обучение ещё не завершено. После запуска train_models.py здесь появятся реальные результаты и прогнозы.')
    else:
        with forecast_panel:
            if competition == ml['competition_id'] and season == ml['season_id']:
                part = next((name for name, split in ml['splits'].items() if mid in split['match_ids']), 'неизвестно')
                st.info(f'Выбранный матч относится к части «{part}». Прогноз на обучающем матче нельзя считать независимой проверкой.')
                try:
                    from ml_runtime import predict_all
                    selected, probabilities = predict_all(events, lineups, cutoff, tid, game['home_team']['home_team_id'])
                    model_name = st.selectbox('Модель прогноза', list(probabilities), index=list(probabilities).index(selected))
                    if rec['finished']:
                        st.info('Матч завершён: его исход уже известен. Прогноз больше не нужен.')
                    else:
                        probability_view(probabilities[model_name])
                        st.caption('Экспериментальные вероятности. Перед матчем модель знает в основном фактор своего поля, '
                                   'а не реальную силу выбранных стартовых игроков.')
                        if state['last'].get('minute', 0) > 85:
                            st.warning('Модель обучалась на срезах до 85-й минуты. Более поздний прогноз является экстраполяцией.')
                        if st.button('Построить изменение ML-прогноза', key=f'curve_{mid}_{tid}'):
                            from ml_data import SAMPLE_MINUTES
                            from core import seconds
                            curve = []
                            for minute in SAMPLE_MINUTES:
                                period, local = (1, minute*60) if minute < 45 else (2, (minute-45)*60)
                                tick = max((t for t, e in timed if e['period'] == period and seconds(e) <= local), default=None)
                                if tick is not None and tick <= cutoff:
                                    _, probs = predict_all(events, lineups, tick, tid, game['home_team']['home_team_id'])
                                    p = probs[model_name]
                                    curve.append({'Минута': minute, 'Победа': p[2], 'Ничья': p[1], 'Поражение': p[0]})
                            if curve:
                                st.line_chart(pd.DataFrame(curve).set_index('Минута'))
                        st.download_button('Скачать текущие прогнозы всех моделей',
                            json.dumps({'match_id': mid, 'cutoff': cutoff, 'team_id': tid, 'split': part,
                                        'selected_by_validation': selected, 'class_order': ['loss', 'draw', 'win'],
                                        'probabilities': probabilities}, ensure_ascii=False, indent=2),
                            file_name=f'ml_{mid}_{cutoff}.json', mime='application/json')
                except (OSError, ValueError, ImportError, RuntimeError) as exc:
                    st.error(f'Не удалось загрузить модели: {exc}. Повторите train_models.py в окружении из requirements.txt.')
            else:
                st.warning('Этот набор отличается от Premier League 2015/16. Качество моделей на нём не проверено; вероятности здесь не показываются.')
        st.divider()
        st.subheader('Метрики обучения и проверки моделей')
        st.caption('Все модели оценивают исход основного времени. Результат выбирается по валидации; тест не используется для выбора.')
        split_rows = [{'Часть': name, 'Матчи': value['matches'], 'Состояния': value['states'],
                       'С': value['date_from'], 'По': value['date_to']} for name, value in ml['splits'].items()]
        st.dataframe(pd.DataFrame(split_rows), hide_index=True, width='stretch')
        table = [{'Модель': name, 'Validation Log Loss': r['validation']['log_loss'],
                  'Test Log Loss': r['test']['log_loss'], 'Test Brier': r['test']['brier_multiclass'],
                  'Test Accuracy': r['test']['accuracy'], 'Test AUC macro': r['test'].get('roc_auc_macro_ovr')} for name, r in ml['models'].items()]
        st.dataframe(pd.DataFrame(table).round(4), hide_index=True, width='stretch')
        st.write('**Модель, выбранная по валидации:** ' + ml['selected_by_validation'])
        st.write(f'Базовый прогноз по времени, счёту, численности и полю: test Log Loss **{ml["baseline_score_time"]["log_loss"]:.4f}**. '
                 f'Частоты классов из обучения: **{ml["baseline_training_class_prior"]["log_loss"]:.4f}**. Меньше — лучше.')
        if ml['baseline_score_time']['log_loss'] < min(r['test']['log_loss'] for r in ml['models'].values()):
            st.warning('На этом тесте простая базовая модель оказалась лучше всех шести полных моделей по Log Loss. '
                       'Преимущество нейросетей и дополнительных признаков не подтверждено. Основная модель среди шести '
                       'по-прежнему выбрана по валидации, а не подменена после просмотра теста.')
        model_for_details = st.selectbox('Подробности проверки', list(ml['models']))
        checked = ml['models'][model_for_details]
        with st.expander('Полные метрики обучения, валидации и теста', expanded=False):
            metric_names = {'accuracy': 'Accuracy', 'precision_macro': 'Precision macro', 'recall_macro': 'Recall macro',
                            'f1_macro': 'F1 macro', 'roc_auc_macro_ovr': 'ROC-AUC macro',
                            'pr_auc_macro_average_precision': 'PR-AUC macro (AP)', 'mcc': 'MCC', 'cohen_kappa': 'Cohen kappa',
                            'log_loss': 'Log Loss', 'brier_multiclass': 'Brier', 'ece_top_label_10_bins': 'ECE'}
            metrics_rows = [{'Часть': split, **{title: checked.get(split, {}).get(key) for key, title in metric_names.items()}}
                            for split in ('train', 'validation', 'test')]
            st.dataframe(pd.DataFrame(metrics_rows).round(4), hide_index=True, width='stretch')
            st.caption('PR-AUC здесь означает average precision. ECE использует 10 интервалов уверенности. '
                       'Для Log Loss, Brier и ECE меньше лучше. Метрики описывают прогноз исхода, не эффективность тактики.')
            if 'per_class' in checked['test']:
                st.dataframe(pd.DataFrame(checked['test']['per_class']).T.round(4), width='stretch')
            all_metrics_path = Path(__file__).parent / 'reports' / 'all_metrics.csv'
            if all_metrics_path.exists():
                st.download_button('Скачать метрики всех моделей и частей CSV', all_metrics_path.read_bytes(),
                                   file_name='all_metrics.csv', mime='text/csv')
        if 'roc_auc_per_class' in checked['test']:
            st.write('**ROC-AUC по классам:** ' + ', '.join(f'{k}: {v:.4f}' for k, v in checked['test']['roc_auc_per_class'].items()))
            if 'auc_by_minute' in checked:
                st.line_chart(pd.DataFrame(checked['auc_by_minute'])[['minute', 'roc_auc_macro_ovr']].set_index('minute'))
                st.caption('AUC macro OvR по минутам. Общий AUC включает поздние состояния, где счёт уже информативен.')
        st.write('**95% интервал test Log Loss при повторной выборке целых матчей:** ' +
                 ' — '.join(f'{x:.3f}' for x in checked['test']['log_loss_match_bootstrap_95']))
        st.caption('Интервал отражает вариацию по матчам тестового набора. Общие команды и один сезон ограничивают обобщение.')
        a, b = st.columns(2)
        with a:
            st.write('**Матрица ошибок: строки — факт, столбцы — прогноз**')
            st.dataframe(pd.DataFrame(checked['test']['confusion_matrix'], index=ml['labels'], columns=ml['labels']))
        with b:
            st.write('**Проверка вероятности победы**')
            bins = [x for x in checked['calibration_test'] if x['class'] == 'Победа']
            if bins:
                st.line_chart(pd.DataFrame({'Прогноз': [x['predicted'] for x in bins], 'Наблюдаемая доля': [x['observed'] for x in bins]},
                                            index=[x['bin'] for x in bins]))
        if 'validation_curve' in checked['configuration']:
            st.line_chart(pd.DataFrame(checked['configuration']['validation_curve']).set_index('epoch'))
        with st.expander('Качество по минутам и все тестовые прогнозы'):
            predictions_file = Path(__file__).parent / 'reports' / 'test_predictions.csv'
            if predictions_file.exists():
                import numpy as np
                predictions = pd.read_csv(predictions_file)
                selected_predictions = predictions[predictions['model'] == model_for_details].copy()
                p = selected_predictions[['p_loss', 'p_draw', 'p_win']].to_numpy()
                actual = selected_predictions['actual'].to_numpy(dtype=int)
                selected_predictions['Log Loss'] = -np.log(np.clip(p[np.arange(len(p)), actual], 1e-6, 1))
                st.line_chart(selected_predictions.groupby('minute')['Log Loss'].mean())
                st.caption('Каждая точка — средний Log Loss на тестовых матчах в одну минуту. '
                           'Поздние состояния обычно проще, поскольку часть исхода уже отражена в счёте.')
                st.download_button('Скачать все тестовые прогнозы CSV', predictions_file.read_bytes(),
                                   file_name='test_predictions.csv', mime='text/csv')
        st.download_button('Скачать полный ML-отчёт JSON', json.dumps(ml, ensure_ascii=False, indent=2),
                           file_name='ml_results.json', mime='application/json')
        st.caption('Оба ракурса и все срезы одного матча зависимы. Нет утверждения, что использование рекомендаций повышает вероятность победы.')

with comparison:
    st.subheader('Одна ситуация — разные приоритеты')
    st.write('Изменяется цель решения, а факты матча и доступный состав остаются теми же.')
    for col, objective, title in zip(st.columns(2), ['win', 'draw'], ['Нужна победа', 'Достаточно не проиграть']):
        r = recommend(state, tid, objective, roles)
        with col:
            st.markdown(f'### {title}')
            st.write('**' + PLANS[r['plan']] + '**')
            st.write(r['attack'])
            st.caption('Оценки правил до порога переключения; это не вероятности.')
            st.bar_chart(pd.DataFrame({'Баллы': {PLANS[k]: v for k, v in r['scores'].items()}}))
            st.write('**Риск:** ' + r['risk'])
    st.caption('Рекомендации могут совпасть: например, сохранение преимущества соответствует обеим целям.')

with journal:
    st.subheader('Когда и почему менялся план')
    st.caption('Контроль каждые 5 минут и после гола, удаления или замены. Порог смены — 2 балла; гол и удаление позволяют немедленный пересмотр.')
    st.dataframe(pd.DataFrame([{'Время': x['time'], 'План': x['plan'], 'Причина': x['reason']} for x in log]),
                 hide_index=True, width='stretch')
    note = st.text_area('Заметка тренера к этому моменту', key=f'note_{mid}_{tid}_{cutoff}',
                        placeholder='Например: проверить готовность игрока перед решением о замене.')
    st.subheader('Известные события матча')
    rows = []
    for t, e in state['visible']:
        kind = e['type']['name']
        if kind == 'Substitution' or card(e) or kind in ('Own Goal Against', 'Tactical Shift') or kind == 'Shot' and e.get('shot', {}).get('outcome', {}).get('name') == 'Goal':
            description = {'Substitution': 'Замена', 'Tactical Shift': 'Перестроение', 'Own Goal Against': 'Автогол', 'Shot': 'Гол'}.get(kind, kind)
            description = card(e) or description
            name = e.get('player', {}).get('name', '')
            if kind == 'Substitution': name += ' → ' + e['substitution']['replacement']['name']
            rows.append({'Время': clock_label(e), 'Команда': e.get('team', {}).get('name', ''), 'Событие': description, 'Игрок': name})
    if rows: st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
    else: st.info('Значимых событий ещё нет.')
    report = {'match_id': mid, 'team': teams[tid], 'goal': target, 'clock': clock_label(state['last']),
              'score': [state['goals'][tid], state['goals'][opp]], 'recommendation': PLANS[effective],
              'evidence': rec['evidence'], 'coach_note': note, 'decisions': log,
              'substitution_options': rec['sub_options'], 'short_plan': st.session_state.get(plan_key),
              'disclaimer': 'Историческое воспроизведение. Причинный эффект альтернативной тактики не измерен.'}
    st.download_button('Скачать разбор решения', json.dumps(report, ensure_ascii=False, indent=2),
                       file_name=f'matchplan_{mid}_{cutoff}.json', mime='application/json')
    report_text = '\n'.join([
        f'# MatchPlan — {teams[tid]} vs {teams[opp]}', '',
        f'- Дата: {game["match_date"]}', f'- Состояние: {clock_label(state["last"])}',
        f'- Счёт: {state["goals"][tid]}:{state["goals"][opp]}', f'- Цель: {target}',
        f'- Рекомендация: {PLANS[effective]}', '', '## План действий', rec['attack'], '', rec['defense'], '',
        '## Основания', *[f'- {reason}' for reason in rec['evidence']], '',
        '## Компромисс', rec['risk'], '', '## Заметка тренера', note or '—', '',
        'Историческое воспроизведение. Причинное влияние альтернативной тактики на итог матча не измерено.'
    ])
    if st.session_state.get(plan_key):
        exported_plan = st.session_state[plan_key]
        report_text += '\n\n## План на отрезок\n' + exported_plan['tactic']['title'] + '\n'
        report_text += f'Начало: {exported_plan["clock"]}; длительность: {exported_plan["horizon"]} минут.\n'
        report_text += '\n'.join('- ' + task for task in exported_plan['tactic']['tasks'])
        report_text += '\nПроверка: ' + exported_plan['tactic']['check']
    if rec['sub_options']:
        report_text += '\n\n## Альтернативы одной замены\n' + '\n'.join(
            f'- {s["out"]} → {s["in"]}: {s["reason"]}' for s in rec['sub_options'])
    st.download_button('Скачать отчёт для тренера (Markdown)', report_text,
                       file_name=f'matchplan_{mid}_{cutoff}.md', mime='text/markdown')
    if st.button('Сравнить подсказки с реальными заменами', key=f'coach_audit_{mid}_{tid}'):
        from coach_audit import audit_substitutions, audit_formations
        with st.spinner('Сопоставляю рекомендации до замен с фактическими решениями…'):
            audit = audit_substitutions(events, lineups, tid, roles, rules, goal, cutoff=cutoff)
            formation_audit = audit_formations(events, lineups, tid, roles, profiles, rules, goal, cutoff=cutoff)
        if not audit['actual_count']:
            st.info('К выбранному моменту нет замен после 60-й минуты для сравнения. Продвиньте время матча.')
        else:
            st.write(f'Покрытие подсказкой: {audit["covered_count"]}/{audit["actual_count"]} фактических замен.')
            if audit['agreement_when_suggested'] is not None:
                st.write(f'Полное совпадение пары «ушёл / вышел» среди подсказанных замен: '
                         f'{audit["exact_count"]}/{audit["covered_count"]}.')
                st.write(f'Совпадение среди первых трёх вариантов: {audit["top3_count"]}/{audit["covered_count"]}.')
            st.caption(f'Цель сравнения: «{target.lower()}». Это описательное совпадение с историческими решениями, '
                       'а не оценка влияния рекомендации на результат; причина фактической замены в наборе данных не указана.')
            st.dataframe(pd.DataFrame([{'Время': row['time'], 'Фактическая замена': f'{row["actual_out"]} → {row["actual_in"]}',
                'Подсказка системы': f'{row["suggestion"]["out"]} → {row["suggestion"]["in"]}' if row['suggestion'] else 'Подходящая пара не найдена',
                'Совпало': 'Да' if row['exact_match'] else 'Нет'} for row in audit['rows']]), hide_index=True, width='stretch')
        st.write('**Смена схемы: сравнение до фактического решения тренера**')
        if formation_audit['rows']:
            st.write(f'Совпадений: {formation_audit["exact_count"]}/{formation_audit["covered_count"]} '
                     f'при подтверждённой схеме; всего фактических смен: {formation_audit["actual_count"]}.')
            st.dataframe(pd.DataFrame(formation_audit['rows']).rename(columns={'time': 'Время', 'before': 'До',
                'actual': 'Факт', 'suggestion': 'Предложение системы', 'exact_match': 'Совпало'}), hide_index=True)
        else:
            st.info('К выбранному моменту в событиях нет зафиксированных изменений числовой схемы.')
        st.caption('Проверка выполняется на ситуации непосредственно до решения. Отсутствие Tactical Shift '
                   'не доказывает отсутствие реальных перестроений; причины решений тренера неизвестны.')

with method:
    tactical_audit = Path(__file__).parent / 'reports/tactical_field_audit.json'
    if tactical_audit.exists():
        with st.expander('Какие тактические данные реально есть в StatsBomb'):
            audit = json.loads(tactical_audit.read_text(encoding='utf-8'))
            st.write(f'Аудит АПЛ 2015/16: {audit["matches"]} матчей, {audit["events"]:,} событий.')
            descriptions={'under_pressure':'События с отмеченным давлением','counterpress':'События с флагом контрпрессинга',
                          'dribble_outcome':'Результат обводки','pass_assisted_shot_id':'Связь передачи с ударом',
                          'shot_key_pass_id':'Обратная связь удара с передачей',
                          'pass_cut_back':'Пас назад от лицевой','pass_through_ball':'Разрезающая передача'}
            st.dataframe(pd.DataFrame([{'Поле':descriptions.get(key,key),'Событий':values['events'],
                                       'Матчей':values['matches']} for key,values in audit['fields'].items()]), hide_index=True)
            st.caption('Это наличие явных отметок в записи. Отсутствие флага не означает отсутствие явления. Непрерывного трекинга игроков здесь нет.')
    st.image(str(Path(__file__).parent / 'assets' / 'statsbomb.png'), width=180)
    past_report = Path(__file__).parent / 'reports' / 'history_experiment.json'
    if past_report.exists():
        with st.expander('Эксперимент с прошлыми сезонами'):
            history_result = json.loads(past_report.read_text(encoding='utf-8'))
            st.write('69 матчей Ла Лиги 2013/14–2014/15 добавлены только к обучению. '
                     'Валидация и тест АПЛ сохранены. Наборы прошлых сезонов неполные.')
            st.dataframe(pd.DataFrame([{'Обучение': name, 'Validation Log Loss': result['validation']['log_loss'],
                'Test Log Loss': result['test']['log_loss'], 'Test AUC': result['test']['roc_auc_macro_ovr']}
                for name, result in history_result['results'].items()]), hide_index=True)
            st.caption('Смешанный результат: добавление истории не улучшило все метрики. '
                       'Основные модели и ранее опубликованные оценки не заменены этим экспериментом.')
    st.subheader('Что умеет эта версия')
    st.write('Гибридная система: шесть обученных моделей прогнозируют исход, оптимизация подбирает игроков на роли, '
             'а экспертные правила рекомендуют тактический подход. Прогнозы и рекомендации разделены: '
             'причинный эффект несыгранных тактик не измерен.')
    st.write(f'**История для профилей в этом матче:** {previous_count} предыдущих матчей из доступной выборки. '
              'Роли запасных используются при наличии предыдущих наблюдений. Для АПЛ дополнительно доступна '
              'история игроков из 69 матчей прошлых сезонов Ла Лиги; при совпадении ID и только до даты матча. '
              'Стартовые 11 и скамейка берутся из фактической заявки.')
    st.markdown('''**Защита от утечки данных**

- События после выбранного момента исключаются.
- Будущие карточки, позиции и интервалы участия из файлов составов не используются.
- Профили запасных строятся только по матчам с более ранней датой.
- Итоговый счёт из метаданных не передаётся алгоритму.

**Ограничения**

- Основной набор — Premier League 2015/16; один исторический сезон ограничивает перенос на другие лиги и годы.
- Отдельный демонстрационный набор «Байера» содержит только его матчи; модели на нём не проверены.
- Нагрузка в минутах не равна измеренной усталости; скорости и физической готовности нет.
- Тактический подход — рекомендация. Схема на поле показывает фактическую расстановку.
- Запись продолжает фактический матч независимо от рекомендаций. Альтернативный ход игры не симулируется.
- Роли для замен сгруппированы грубо; точную совместимость и готовность подтверждает тренер.
- Тактические правила и веса — допущения авторов. Баллы не переводятся в вероятности; вероятности дают отдельные ML-модели.
''')
    evaluation = Path(__file__).parent / 'reports' / 'evaluation.json'
    if evaluation.exists():
        result = json.loads(evaluation.read_text(encoding='utf-8'))
        st.subheader('Аудит правил на демо «Байер»: 34 матча')
        st.json(result, expanded=False)
    audit_path = Path(__file__).parent / 'reports' / 'data_audit.json'
    if audit_path.exists():
        st.subheader('Аудит основного набора Premier League')
        st.json(json.loads(audit_path.read_text(encoding='utf-8')), expanded=False)
    preprocessing_path = Path(__file__).parent / 'reports' / 'preprocessing_audit.json'
    if preprocessing_path.exists():
        st.subheader('Схема, пропуски, дубликаты и координаты')
        st.json(json.loads(preprocessing_path.read_text(encoding='utf-8')), expanded=False)
    st.markdown('Источник: [StatsBomb Open Data](https://github.com/hudl/open-data). '
                'При публикации исследования необходимо указать StatsBomb и использовать их логотип согласно условиям источника.')
