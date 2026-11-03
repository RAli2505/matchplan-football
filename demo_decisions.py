"""Data-free synthetic demonstration; no trained model metrics or real match claims."""
import json
from pathlib import Path
from core import snapshot
from decision_support import compare_plans,build_package
from match_insights import coach_report_html


def main():
    positions=['Goalkeeper','Right Back','Right Center Back','Left Center Back','Left Back',
               'Center Defensive Midfield','Right Center Midfield','Left Center Midfield',
               'Right Wing','Left Wing','Center Forward']
    lineups=[]; events=[]
    for tid in (1,2):
        players=[{'player_id':tid*100+i,'player_name':f'Demo {tid}-{i}','jersey_number':i} for i in range(1,15)]
        lineups.append({'team_id':tid,'team_name':f'Demo team {tid}','lineup':players})
        events.append({'type':{'name':'Starting XI'},'team':{'id':tid},'period':1,'timestamp':'00:00:00','minute':0,
            'tactics':{'formation':433,'lineup':[{'player':{'id':p['player_id'],'name':p['player_name']},
                'position':{'name':role},'jersey_number':p['jersey_number']} for p,role in zip(players,positions)]}})
    events += [{'type':{'name':'Half End'},'period':1,'timestamp':'00:45:00','minute':45},
               {'type':{'name':'Shot'},'period':2,'timestamp':'00:15:00','minute':60,'team':{'id':2},
                'location':[108,40],'shot':{'statsbomb_xg':.2,'outcome':{'name':'Goal'}}}]
    for minute in range(16,25):
        events.append({'type':{'name':'Pass'},'period':2,'timestamp':f'00:{minute:02}:00','minute':45+minute,
            'team':{'id':1},'player':{'id':106,'name':'Demo 1-6'},'location':[25,40],'under_pressure':True,
            'pass':{'outcome':{'name':'Incomplete'},'end_location':[50,40]}})
    state=snapshot(events,lineups,4500)
    roles={112:'Center Forward',113:'Center Midfield',114:'Right Back'}
    plans=compare_plans(state,1,'win',roles)
    package=build_package(state,1,'win',roles,{},'attacking',0)
    directory=Path(__file__).parent/'reports/demo'; directory.mkdir(parents=True,exist_ok=True)
    payload={'source':'SYNTHETIC DEMO — not a real match; no trained prediction provided','plans':plans,'package':package}
    (directory/'decision_demo.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    document=coach_report_html(state,1,{1:'Synthetic demo team A',2:'Synthetic demo team B'},0,package,
                              source='SYNTHETIC DEMONSTRATION. Not a real match; player names and events are fabricated for a software example')
    document=document.replace('<h1>','<h1>SYNTHETIC DEMO · ',1)
    (directory/'decision_demo.html').write_text(document,encoding='utf-8')
    print('SYNTHETIC DEMO: three plans, legal substitution, compatible roles, coach report.')
    print('No archive, network access or installed packages required. No model trained or evaluated.')
    print(directory/'decision_demo.html')


if __name__=='__main__':main()
