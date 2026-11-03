"""Independent event analytics inspired by the supplied dashboards.

No source from the two unlicensed dashboard archives is redistributed.
All positions are ball-event locations, not player tracking.
"""
import html
from collections import Counter,defaultdict
from core import seconds,clock_label
from event_adapter import coordinates,movement,visible_events
from field_views import field,point


def phase_comparison(state,tid,minutes=10):
    """Two adjacent equal windows in the current period, no halftime crossing."""
    period=state['last'].get('period',1)
    current=seconds(state['last']); width=minutes*60
    if current<2*width:
        return {'ready':False,'message':f'Нужны два полных отрезка по {minutes} минут в текущем тайме.'}
    groups=[[],[]]
    for tick,e in visible_events(state):
        if e.get('period')!=period or e.get('team',{}).get('id')!=tid: continue
        local=seconds(e)
        if current-2*width<local<=current-width: groups[0].append(e)
        elif current-width<local<=current: groups[1].append(e)
    values=[]
    for es in groups:
        c=Counter()
        for e in es:
            kind=e.get('type',{}).get('name'); loc=coordinates(e.get('location'))
            if kind=='Shot': c['Удары']+=1; c['xG']+=e.get('shot',{}).get('statsbomb_xg',0)
            if kind=='Pressure': c['Давления']+=1
            if kind=='Pass' and not e.get('pass',{}).get('outcome'):
                c['Успешные передачи']+=1
                if loc and loc[0]>=80: c['Передачи из атакующей трети']+=1
            move=movement(e)
            if move and move[2] and move[1][0]-move[0][0]>=10: c['Продвижения ≥10']+=1
            if move and move[2] and move[1][0]>=102 and 18<=move[1][1]<=62 and not(move[0][0]>=102 and 18<=move[0][1]<=62):
                c['Входы в штрафную']+=1
        values.append(c)
    rows=[{'Показатель':key,'Предыдущий отрезок':round(values[0][key],3),'Последний отрезок':round(values[1][key],3),
           'Изменение':round(values[1][key]-values[0][key],3)} for key in
          ('Удары','xG','Давления','Успешные передачи','Передачи из атакующей трети','Продвижения ≥10','Входы в штрафную')]
    return {'ready':True,'rows':rows,'values':values,'period':period,'window_minutes':minutes,
            'local_bounds':[(current-2*width,current-width),(current-width,current)]}


def phase_advice(ours,theirs):
    if not ours['ready'] or not theirs['ready']: return []
    before,now=theirs['values']; ownbefore,ownnow=ours['values']; advice=[]
    if now['Входы в штрафную']-before['Входы в штрафную']>=2:
        advice.append({'Наблюдение':f'Входы соперника в штрафную: {before["Входы в штрафную"]} → {now["Входы в штрафную"]}.',
            'Задача':'Сначала проверить эпизоды входов: опорник страхует центр, крайний защитник не выходит без страховки.',
            'Проверка':'За следующие 5 минут сравнить число входов; при голе или удалении сразу пересмотреть план.'})
    if ownbefore['Продвижения ≥10']>=4 and ownnow['Продвижения ≥10']<=ownbefore['Продвижения ≥10']/2:
        advice.append({'Наблюдение':f'Наши продвижения: {ownbefore["Продвижения ≥10"]} → {ownnow["Продвижения ≥10"]}.',
            'Задача':'Проверить сеть передач: предложить получателю открываться под диагональный пас; сохранять опорную страховку.',
            'Проверка':'Повторно оценить успешные продвижения и потери через 5 минут.'})
    if not advice:
        advice.append({'Наблюдение':'Пороговые сигналы по входам и продвижению не сработали.',
            'Задача':'Сверить текущий план со счётом и доступными игроками, затем просмотреть цепочки ударов.',
            'Проверка':'Повторить сравнение через 5 минут; отсутствие сигнала не означает отсутствие угрозы.'})
    return advice


def network_analysis(state,tid,window=900,min_edge=2):
    links=Counter(); names={}; locs=defaultdict(list)
    for tick,e in visible_events(state,window):
        if e.get('team',{}).get('id')!=tid or e.get('type',{}).get('name')!='Pass': continue
        p=e.get('pass',{}); a=e.get('player',{}); b=p.get('recipient',{}); move=movement(e)
        if not move or not move[2] or not a.get('id') or not b.get('id') or a['id']==b['id']: continue
        links[a['id'],b['id']]+=1; names[a['id']]=a.get('name','?'); names[b['id']]=b.get('name','?')
        locs[a['id']].append(move[0]); locs[b['id']].append(move[1])
    total=sum(links.values()); nodes=[]
    for pid,name in names.items():
        sent=sum(n for (a,b),n in links.items() if a==pid); received=sum(n for(a,b),n in links.items() if b==pid)
        neighbours={b if a==pid else a for a,b in links if a==pid or b==pid}
        nodes.append({'id':pid,'Игрок':name,'Отдал':sent,'Получил':received,'Партнёров':len(neighbours),
                      'Доля участий':(sent+received)/(2*total) if total else 0,
                      'location':tuple(sum(p[i] for p in locs[pid])/len(locs[pid]) for i in (0,1))})
    nodes.sort(key=lambda n:(-n['Доля участий'],n['id']))
    filtered=[{'a':a,'b':b,'Передач':count,'От':names[a],'Кому':names[b]} for (a,b),count in links.most_common() if count>=min_edge]
    return {'nodes':nodes,'edges':filtered,'total':total,'threshold':min_edge}


def network_diagram(network):
    positions={n['id']:point(n['location']) for n in network['nodes']}; parts=[]
    for e in network['edges']:
        a,b=positions[e['a']],positions[e['b']]
        title=html.escape(e['От']+' → '+e['Кому']+': '+str(e['Передач']))
        parts.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="#306a9e" opacity=".5" stroke-width="{min(8,e["Передач"])}"><title>{title}</title></line>')
    for i,n in enumerate(network['nodes'],1):
        x,y=positions[n['id']]; radius=8+22*n['Доля участий']
        parts.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="#156c80"/><text x="{x}" y="{y+4}" text-anchor="middle" fill="white" font-size="11">{i}</text>')
    return field(''.join(parts),'Сеть передач и участие игроков',light=True)


def progression(state,tid,window=0):
    rows=[]
    for tick,e in visible_events(state,window):
        if e.get('team',{}).get('id')!=tid: continue
        move=movement(e)
        if move and move[2] and move[1][0]-move[0][0]>=10:
            rows.append({'event':e,'start':move[0],'end':move[1],'tick':tick})
    return rows


def arrows(rows,value_key=None):
    parts=['<defs><marker id="lab-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#146d89"/></marker></defs>']
    for row in rows:
        x,y=point(row['start']); xx,yy=point(row['end'])
        title=html.escape(row['event'].get('player',{}).get('name','?'))
        if value_key: title+=f' · xT {row[value_key]:+.4f}'
        parts.append(f'<line x1="{x}" y1="{y}" x2="{xx}" y2="{yy}" stroke="#146d89" stroke-width="2" opacity=".65" marker-end="url(#lab-arrow)"><title>{title}</title></line>')
    return field(''.join(parts),'Наблюдавшиеся продвижения мяча',light=True)


def xt_surface_diagram(surface):
    from expected_threat import L,W
    values=surface['values']; high=max(values) or 1; parts=[]
    for i,v in enumerate(values):
        col,row=i%L,i//L; x,y=20+col*560/L,20+row*390/W
        parts.append(f'<rect x="{x}" y="{y}" width="{560/L}" height="{390/W}" fill="#18979b" fill-opacity="{.05+.7*v/high}" stroke="#dde7e9"/><text x="{x+280/L}" y="{y+195/W+4}" text-anchor="middle" fill="#123447" font-size="10">{v:.3f}</text>')
    return field(''.join(parts),'xT зон, модель предыдущих обучающих матчей',light=True)


def xt_summary(rows):
    byplayer=defaultdict(lambda:{'Действий':0,'xT сумма':0.,'xT положительный':0.})
    for row in rows:
        e=row['event']; key=(e.get('player',{}).get('id'),e.get('player',{}).get('name','?'))
        result=byplayer[key]; result['Действий']+=1; result['xT сумма']+=row['xt']; result['xT положительный']+=max(0,row['xt'])
    return sorted([{'Игрок':name,**{k:round(v,4) for k,v in stats.items()}} for (pid,name),stats in byplayer.items()],key=lambda r:-r['xT сумма'])
