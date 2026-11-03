"""Descriptive territory, set pieces and a self-contained coach report."""
from collections import Counter
from html import escape
from core import metrics,clock_label


def territory(state,tid,window=900):
    opp=next(t for t in state['players'] if t!=tid)
    counts=Counter()
    for tick,e in state['visible']:
        if not max(0,state['cutoff']-window)<=tick<=state['cutoff'] or e['type']['name']!='Pass': continue
        pas=e.get('pass',{}); loc=e.get('location')
        if pas.get('outcome') or not loc or loc[0]<80: continue
        counts[e['team']['id']]+=1
    total=counts[tid]+counts[opp]
    return {'ours':counts[tid],'opponent':counts[opp],'share':counts[tid]/total if total else None,
            'definition':'Доля нашей команды среди успешных передач обеих команд, начатых в атакующей трети. Это событийный показатель, не владение мячом по времени.'}


def set_piece_summary(state,tid,window=0):
    opp=next(t for t in state['players'] if t!=tid)
    bins={}
    for tick,e in state['visible']:
        if tick>state['cutoff'] or window and tick<state['cutoff']-window: continue
        if e['type']['name']!='Shot': continue
        team=e.get('team',{}).get('id')
        if team not in (tid,opp): continue
        shot=e.get('shot',{})
        if shot.get('type',{}).get('name')=='Penalty': category='Пенальти'
        elif shot.get('type',{}).get('name')=='Free Kick': category='Прямой штрафной'
        else:
            category={'From Corner':'После углового','From Free Kick':'После розыгрыша штрафного',
                      'From Throw In':'После вбрасывания'}.get(e.get('play_pattern',{}).get('name'),'Другие атаки')
        key=(team,category); item=bins.setdefault(key,{'Удары':0,'Голы':0,'xG':0.})
        item['Удары']+=1; item['Голы']+=int(shot.get('outcome',{}).get('name')=='Goal'); item['xG']+=shot.get('statsbomb_xg',0)
    return [{'Команда':'Мы' if team==tid else 'Соперник','Ситуация':category,
             **dict(value,xG=round(value['xG'],3))} for (team,category),value in sorted(bins.items())]


def coach_report_html(state,tid,teams,match_id,package=None,execution=None,source='StatsBomb Open Data'):
    opp=next(t for t in state['players'] if t!=tid)
    def text(value): return escape(str(value))
    def table(rows):
        if not rows: return '<p>Нет записанных наблюдений.</p>'
        keys=list(rows[0]); result='<table><thead><tr>'+''.join('<th>'+text(k)+'</th>' for k in keys)+'</tr></thead><tbody>'
        for row in rows: result+='<tr>'+''.join('<td>'+text(row.get(k,''))+'</td>' for k in keys)+'</tr>'
        return result+'</tbody></table>'
    a,b=metrics(state,tid,0),metrics(state,opp,0)
    body=f'<h1>MatchPlan · отчёт тренера</h1><h2>{text(teams[tid])} {state["goals"][tid]} : {state["goals"][opp]} {text(teams[opp])}</h2>'
    body+=f'<p>Матч {int(match_id)} · {text(clock_label(state["last"]))} · только уже произошедшие события.</p>'
    body+=table([{'Показатель':label,'Мы':a[key],'Соперник':b[key]} for label,key in [('Удары','shots'),('xG','xg'),('Входы в штрафную','box_entries')]])
    if package:
        body+='<h2>Выбранный пакет: '+text(package['title'])+'</h2><p>'+text(package['intent'])+'</p>'
        body+='<p>Цель: '+('победить' if package['goal']=='win' else 'не проиграть')+'. Создано: '+text(package['plan']['clock'])+'</p>'
        if package['formation']: body+='<p>Схема: '+text(package['formation']['formation'])+'</p>'
        if package['substitution']: body+='<p>Кандидат на замену: '+text(package['substitution']['out'])+' → '+text(package['substitution']['in'])+'</p>'
        body+='<h3>'+text(package['task']['title'])+'</h3><ol>'+''.join('<li>'+text(t)+'</li>' for t in package['task']['tasks'])+'</ol>'
        body+='<p>Риск: '+text(package['task']['risk'])+'</p><p>Проверка: '+text(package['task']['check'])+'</p>'
        body+='<h3>Индивидуальные задачи</h3>'+table(package['plan']['details']['assignments'])
        body+='<h3>Основания</h3><p>'+text(package['support']['level'])+'</p><p>'+text(package['task']['why'])+'</p>'
    if execution:
        body+='<h3>Ручные отметки тренера</h3>'+table([{'Действие':key,'Статус':value} for key,value in execution.get('statuses',{}).items()])
        body+='<p>'+text(execution.get('note',''))+'</p><p>Отметки не подтверждают выполнение плана в исторической записи.</p>'
    body+='<h2>Удары по типу атаки</h2>'+table(set_piece_summary(state,tid))
    body+='<footer>Источник событий: '+text(source)+'. xG описывает качество ударов. Пакет — предложение тренеру; причинный эффект не измерен.</footer>'
    return '<!doctype html><html lang="ru"><meta charset="utf-8"><title>MatchPlan — отчёт</title><style>body{font:16px/1.6 system-ui;max-width:1000px;margin:36px auto;padding:24px;color:#172d48}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{border:1px solid #ccd6de;padding:9px;text-align:left}th{background:#eff4f8}footer{margin-top:35px;color:#536778}@media print{body{margin:0}}</style>'+body+'</html>'
