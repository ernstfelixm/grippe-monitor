"""Build static Pages output and copy/paste Shorthand files; no dependencies."""
import argparse
import json
from pathlib import Path
import re
import shutil

def build(base,data_url):
    data=json.loads((base/'monitor.json').read_text())
    if data.get('metric')!='AUFNAHMEN' or not data.get('weeks'):raise ValueError('Invalid dataset')
    feeds = ['index.json', 'austria.json', 'ages.json', 'regions.json', 'details.json']
    for filename in feeds:
        feed=json.loads((base/'data'/filename).read_text())
        if any(feed.get(key)!=data.get(key) for key in ['sourceSha256','retrievedAt']):
            raise ValueError('Mixed data snapshots: '+filename)
    if data_url and not re.fullmatch(r'https://[^\s<>"\x27]+',data_url):raise ValueError('Expected HTTPS data URL')
    html=(base/'chart.html').read_text().replace('data-source=""','data-source="'+data_url+'"')
    css=(base/'chart.css').read_text();js=(base/'chart.js').read_text()
    snapshot=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    section='<style>\n'+css+'\n</style>\n'+html+'\n<script type="application/json" id="kst-data">'+snapshot+'</script>'
    code='<script>\n'+js+'\n</script>'
    site=base/'site';site.mkdir(exist_ok=True)
    (site/'shorthand-section.html').write_text(section)
    (site/'shorthand-javascript.html').write_text(code)
    (site/'shorthand.html').write_text(section+code)
    (site/'index.html').write_text('<!doctype html><html lang="de-AT"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Atemwegsmonitor</title><style>body{max-width:1000px;margin:16px auto;padding:0 12px;font-family:Arial,sans-serif}</style></head><body>'+section+code+'</body></html>')
    shutil.copyfile(base/'monitor.json',site/'monitor.json')
    (site/'data').mkdir(exist_ok=True)
    for filename in feeds:shutil.copyfile(base/'data'/filename,site/'data'/filename)
    if (base/'status.json').exists():shutil.copyfile(base/'status.json',site/'status.json')
    (site/'.nojekyll').touch()
    print('Built',site)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--data-url',default='');args=ap.parse_args()
    build(Path(__file__).parent,args.data_url)
