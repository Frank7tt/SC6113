"""Portable one-command local launcher after dependency installation."""
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
node=shutil.which('node')
if not node:
    sys.exit('Node.js was not found. Install Node.js LTS and follow README Quick start.')
if not (ROOT/'node_modules/solc').exists():
    sys.exit('JavaScript dependencies missing. Run npm install --ignore-scripts first.')
try:
    import flask, web3
except ImportError:
    sys.exit('Python dependencies missing. Activate .venv and pip install -r requirements.txt.')

def rpc(method,params=None):
    req=urllib.request.Request('http://127.0.0.1:8545',data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params or []}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=2) as r:
        result=json.load(r)
    if 'error' in result:raise RuntimeError(result['error'])
    return result['result']

owned=[]
try:
    try:
        chain=int(rpc('eth_chainId'),16)
        if chain!=31337:sys.exit('Port 8545 is used by another network. Stop that service or use the manual README instructions.')
        print('Using existing local chain 31337.')
    except (OSError,TimeoutError):
        owned.append(subprocess.Popen([node,'scripts/local-chain.mjs'],cwd=ROOT))
        for _ in range(50):
            try:
                if int(rpc('eth_chainId'),16)==31337:break
            except (OSError,TimeoutError):time.sleep(.2)
        else:raise RuntimeError('Local chain did not start.')
    subprocess.run([node,'scripts/compile.mjs'],cwd=ROOT,check=True)
    cfg_path=ROOT/'deployment.json'
    needs_deploy=True
    if cfg_path.exists():
        cfg=json.loads(cfg_path.read_text())
        if cfg.get('chainId')!=31337:
            sys.exit('Existing configuration is for a public network. Preserve it and follow the explicit deploy:local instructions if switching.')
        needs_deploy=rpc('eth_getCode',[cfg['contractAddress'],'latest'])=='0x'
    if needs_deploy:subprocess.run([node,'scripts/deploy.mjs'],cwd=ROOT,check=True)
    print('Open http://127.0.0.1:5000. Press Ctrl+C here to stop services started by this launcher.')
    server=subprocess.Popen([sys.executable,'app.py'],cwd=ROOT);owned.append(server);server.wait()
except KeyboardInterrupt:
    print('\nStopping local services.')
finally:
    for p in reversed(owned):
        if p.poll() is None:p.terminate()
    for p in owned:
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill()
