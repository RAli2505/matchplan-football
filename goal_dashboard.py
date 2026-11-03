"""Descriptive shot and goal maps, separate from prediction inputs."""
import html
import json
import zipfile
from core import ARCHIVE
from field_views import field, point


def records_from_events(events, match_id=None, date=''):
    records=[]
    for e in events:
        kind=e['type']['name']
        if kind not in ('Shot','Own Goal Against'): continue
        shot=e.get('shot',{})
        records.append(dict(match_id=match_id,date=date,team_id=e.get('team',{}).get('id'),
            player=e.get('player',{}).get('name','—'),minute=e.get('minute',0),second=e.get('second',0),period=e.get('period',1),
            own_goal=kind=='Own Goal Against',goal=shot.get('outcome',{}).get('name')=='Goal',
            location=e.get('location'),end=shot.get('end_location'),xg=shot.get('statsbomb_xg',0),
            play=shot.get('type',{}).get('name','Unknown'),outcome=shot.get('outcome',{}).get('name','')))
    return records


def season_records(games,tid):
    records=[]
    with zipfile.ZipFile(ARCHIVE) as z:
        names=z.namelist()
        prefix=next(n for n in names if '/data/events/' in n).split('/data/events/')[0]
        for game in games:
            if tid not in (game['home_team']['home_team_id'],game['away_team']['away_team_id']): continue
            es=json.loads(z.read(prefix+f'/data/events/{game["match_id"]}.json'))
            records.extend(records_from_events(es,game['match_id'],game['match_date']))
    return records


def select_records(records,tid,conceded=False,play='Все ситуации'):
    selected=[]
    for r in records:
        belongs = (r['team_id']==tid) if not r['own_goal'] else (r['team_id']!=tid)
        if belongs == conceded: continue
        if play=='Открытая игра' and r['play']!='Open Play': continue
        if play=='Стандарты и пенальти' and r['play']=='Open Play': continue
        selected.append(r)
    return selected


def match_goal_map(records, tid, conceded=False, show_all=False, our_name='Мы', opponent_name='Соперник'):
    """One shared frame: our team attacks right; opponents attack left in both halves."""
    color='#b73a40' if conceded else '#1769aa'
    parts=[]; rows=[]; missing=0; number=0
    for r in records:
        scoring = r['goal'] or r['own_goal']
        if not scoring and not show_all: continue
        location=r['location']
        number+=int(scoring)
        minute=f'{r["minute"]}:{r.get("second",0):02}'
        if scoring:
            rows.append({'№ на поле':number,'Время':minute,'Игрок':r['player'],
                         'Событие':'Автогол' if r['own_goal'] else 'Гол',
                         'Тайм':r.get('period',1),'xG':None if r['own_goal'] else round(r['xg'],3),
                         'Точка на поле':'нет координат' if not location else 'событие автогола' if r['own_goal'] else 'место удара'})
        if not location:
            missing+=int(scoring); continue
        x,y=location[:2]
        if r['team_id'] != tid: x,y=120-x,80-y
        a,b=point([x,y])
        if scoring:
            title=html.escape(f'{number}. {r["player"]} · {minute}'+(' · автогол' if r['own_goal'] else ''))
            if r['own_goal']:
                parts.append(f'<path d="M{a} {b-13}L{a+13} {b}L{a} {b+13}L{a-13} {b}Z" fill="{color}" stroke="#123a32"><title>{title}</title></path>')
            else:
                end=r.get('end')
                if end and len(end)>=2:
                    ex,ey=end[:2]
                    if r['team_id'] != tid: ex,ey=120-ex,80-ey
                    c,d=point([max(0,min(120,ex)),max(0,min(80,ey))])
                    parts.append(f'<path d="M{a} {b}L{c} {d}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="5 4" opacity=".65"/>')
                parts.append(f'<circle cx="{a}" cy="{b}" r="13" fill="{color}" stroke="#123a32" stroke-width="2"><title>{title}</title></circle>')
            parts.append(f'<text x="{a}" y="{b+5}" text-anchor="middle" fill="white" font-size="14" font-weight="bold">{number}</text>')
        else:
            parts.append(f'<circle cx="{a}" cy="{b}" r="4" fill="#d3e2dc" opacity=".55"/>')
    target='НАШИ ВОРОТА' if conceded else 'ВОРОТА СОПЕРНИКА'
    label_x=90 if conceded else 510
    parts.append(f'<rect x="{label_x-78}" y="7" width="156" height="25" rx="5" fill="#f2f5f8" stroke="#ccd6de"/>'
                 f'<text x="{label_x}" y="24" text-anchor="middle" fill="{color}" font-size="12" font-weight="bold">{target}</text>')
    if not rows:
        parts.append('<rect x="120" y="175" width="360" height="65" rx="10" fill="#f2f5f8" stroke="#ccd6de"/>'
                     '<text x="300" y="202" text-anchor="middle" fill="#243b4d" font-size="20">Голов пока нет</text>'
                     '<text x="300" y="223" text-anchor="middle" fill="#526575" font-size="12">До выбранной минуты матча</text>')
    title='Голы соперника в наши ворота' if conceded else 'Наши голы в ворота соперника'
    drawing=field(''.join(parts),title,light=True)
    drawing=drawing.replace('Направление атаки →', 'Соперник атакует ← · Мы атакуем →')
    return drawing,rows,missing


def zone_map(records,conceded=False,show_all=False,mirror=False):
    shots=[r for r in records if not r['own_goal']]
    color='#d55b62' if conceded else '#4288cf'
    parts=[]; labels=[]
    zones=[]
    x_bins=((60,102,'До штрафной'),(102,114,'Штрафная'),(114,120.01,'У ворот'))
    y_bins=((0,26.67,'Левый край'),(26.67,53.33,'Центр'),(53.33,80.01,'Правый край'))
    max_xg=max((sum(r['xg'] for r in shots if r['location'] and lo<=r['location'][0]<hi
                   and bottom<=r['location'][1]<top) for lo,hi,_ in x_bins for bottom,top,_ in y_bins),default=0)
    def p(location):
        if mirror:
            return 20+(120-location[0])/60*560,20+(80-location[1])/80*390
        return 20+(location[0]-60)/60*560,20+location[1]/80*390
    for col,(lo,hi,label) in enumerate(x_bins):
        for row,(bottom,top,side) in enumerate(y_bins):
            rs=[r for r in shots if r['location'] and lo<=r['location'][0]<hi and bottom<=r['location'][1]<top]
            goals=sum(r['goal'] for r in rs)
            xg=sum(r['xg'] for r in rs)
            x,y=p([lo,bottom]); xx,yy=p([min(hi,120),min(top,80)])
            x,xx=sorted((x,xx)); y,yy=sorted((y,yy))
            opacity=.06+.6*xg/max_xg if max_xg else .06
            parts.append(f'<rect x="{x}" y="{y}" width="{xx-x}" height="{yy-y}" fill="{color}" fill-opacity="{opacity}" stroke="#a9b8c2" stroke-width="1"/>')
            cx,cy=(x+xx)/2,(y+yy)/2
            width=min(100,xx-x-8)
            labels.append(f'<rect x="{cx-width/2}" y="{cy-39}" width="{width}" height="78" rx="6" fill="white" opacity=".82"/>'
                          f'<text x="{cx}" y="{cy-18}" text-anchor="middle" fill="#172d48" font-size="20" font-weight="bold">{xg:.2f}</text>'
                          f'<text x="{cx}" y="{cy-3}" text-anchor="middle" fill="#364f62" font-size="12">xG</text>'
                          f'<text x="{cx}" y="{cy+14}" text-anchor="middle" fill="#364f62" font-size="11">{goals} гол.</text>'
                          f'<text x="{cx}" y="{cy+30}" text-anchor="middle" fill="#364f62" font-size="11">{len(rs)} уд.</text>')
            zones.append({'Зона':label+' · '+side,'Голы':goals,'Удары':len(rs),'xG':round(xg,2)})
    for r in shots:
        if not r['location'] or r['location'][0]<60 or (not show_all and not r['goal']): continue
        x,y=p(r['location'])
        parts.append(f'<circle cx="{x}" cy="{y}" r="{5 if r["goal"] else 3}" fill="{color if r["goal"] else "#d8e6e3"}" stroke="#173b35"><title>{html.escape(r["player"])} · {r["minute"]} мин · xG {r["xg"]:.2f}</title></circle>')
    far=[r for r in shots if r['location'] and r['location'][0]<60]
    zones.append({'Зона':'Со своей половины','Голы':sum(r['goal'] for r in far),'Удары':len(far),'xG':round(sum(r['xg'] for r in far),2)})
    unknown=[r for r in shots if not r['location']]
    zones.append({'Зона':'Без координат','Голы':sum(r['goal'] for r in unknown),'Удары':len(unknown),'xG':round(sum(r['xg'] for r in unknown),2)})
    outline='M20 20H580V410H20ZM188 118V312H20 M76 171V259H20' if mirror else 'M20 20H580V410H20ZM412 118V312H580 M524 171V259H580'
    orientation='Наши ворота слева · атаки соперника ←' if mirror else 'Наши ворота справа · обзор атак соперника →' if conceded else 'Ворота соперника справа · наши атаки →'
    svg=('<svg role="img" aria-label="Зоны голов на атакующей половине поля" viewBox="0 0 600 440" width="100%" xmlns="http://www.w3.org/2000/svg">'
         '<rect width="600" height="440" rx="14" fill="#ffffff"/>'
         f'<path d="{outline}" fill="none" stroke="#869ba7" stroke-width="2"/>'
         f'<text x="300" y="432" text-anchor="middle" fill="#364f62" font-size="12">{orientation}</text>')
    return svg+''.join(parts)+''.join(labels)+'</svg>',zones


def goalmouth(records):
    points=[]
    for r in records:
        end=r['end']
        if not r['goal'] or r['own_goal'] or not end or len(end)<3: continue
        if 36<=end[1]<=44 and 0<=end[2]<=2.67:
            points.append((end[1],end[2],r))
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 210" width="100%" role="img" aria-label="Куда забиты голы в створ"><rect width="500" height="210" rx="12" fill="#ffffff"/>'
    for x in range(4): svg+=f'<path d="M{35+x*143.33} 30V175" stroke="#9caeb2" stroke-width="{3 if x in (0,3) else 1}"/>'
    for y in range(4): svg+=f'<path d="M35 {30+y*48.33}H465" stroke="#9caeb2" stroke-width="{3 if y in (0,3) else 1}"/>'
    for y,z,r in points:
        x=35+(y-36)/8*430; yy=175-z/2.67*145
        svg+=f'<circle cx="{x}" cy="{yy}" r="6" fill="#1769aa"><title>{html.escape(r["player"])}</title></circle>'
    return svg+'<text x="250" y="200" text-anchor="middle" fill="#364f62" font-size="12">Вид на ворота со стороны бьющего</text></svg>',len(points)
