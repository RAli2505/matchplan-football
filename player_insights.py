"""Individual event cards; no inferred fitness, speed or player quality rating."""
from collections import Counter
import html
from core import clock_label
from field_views import field,point


def player_card(state,tid,pid):
    visible=[(t,e) for t,e in state['visible'] if t<=state['cutoff']]
    shots={e.get('id'):(t,e) for t,e in visible if e['type']['name']=='Shot' and e.get('id')}
    counts=Counter(); rows=[]; locations=[]
    for tick,e in visible:
        if e.get('team',{}).get('id')!=tid or e.get('player',{}).get('id')!=pid: continue
        kind=e['type']['name']; location=e.get('location')
        if kind=='Pass':
            pas=e.get('pass',{}); complete=not pas.get('outcome')
            counts['passes']+=1; counts['passes_complete']+=int(complete)
            if e.get('under_pressure') is True:
                counts['pressured']+=1; counts['pressured_complete']+=int(complete)
            end=pas.get('end_location')
            if complete and location and end and end[0]-location[0]>=10: counts['forward_passes']+=1
            shot=shots.get(pas.get('assisted_shot_id'))
            if shot and shot[0]>=tick and shot[1].get('team',{}).get('id')==tid: counts['shot_assists']+=1
        elif kind=='Carry':
            end=e.get('carry',{}).get('end_location')
            if location and end and end[0]-location[0]>=10: counts['forward_carries']+=1
        elif kind=='Shot':
            counts['shots']+=1; counts['xg']+=e.get('shot',{}).get('statsbomb_xg',0)
            counts['goals']+=int(e.get('shot',{}).get('outcome',{}).get('name')=='Goal')
        elif kind in ('Dispossessed','Miscontrol'): counts['recorded_losses']+=1
        labels={'Pass':'Передача','Carry':'Ведение','Shot':'Удар','Dispossessed':'Потеря при отборе',
                'Miscontrol':'Ошибка контроля','Dribble':'Обводка','Pressure':'Давление'}
        if kind in labels:
            rows.append({'Время':clock_label(e),'Действие':labels[kind]})
            if location: locations.append({'location':location,'label':labels[kind],'clock':clock_label(e)})
    return {'counts':dict(counts),'events':rows,'locations':locations,'yellow':pid in state['yellow'],
            'on_pitch':pid in state['players'][tid],
            'minutes':max(0,(state['cutoff']-state['entered'][pid])/60) if pid in state['players'][tid] and pid in state['entered'] else None}


def player_map(card):
    parts=[]
    for event in card['locations']:
        x,y=point(event['location'])
        title=html.escape(event['clock']+' · '+event['label'])
        color='#b73a40' if event['label'] in ('Потеря при отборе','Ошибка контроля') else '#1769aa'
        parts.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{color}" opacity=".65"><title>{title}</title></circle>')
    return field(''.join(parts),'Карта записанных событий игрока',light=True)
