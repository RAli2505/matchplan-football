"""Independent vertical goal views inspired by the supplied football-intelligence UI.

Source archive has no license notice; no original JS/CSS is vendored here.
Raw StatsBomb values and cutoff selection remain owned by goal_dashboard/app.
"""
import html
import math

X_EDGES=(60,84,102,114,120)
Y_EDGES=(0,18,30,50,62,80)


def valid_location(raw):
    return (isinstance(raw,(list,tuple)) and len(raw)>=2 and
            all(isinstance(v,(float,int)) and math.isfinite(v) for v in raw[:2]) and
            0<=raw[0]<=120 and 0<=raw[1]<=80)


def position(location,conceded=False):
    x,y=location[:2]
    # Our right flank stays on the right in both panels.
    return (40+(80-y)*6,48+(x-60)*6) if conceded else (40+y*6,48+(120-x)*6)


def vertical_goal_view(records,conceded=False,mode='zones',show_all=False):
    shots=[r for r in records if not r['own_goal']]
    color='#c73c40' if conceded else '#2876ca'
    cells=[]; rows=[]
    for i,(lo,hi) in enumerate(zip(X_EDGES,X_EDGES[1:])):
        for j,(left,right) in enumerate(zip(Y_EDGES,Y_EDGES[1:])):
            rs=[r for r in shots if valid_location(r['location']) and
                lo<=r['location'][0] and (r['location'][0]<hi or i==3 and r['location'][0]==hi) and
                left<=r['location'][1] and (r['location'][1]<right or j==4 and r['location'][1]==right)]
            xg=sum(r['xg'] for r in rs); goals=sum(r['goal'] for r in rs)
            side=('Левый фланг','Левый полуфланг','Центр','Правый полуфланг','Правый фланг')[j]
            if conceded: side=('Правый фланг','Правый полуфланг','Центр','Левый полуфланг','Левый фланг')[j]
            name=('Дальняя зона','Перед штрафной','Штрафная','У ворот')[i]+' · '+side
            rows.append({'Зона':name,'Голы':goals,'Удары':len(rs),'xG':round(xg,4)})
            cells.append((lo,hi,left,right,xg,goals,len(rs)))
    for title,predicate in [('Со своей половины',lambda r:valid_location(r['location']) and r['location'][0]<60),
                            ('Без координат',lambda r:not valid_location(r['location']))]:
        rs=[r for r in shots if predicate(r)]
        rows.append({'Зона':title,'Голы':sum(r['goal'] for r in rs),'Удары':len(rs),'xG':round(sum(r['xg'] for r in rs),4)})
    fill=[]; labels=[]; maximum=max((c[4] for c in cells),default=0)
    if mode=='zones':
        for lo,hi,left,right,xg,goals,count in cells:
            a,b=position((lo,left),conceded),position((hi,right),conceded)
            x,y=min(a[0],b[0]),min(a[1],b[1]); w,h=abs(a[0]-b[0]),abs(a[1]-b[1])
            opacity=.04+.66*xg/maximum if maximum else .04
            fill.append(f'<rect x="{x+1}" y="{y+1}" width="{w-2}" height="{h-2}" rx="4" fill="{color}" fill-opacity="{opacity:.3f}"><title>xG {xg:.4f}; ударов {count}; голов {goals}</title></rect>')
            ink='#fff' if maximum and xg/maximum>.55 else '#172b3e'
            labels.append(f'<text x="{x+w/2}" y="{y+h/2+1}" text-anchor="middle" font-size="16" font-weight="650" fill="{ink}">{xg:.2f}</text>'
                          f'<text x="{x+w/2}" y="{y+h/2+14}" text-anchor="middle" font-size="9" fill="{ink}">{count} уд. / {goals} гол.</text>')
    else:
        number=0
        for r in records:
            if r['own_goal'] or r['goal']: number+=1
            if mode=='goals' and not(r['own_goal'] or r['goal'] or show_all): continue
            if not valid_location(r['location']): continue
            location=r['location'][:2]
            if r['own_goal']: location=(120-location[0],80-location[1])
            if location[0]<60: continue
            x,y=position(location,conceded); radius=4+17*math.sqrt(max(0,r['xg']))
            title=html.escape(f'{r["player"]} · {r["minute"]} мин · '+('автогол' if r['own_goal'] else f'xG {r["xg"]:.3f}'))
            if r['own_goal']:
                fill.append(f'<path d="M{x} {y-7}l7 7 -7 7 -7 -7Z" fill="{color}"><title>{title}</title></path>')
            else:
                fill.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{color if r["goal"] else "#fcfcfb"}" fill-opacity=".85" stroke="{color if r["goal"] else "#747974"}" stroke-width="1.5"><title>{title}</title></circle>')
            if mode=='goals' and (r['goal'] or r['own_goal']):
                labels.append(f'<text x="{x+radius+4}" y="{y+4}" font-size="12" font-weight="700" fill="#172b3e">{number}</text>')
    # Pitch markings drawn after tiles, then labels above markings.
    def rect(lo,hi,left,right):
        a,b=position((lo,left),conceded),position((hi,right),conceded)
        return f'<rect x="{min(a[0],b[0])}" y="{min(a[1],b[1])}" width="{abs(a[0]-b[0])}" height="{abs(a[1]-b[1])}"/>'
    spot=position((108,40),conceded); goal_y=408 if conceded else 48
    outline=(f'<g fill="none" stroke="#aab0aa" stroke-width="1.4">{rect(60,120,0,80)}{rect(102,120,18,62)}{rect(114,120,30,50)}'
             f'<rect x="256" y="{goal_y if conceded else goal_y-12}" width="48" height="12"/>'
             f'<circle cx="{spot[0]}" cy="{spot[1]}" r="2" fill="#aab0aa"/></g>')
    heading='Наши ворота ↓' if conceded else 'Ворота соперника ↑'
    return ('<svg role="img" aria-label="Зоны голов на атакующей половине поля — вертикальная карта" '
            'viewBox="0 0 560 458" width="100%" style="max-height:580px;display:block;margin:auto" xmlns="http://www.w3.org/2000/svg">'
            '<rect width="560" height="458" rx="12" fill="#fcfcfb"/>'
            f'<text x="280" y="23" text-anchor="middle" fill="#27362f" font-size="13" font-weight="600">{heading}</text>'
            +''.join(fill)+outline+''.join(labels)+
            '<text x="40" y="446" fill="#687269" font-size="11">Наш левый фланг</text>'
            '<text x="520" y="446" text-anchor="end" fill="#687269" font-size="11">Наш правый фланг</text></svg>'),rows
