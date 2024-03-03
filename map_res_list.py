"""
Usage:
    map_res_list.py [options]

Options:
    --type <str>
    --find_str <str>   
    --replace_str <str>         
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
# from docopt import docopt

def up_data():
    star_path = Path(__file__).parent
    
    star_list = []
    
    this_path = str(Path(__file__).parent)
    
    
    for file in star_path.rglob('*'):
        if 'logs' not in str(file) and '.git' not in str(file) and '__' not in str(file) and 'version.json' not in str(file) and 'star_list.json' not in str(file) and os.path.isfile(file):
            star_list.append({
                'path': str(file).replace(this_path, '').replace('\\', '/').lstrip('/'),
                'hash': hashlib.md5(file.read_bytes()).hexdigest()
            })
    
    with open('star_list.json', 'w', encoding='utf-8') as f:
        json.dump(star_list, f, ensure_ascii=False, indent=2)
    
    # 获取当前时间（UTC+8）
    current_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    
    # 生成版本号
    version = current_time.strftime("%m%d%H%M")
    
    # 创建版本号字典
    version_dict = {
        "version": version
    }
    
    # 写入到version.json文件
    with open("version.json", "w") as file:
        json.dump(version_dict, file)
    '''
    with open('config.json','r') as f:
        config = json.load(f)
        config['start'] = False
    
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    '''

def str_replace(find_str, replace_str):
    with open("requirements.txt", "r", encoding="utf-8") as f:
        content = f.read()
        content = content.replace(find_str, replace_str)
        with open("requirements.txt", "w", encoding="utf-8") as f_new:
            f_new.write(content)
    
if __name__ == '__main__':
    # args = docopt(__doc__)
    # if args.get("--type", "") == "replace":
    #     str_replace(args["--find_str"], args["--replace_str"])
    # else:
    #     up_data()
    up_data()
        
