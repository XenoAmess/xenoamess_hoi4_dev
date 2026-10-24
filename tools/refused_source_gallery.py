"""Build an offline local gallery of original inputs for service-refused calls."""
import argparse
from datetime import datetime,timedelta,timezone
from html import escape
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from PIL import Image


HEAD='''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>钢奶龙心 · 服务拒绝图览</title><style>
*{box-sizing:border-box}body{margin:0;background:#14161b;color:#eef0f5;font:15px/1.6 "Microsoft YaHei",sans-serif}main{max-width:1560px;margin:auto;padding:28px}h1{margin:0 0 8px;font-size:28px}p{margin:8px 0;color:#c3c8d2}a{color:#f3cd75}header{margin-bottom:24px}.toolbar{position:sticky;top:0;background:#14161bf2;padding:12px 0;z-index:2;display:flex;gap:16px;align-items:center;flex-wrap:wrap}input{width:min(560px,100%);padding:12px 16px;border:1px solid #51586a;border-radius:8px;background:#20242d;color:white;font:inherit}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:18px}.card{background:#20242d;border:1px solid #3c4250;border-radius:12px;padding:16px;min-width:0}.card[hidden]{display:none}h2{font-size:17px;overflow-wrap:anywhere;margin:8px 0}.badge{color:#ffd08b;font-size:13px}.original{display:flex;height:260px;align-items:center;justify-content:center;border-radius:8px;background:repeating-conic-gradient(#e9e9e9 0% 25%,#cbd0d5 0% 50%) 50%/20px 20px}.original img{max-width:100%;max-height:246px;object-fit:contain;image-rendering:pixelated}.mono{font-family:Consolas,monospace;font-size:12px;overflow-wrap:anywhere;color:#b6bfce}.caption{font-size:13px;color:#ccd1db}summary{cursor:pointer;color:#f3cd75;padding:8px 0}details{border-top:1px solid #3c4250;margin-top:10px}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto;background:#151820;padding:12px;border-radius:6px;font:12px/1.6 Consolas,"Microsoft YaHei",monospace}.inputs figure{margin:12px 0}.inputs img{max-width:100%;max-height:230px;object-fit:contain;background:#d8dce1}.footer{margin-top:28px;font-size:12px;color:#929bac}button{font:inherit;cursor:pointer;background:#343c4b;color:#eef0f5;border:1px solid #535e72;border-radius:6px;padding:9px 14px}
</style><main>'''
TAIL='''<script>
const search=document.getElementById('search');const cards=[...document.querySelectorAll('.card')];
search.addEventListener('input',()=>{const q=search.value.trim().toLowerCase();let n=0;for(const card of cards){card.hidden=!card.dataset.search.includes(q);if(!card.hidden)n++;}document.getElementById('visible').textContent=n;});
document.getElementById('clear').addEventListener('click',()=>{search.value='';search.dispatchEvent(new Event('input'));search.focus();});
</script></main></html>'''


def build_gallery(audit_path,output):
    audit=read_json(audit_path)
    records=[r for r in audit['records'] if r['result']=='service_refusal']
    assert records and len({r['source_sha256'] for r in records})==len(records)
    audit_sha=file_sha256(audit_path);now=utc_now();parts=[HEAD]
    parts.append(f'<header><h1>本轮 {len(records)} 项服务拒绝</h1><p>这轮服务未返回新图片。下方卡片展示每项请求的原图；点击原图可打开本机 PNG。</p><p>展开卡片可查看实际输入、完整提示词和服务回执。原图与输入仅从本机文件读取。</p><div class="toolbar"><input id="search" type="search" placeholder="搜索文件名、路径或来源 SHA" aria-label="搜索原图"><button id="clear">清空</button><span>显示 <b id="visible">{len(records)}</b> / {len(records)}</span></div></header><section class="grid">')
    proofs=[]
    mascot=(ROOT/'mod_nailong/assets/reference/naiwa.png').resolve()
    for n,r in enumerate(records,1):
        key=r['source_sha256'];job=r['full_actual_job'];verification=r['actual_request_verification']
        refs=[Path(p).resolve() for p in job['references']]
        expected=verification['input_sha256'];assert len(refs)==len(expected)
        actual=[file_sha256(p) for p in refs];assert actual==expected,'Actual request input bytes changed'
        original=Path(job.get('original',ROOT/f'runtime/references/{key}.png')).resolve()
        assert original in refs,'Main original must be an actual unchanged request input'
        with Image.open(original) as image:original_size=image.size
        source=job.get('source',original.name);label=Path(source).stem
        local=datetime.fromisoformat(r['actual_returned_at_utc']).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        parts.append(f'<article class="card" data-search="{escape((source+" "+key).lower(),quote=True)}"><div class="badge">{n:02d} · 服务拒绝 · 本轮额外第 1 次</div><h2>{escape(label)}</h2><a class="original" href="{escape(original.as_uri(),quote=True)}" target="_blank" rel="noopener"><img loading="lazy" src="{escape(original.as_uri(),quote=True)}" alt="{escape(label,quote=True)} 原图"></a><div class="caption">原图 · {original_size[0]} × {original_size[1]} · 点击查看</div><div class="mono">{escape(source)}<br>来源 SHA：{key}</div><p class="caption">回执：北京时间 {local}<br>累计冷却重试：{r["cumulative_retry_number"]} 次</p><details><summary>实际输入（按调用顺序）</summary><div class="inputs">')
        for i,(path,sha) in enumerate(zip(refs,actual),1):
            role='原图' if path==original else '用户奶龙参考图' if path==mascot else '旧生成图或其他实际编辑输入'
            with Image.open(path) as image:size=image.size
            uri=escape(path.as_uri(),quote=True)
            parts.append(f'<figure><figcaption>输入 {i} · {role} · {size[0]} × {size[1]}</figcaption><a href="{uri}" target="_blank" rel="noopener"><img loading="lazy" src="{uri}" alt="输入 {i}：{role}"></a><div class="mono">{escape(str(path))}<br>SHA256：{sha}</div></figure>')
        parts.append(f'</div></details><details><summary>完整实际提示词</summary><pre>{escape(job["prompt"])}</pre></details><details><summary>服务拒绝回执</summary><pre>{escape(r.get("error") or "服务拒绝；完整回执见逐项审计。")}</pre><div class="mono">UTC：{escape(r["actual_returned_at_utc"])}<br>日志 attempt：{r["extra_attempt_number"]}</div></details></article>')
        proofs.append({'source_sha256':key,'original':str(original),'ordered_input_paths':[str(p) for p in refs],'ordered_input_sha256':actual})
    parts.append(f'</section><div class="footer">钢奶龙心 · 本机图览 · {escape(now)} UTC<br>机器：{escape(machine_id())}<br>审计文件：{escape(str(audit_path))}<br>审计 SHA256：{audit_sha}<br>此页展示原图及实际请求输入，不表示生成成功、美术通过或游戏显示验收。</div>')
    parts.append(TAIL);document=''.join(parts)
    assert document.count('<article class="card"')==len(records)
    assert 'src="http' not in document and 'href="http' not in document
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(document,encoding='utf-8',newline='\n')
    receipt=output.with_suffix('.json')
    write_json(receipt,{'machine_id':machine_id(),'observed_at_utc':now,'audit':str(audit_path),'audit_sha256':audit_sha,'html':str(output),'html_sha256':file_sha256(output),'source_cards':len(records),'ordered_input_positions_verified':sum(len(p['ordered_input_paths']) for p in proofs),'inputs':proofs,'scope':'Local original-input viewer only. No game originals embedded/uploaded, no new image generation or visual approval; all local actual input bytes checked.'})
    return {'html':str(output),'receipt':str(receipt),'cards':len(records),'ordered_inputs_verified':sum(len(p['ordered_input_paths']) for p in proofs)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',default='mod_nailong/data/extra-retry-rounds/20261024-exhausted-high-31-completed.json')
    parser.add_argument('--output',default='runtime/reports/extra31-service-refusals/index.html')
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args();audit=(ROOT/args.audit).resolve();output=(ROOT/args.output).resolve()
    assert output.is_relative_to((ROOT/'runtime').resolve()),'Local game-input gallery must stay in ignored runtime'
    result=build_gallery(audit,output);print(json.dumps(result,ensure_ascii=True),flush=True)
    if args.open:os.startfile(str(output))


if __name__=='__main__':main()
