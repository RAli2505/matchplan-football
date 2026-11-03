"""Visible possession chains ending in shots. No inferred passes or tracking positions."""
import html
from core import clock_label
from field_views import field,point


def attack_chains(state,tid,opponent=False,window=900):
    target=next(t for t in state['players'] if t!=tid) if opponent else tid
    visible=[(t,e) for t,e in state['visible'] if t<=state['cutoff']]
    result=[]
    for index,(tick,shot) in enumerate(visible):
        if shot['type']['name']!='Shot' or shot.get('team',{}).get('id')!=target: continue
        if window and tick<state['cutoff']-window: continue
        possession=shot.get('possession')
        chain=[]
        for t,e in visible[max(0,index-100):index+1]:
            if tick-t>25 or e.get('period')!=shot.get('period'): continue
            if possession is None and e is not shot: continue
            if possession is not None and e.get('possession')!=possession: continue
            if e.get('team',{}).get('id')!=target: continue
            kind=e['type']['name']
            if kind not in ('Pass','Carry','Dribble','Ball Recovery','Shot'): continue
            end=e.get('pass' if kind=='Pass' else 'carry' if kind=='Carry' else 'shot',{}).get('end_location')
            chain.append({'Время':clock_label(e),'Игрок':e.get('player',{}).get('name','—'),
                'Действие':{'Pass':'Передача','Carry':'Ведение','Dribble':'Обводка','Ball Recovery':'Возврат мяча','Shot':'Удар'}[kind],
                'start':e.get('location'),'end':end,'kind':kind,
                'successful':kind!='Pass' or not e.get('pass',{}).get('outcome')})
        result.append({'id':shot.get('id',f'{shot.get("period")}_{tick}_{index}'),'time':clock_label(shot),
            'shooter':shot.get('player',{}).get('name','—'),'xg':shot.get('shot',{}).get('statsbomb_xg',0),
            'goal':shot.get('shot',{}).get('outcome',{}).get('name')=='Goal','opponent':opponent,
            'events':chain[-12:],'truncated':len(chain)>12,'possession_known':possession is not None})
    return list(reversed(result))


def chain_diagram(chain):
    parts=[]; color='#b73a40' if chain['opponent'] else '#1769aa'
    def xy(loc):
        x,y=loc[:2]
        return point([120-x,80-y] if chain['opponent'] else [x,y])
    for number,event in enumerate(chain['events'],1):
        if not event['start']: continue
        x,y=xy(event['start'])
        if event['end'] and len(event['end'])>=2:
            xx,yy=xy(event['end'])
            dash='6 4' if event['kind']=='Shot' or not event['successful'] else ''
            parts.append(f'<path d="M{x} {y}L{xx} {yy}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}"/>')
        title=html.escape(event['Время']+' · '+event['Игрок']+' · '+event['Действие'])
        parts.append(f'<circle cx="{x}" cy="{y}" r="10" fill="{color}"><title>{title}</title></circle>'
                     f'<text x="{x}" y="{y+4}" fill="white" font-size="11" text-anchor="middle">{number}</text>')
    return field(''.join(parts),'Записанная цепочка атаки до удара',light=True)
