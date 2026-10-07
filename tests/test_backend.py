import hashlib
import json
import sys
import time
from pathlib import Path
import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as module
Account.enable_unaudited_hdwallet_features()
MNEMONIC = 'test test test test test test test test test test test junk'

@pytest.fixture()
def env(tmp_path, monkeypatch):
    w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
    artifact = json.loads((module.ROOT / 'artifacts/InvoiceLedger.json').read_text())
    accounts = w3.eth.accounts
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.contract(abi=artifact['abi'],bytecode=artifact['bytecode']).constructor().transact({'from':accounts[0]}))
    cfg = dict(chainId=31337,network='Test fixture',rpcUrl='http://127.0.0.1:8545',contractAddress=receipt.contractAddress,
        deploymentBlock=receipt.blockNumber,confirmations=2,localDemo=True)
    monkeypatch.setattr(module,'settings',lambda:cfg)
    monkeypatch.setattr(module,'DB_PATH',tmp_path/'test.db')
    module.init_db()
    module.app.config['TESTING']=True
    ledger=w3.eth.contract(address=receipt.contractAddress,abi=artifact['abi'])
    return dict(w3=w3,ledger=ledger,cfg=cfg,accounts=accounts,client=module.app.test_client())

def login(env,index=0):
    client=env['client'];message=client.post('/api/auth/challenge').json['message']
    wallet=Account.from_mnemonic(MNEMONIC,account_path=f"m/44'/60'/0'/0/{index}")
    signature=Account.sign_message(encode_defunct(text=message),wallet.key).signature.hex()
    response=client.post('/api/auth/verify',json={'address':wallet.address,'signature':signature})
    assert response.status_code==200
    return response.json['csrf']

def create(env,ref='INV-BACKEND',description='October consulting'):
    w3,ledger,accounts=env['w3'],env['ledger'],env['accounts']
    body={'reference':ref,'description':description,'payer':accounts[1].lower(),'amountWei':'10000000000000000','dueAt':str(w3.eth.get_block('latest').timestamp+10000)}
    _,_,digest=module.canonical_metadata(body)
    ref_hash=Web3.keccak(text=ref)
    invoice=Web3.to_hex(ledger.functions.invoiceId(accounts[0],ref_hash).call())
    tx=ledger.functions.createInvoice(ref_hash,accounts[1],int(body['amountWei']),int(body['dueAt']),digest).transact({'from':accounts[0]})
    w3.eth.wait_for_transaction_receipt(tx)
    return invoice,body

def pay(env,invoice):
    tx=env['ledger'].functions.payInvoice(invoice).transact({'from':env['accounts'][1],'value':10**16})
    return env['w3'].eth.wait_for_transaction_receipt(tx)

def test_dashboard_and_security_headers(env):
    r=env['client'].get('/')
    assert r.status_code==200 and b'InvoiceFlow' in r.data
    assert "script-src 'self'" in r.headers['Content-Security-Policy']
    assert r.headers['X-Frame-Options']=='DENY'

def test_config_excludes_rpc_credentials(env):
    r=env['client'].get('/api/config').json
    assert r['chainId']==31337 and 'rpcUrl' not in r and 'abi' in r

def test_signature_authentication_and_nonce_replay(env):
    c=env['client'];message=c.post('/api/auth/challenge').json['message'];wallet=Account.from_mnemonic(MNEMONIC)
    signature=Account.sign_message(encode_defunct(text=message),wallet.key).signature.hex()
    body={'address':wallet.address,'signature':signature}
    old_cookie=c.get_cookie('session').value
    assert c.post('/api/auth/verify',json=body).status_code==200
    # Restore the PRE-verification cookie to test real stateless-cookie replay.
    c.set_cookie('session',old_cookie)
    assert c.post('/api/auth/verify',json=body).status_code==401

def test_invalid_signature_rejected(env):
    env['client'].post('/api/auth/challenge')
    assert env['client'].post('/api/auth/verify',json={'address':env['accounts'][0],'signature':'0x00'}).status_code==401

def test_expired_challenge_rejected(env):
    c=env['client'];c.post('/api/auth/challenge')
    with c.session_transaction() as s:s['issued']=int(time.time())-301
    assert c.post('/api/auth/verify',json={}).status_code==401

def test_unauthenticated_metadata_rejected(env):
    invoice,body=create(env)
    assert env['client'].post('/api/metadata/'+invoice,json=body).status_code==401

def test_csrf_token_required(env):
    invoice,body=create(env);login(env)
    assert env['client'].post('/api/metadata/'+invoice,json=body).status_code==403

def test_nonissuer_cannot_attach_metadata(env):
    invoice,body=create(env);token=login(env,1)
    assert env['client'].post('/api/metadata/'+invoice,json=body,headers={'X-CSRF-Token':token}).status_code==403

def test_metadata_digest_matches_and_tampering_rejected(env):
    invoice,body=create(env);token=login(env)
    c=env['client'];headers={'X-CSRF-Token':token}
    assert c.post('/api/metadata/'+invoice,json=body,headers=headers).status_code==200
    assert c.get('/api/invoices').json['invoices'][0]['integrity'] is True
    body['description']='changed'
    assert c.post('/api/metadata/'+invoice,json=body,headers=headers).status_code==409

def test_database_tampering_detected_on_read(env):
    invoice,body=create(env);token=login(env)
    env['client'].post('/api/metadata/'+invoice,json=body,headers={'X-CSRF-Token':token})
    with module.connect_db() as db:db.execute('UPDATE metadata SET body=? WHERE id=?', ('corrupted, not JSON',invoice))
    result=env['client'].get('/api/invoices').json['invoices'][0]
    assert result['integrity'] is False and result['reference']==invoice[:12]

def test_reconciliation_idempotency(env):
    invoice,_=create(env);pay(env,invoice)
    first=env['client'].post('/api/reconcile').json
    second=env['client'].post('/api/reconcile').json
    assert len(first['events'])==len(second['events'])==2
    assert second['newEvents']==0

def test_confirmation_threshold_and_exact_settlement(env):
    invoice,_=create(env);pay(env,invoice)
    first=env['client'].get('/api/invoices').json['invoices'][0]
    assert first['status']=='Confirming' and not first['reconciled']
    env['w3'].provider.make_request('evm_mine',[])
    second=env['client'].get('/api/invoices').json['invoices'][0]
    assert second['status']=='Settled' and second['reconciled'] and second['confirmations']==2

def test_chain_rollback_rebuilds_index(env):
    invoice,_=create(env)
    snapshot=env['w3'].provider.make_request('evm_snapshot',[])['result']
    pay(env,invoice)
    assert len(env['client'].get('/api/invoices').json['events'])==2
    env['w3'].provider.make_request('evm_revert',[snapshot])
    result=env['client'].post('/api/reconcile').json
    assert result['reorgRecovered'] and len(result['events'])==1
    assert result['invoices'][0]['status']=='Open' and result['invoices'][0]['paymentTx'] is None

def test_csv_formula_injection_prevented(env):
    invoice,body=create(env,ref='=DANGEROUS()');token=login(env)
    env['client'].post('/api/metadata/'+invoice,json=body,headers={'X-CSRF-Token':token})
    r=env['client'].get('/api/export.csv')
    assert r.status_code==200 and "'=DANGEROUS()" in r.text

def test_invalid_metadata_input(env):
    invoice,body=create(env);token=login(env);body['amountWei']='-1'
    r=env['client'].post('/api/metadata/'+invoice,json=body,headers={'X-CSRF-Token':token})
    assert r.status_code==400

def test_invalid_wallet_and_invoice_identifier(env):
    assert env['client'].get('/api/account/invalid').status_code==400
    token=login(env)
    assert env['client'].post('/api/metadata/invalid',json={},headers={'X-CSRF-Token':token}).status_code==400

def test_no_client_payment_claim_endpoint(env):
    assert env['client'].post('/api/payments',json={'paid':True,'transactionHash':'fake'}).status_code==404

def test_wrong_rpc_chain_fails_closed(env):
    env['cfg']['chainId']=11155111
    assert env['client'].get('/api/invoices').status_code==503

def test_unicode_canonicalization():
    body={'reference':'INV-中文','description':'咨询服务','payer':'0x'+'1'*40,'amountWei':'001','dueAt':'123'}
    normalized,text,digest=module.canonical_metadata(body)
    assert normalized['amountWei']=='1' and '中文' in text
    assert digest=='0x'+hashlib.sha256(text.encode('utf-8')).hexdigest()
