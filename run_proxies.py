import yaml
import subprocess
import re

with open('config.yml', 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
#代理列表，None为不使用代理
proxies= [None,'socks5://127.0.0.1:10808','socks5://127.0.0.1:10809']

#可以顺便修改整理文件夹或其他配置
#cfg['scanner']['input_directory']='/root/media' 
cfg['other']['auto_exit']=True
for proxy in proxies:
    cfg['network']['proxy_server']=proxy
    with open('config_temp.yml', 'w', encoding='utf-8') as f:
        yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)
    jav_cmd=['javsp','-c','config_temp.yml']
    jav_result = subprocess.run(
    jav_cmd,
    capture_output=True,
    text=True,
    check=False,
    encoding='utf-8'
    )
    # print('使用代理：'+proxy)
    # print(jav_result.stdout)
    if "失败详情:" not in jav_result.stdout:
        with open('err.log', 'w', encoding='utf-8') as f:
            f.write('')
            print('ok')
        break
if "失败详情:" in jav_result.stdout:
    failed_video = re.search(r"失败详情:\s*\n(.*?)(?=\n-{10,}|\n=|\Z)", jav_result.stdout, re.DOTALL)
    with open('err.log', 'w', encoding='utf-8') as f:
        f.write(failed_video)