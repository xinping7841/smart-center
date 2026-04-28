import json

with open('projector_brands.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('当前品牌数量:', len(data['brands']))
print('\n品牌列表:')
for b in data['brands']:
    print(f'  - {b["id"]}: {b["name"]}')
