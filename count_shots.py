import json

# Adrian
with open('/mnt/c/Users/scott/Documents/liberty-basketball-analysis/data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json') as f:
    data = json.load(f)
shots = [r for r in data['rows'] if r.get('eventtype') in ('2PT', '3PT', 'FT')]
print(f'Adrian tagged shots: {len(shots)}')
for q in ['Q1','Q2','Q3','Q4']:
    qs = [r for r in shots if r.get('quarter')==q]
    print(f'  {q}: {len(qs)}')

# Notus
with open('/mnt/c/Users/scott/Documents/liberty-basketball-analysis/data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json') as f:
    data = json.load(f)
shots = [r for r in data['rows'] if r.get('eventtype') in ('2PT', '3PT', 'FT')]
print(f'Notus tagged shots: {len(shots)}')
for q in ['Q1','Q2','Q3','Q4']:
    qs = [r for r in shots if r.get('quarter')==q]
    print(f'  {q}: {len(qs)}')