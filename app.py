"""InvoiceFlow: read-only blockchain indexing, authenticated metadata, exact reconciliation."""
import csv
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from flask import Flask, jsonify, request, session, render_template, Response
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / 'data' / 'invoiceflow.db'
LOCK = threading.Lock()
STATUS = ['Missing', 'Open', 'Paid', 'Cancelled']

def canonical_metadata(body):
    """Identical fixed-field JSON representation in Python and JavaScript."""
    if not isinstance(body, dict):
        raise ValueError('Expected an object.')
    ref = str(body.get('reference', '')).strip()
    desc = str(body.get('description', '')).strip()
    payer = str(body.get('payer', '')).lower()
    amount = str(body.get('amountWei', ''))
    due = str(body.get('dueAt', ''))
    if not (1 <= len(ref) <= 64 and 1 <= len(desc) <= 500):
        raise ValueError('Reference or description has an invalid length.')
    if not Web3.is_address(payer) or int(payer, 16) == 0:
        raise ValueError('Invalid payer address.')
    if not amount.isdigit() or not 0 < int(amount) < 2**256:
        raise ValueError('Invalid amount.')
    if not due.isdigit() or not 0 < int(due) < 2**64:
        raise ValueError('Invalid due time.')
    # Restrict unusual control characters; unicode text is otherwise supported.
    if any(ord(c) < 32 for c in ref + desc):
        raise ValueError('Control characters are not allowed.')
    value = dict(reference=ref, description=desc, payer=payer,
                 amountWei=str(int(amount)), dueAt=str(int(due)))
    text = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return value, text, '0x' + hashlib.sha256(text.encode()).hexdigest()

def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS metadata(id TEXT PRIMARY KEY, merchant TEXT NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(scope TEXT NOT NULL, tx TEXT NOT NULL, log_index INTEGER NOT NULL, block_number INTEGER NOT NULL,
          block_hash TEXT NOT NULL, kind TEXT NOT NULL, invoice_id TEXT, account TEXT NOT NULL, amount TEXT NOT NULL,
          PRIMARY KEY(scope,tx,log_index));
        CREATE TABLE IF NOT EXISTS checkpoint(scope TEXT PRIMARY KEY, block_number INTEGER NOT NULL, block_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS auth_challenges(nonce TEXT PRIMARY KEY, message TEXT NOT NULL, issued INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0);
        ''')

def settings():
    path = ROOT / 'deployment.json'
    if not path.exists():
        raise RuntimeError('Contract not configured. Compile and deploy first; see README.')
    return json.loads(path.read_text())

def blockchain():
    cfg = settings()
    w3 = Web3(Web3.HTTPProvider(cfg['rpcUrl'], request_kwargs={'timeout': 10}))
    if w3.eth.chain_id != cfg['chainId']:
        raise RuntimeError('RPC network does not match deployment.')
    abi = json.loads((ROOT / 'artifacts' / 'InvoiceLedger.json').read_text())['abi']
    address = Web3.to_checksum_address(cfg['contractAddress'])
    if not w3.eth.get_code(address):
        raise RuntimeError('No contract at configured address. The local chain may have restarted; redeploy.')
    return cfg, w3, w3.eth.contract(address=address, abi=abi)

def hx(value):
    return Web3.to_hex(value)

def snapshot(sync=True):
    cfg, w3, contract = blockchain()
    head = w3.eth.get_block('latest')
    scope = f"{cfg['chainId']}:{cfg['contractAddress'].lower()}"
    n = head.number
    with LOCK, connect_db() as db:
        checkpoint = db.execute('SELECT * FROM checkpoint WHERE scope=?', (scope,)).fetchone()
        reset = False
        if checkpoint:
            reset = checkpoint['block_number'] > n or hx(w3.eth.get_block(checkpoint['block_number']).hash) != checkpoint['block_hash']
        if reset:
            db.execute('DELETE FROM events WHERE scope=?', (scope,))
            db.execute('DELETE FROM checkpoint WHERE scope=?', (scope,))
            checkpoint = None
        start = checkpoint['block_number'] + 1 if checkpoint else cfg['deploymentBlock']
        inserted = 0
        if sync:
            decoders = [contract.events.InvoiceCreated(), contract.events.InvoicePaid(),
                        contract.events.InvoiceCancelled(), contract.events.Withdrawal(), contract.events.PauseChanged()]
            for lo in range(start, n + 1, 1000):
                hi = min(lo + 999, n)
                logs = w3.eth.get_logs({'address': contract.address, 'fromBlock': lo, 'toBlock': hi})
                for log in logs:
                    decoded = None
                    for decoder in decoders:
                        try:
                            decoded = decoder.process_log(log)
                            break
                        except Exception:
                            continue
                    if decoded is None:
                        continue
                    args = decoded['args']
                    event_id = hx(args['id']) if 'id' in args else None
                    account = str(args.get('merchant', '')).lower()
                    cursor = db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?)',
                        (scope, hx(log.transactionHash), log.logIndex, log.blockNumber, hx(log.blockHash), decoded['event'], event_id,
                         account, str(args.get('amount', 0))))
                    inserted += cursor.rowcount
            # Detect a chain change during scanning before committing the checkpoint.
            if hx(w3.eth.get_block(n).hash) != hx(head.hash):
                raise RuntimeError('Chain changed during reconciliation; retry.')
            db.execute('INSERT OR REPLACE INTO checkpoint VALUES(?,?,?)', (scope, n, hx(head.hash)))
        events = [dict(r) for r in db.execute('SELECT * FROM events WHERE scope=? ORDER BY block_number DESC,log_index DESC', (scope,))]
        created = [e for e in events if e['kind'] == 'InvoiceCreated']
        rows = []
        for event in created:
            inv = contract.functions.getInvoice(event['invoice_id']).call(block_identifier=n)
            merchant, payer, amount, due, state, digest = inv
            meta = db.execute('SELECT * FROM metadata WHERE id=? AND merchant=?', (event['invoice_id'], merchant.lower())).fetchone()
            integrity = bool(meta and meta['digest'].lower() == hx(digest).lower()
                             and '0x' + hashlib.sha256(meta['body'].encode()).hexdigest() == hx(digest).lower())
            body = None
            if integrity:
                try:
                    body = json.loads(meta['body'])
                    integrity = isinstance(body, dict) and all(k in body for k in ['reference', 'description'])
                except (ValueError, TypeError):
                    integrity = False
            payment = next((e for e in events if e['invoice_id'] == event['invoice_id'] and e['kind'] == 'InvoicePaid'), None)
            confirmations = n - payment['block_number'] + 1 if payment else 0
            verified = bool(payment and int(payment['amount']) == amount and payment['account'] == merchant.lower() and state == 2)
            label = STATUS[state]
            if state == 1 and head.timestamp > due:
                label = 'Overdue'
            if state == 2:
                label = 'Settled' if verified and confirmations >= cfg['confirmations'] else 'Confirming' if verified else 'Mismatch'
            rows.append(dict(id=event['invoice_id'], reference=body['reference'] if integrity else event['invoice_id'][:12],
                description=body['description'] if integrity else 'Metadata unavailable or failed integrity verification',
                merchant=merchant, payer=payer, amountWei=str(amount), amountEth=Web3.from_wei(amount, 'ether').to_eng_string(),
                dueAt=due, state=state, status=label, integrity=integrity, documentHash=hx(digest),
                creationTx=event['tx'], paymentTx=payment['tx'] if payment else None, confirmations=confirmations,
                requiredConfirmations=cfg['confirmations'], reconciled=verified and confirmations >= cfg['confirmations']))
        # Consistency check includes the pinned-state reads, not just event scanning.
        if hx(w3.eth.get_block(n).hash) != hx(head.hash):
            raise RuntimeError('Chain changed while reading invoices; retry.')
    for event in events:
        event['confirmations'] = n - event['block_number'] + 1
        event.pop('scope', None)
    return dict(invoices=rows, events=events, head=n, headHash=hx(head.hash), chainTime=head.timestamp,
        indexedFrom=cfg['deploymentBlock'], newEvents=inserted, reorgRecovered=reset,
        paused=contract.functions.paused().call(block_identifier=n),
        totalLiabilityWei=str(contract.functions.totalLiability().call(block_identifier=n)))

app = Flask(__name__)
secret = os.environ.get('SECRET_KEY')
if not secret:
    secret_path = ROOT / '.secret-key'
    if not secret_path.exists():
        secret_path.write_text(secrets.token_hex(32))
        secret_path.chmod(0o600)
    secret = secret_path.read_text().strip()
app.secret_key = secret
app.config.update(MAX_CONTENT_LENGTH=8192, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1', TRUSTED_HOSTS=['localhost','127.0.0.1'])
if os.environ.get('TRUSTED_HOST'):
    app.config['TRUSTED_HOSTS'].append(os.environ['TRUSTED_HOST'])
init_db()

@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' http://127.0.0.1:8545; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response

@app.errorhandler(Exception)
def errors(exc):
    from werkzeug.exceptions import HTTPException
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.description), exc.code
    app.logger.warning('%s: %s', type(exc).__name__, exc)
    if isinstance(exc, ValueError):
        return jsonify(error=str(exc)), 400
    return jsonify(error='Blockchain service unavailable or configuration invalid. Retry or check server configuration.'), 503

@app.get('/')
def index():
    return render_template('index.html')

@app.get('/api/config')
def config():
    cfg = settings()
    abi = json.loads((ROOT / 'artifacts/InvoiceLedger.json').read_text())['abi']
    public = {k: cfg[k] for k in ['chainId','network','contractAddress','deploymentBlock','confirmations','localDemo']}
    public['abi'] = abi
    return jsonify(public)

@app.get('/api/session')
def session_info():
    return jsonify(address=session.get('address'), csrf=session.get('csrf'))

@app.post('/api/auth/challenge')
def challenge():
    nonce = secrets.token_hex(16)
    session.clear()
    session['nonce'] = nonce
    session['issued'] = int(time.time())
    cfg = settings()
    message = f"InvoiceFlow wallet authentication\nOrigin: {request.host}\nChain ID: {cfg['chainId']}\nNonce: {nonce}\nIssued at: {session['issued']}\nPurpose: edit invoice metadata only; no funds authorization."
    session['message'] = message
    with connect_db() as db:
        db.execute('DELETE FROM auth_challenges WHERE issued < ?', (int(time.time()) - 300,))
        db.execute('INSERT INTO auth_challenges(nonce,message,issued) VALUES(?,?,?)', (nonce, message, session['issued']))
    return jsonify(message=message)

@app.post('/api/auth/verify')
def verify():
    body = request.get_json(silent=True) or {}
    message = session.pop('message', None)
    issued = session.pop('issued', 0)
    nonce = session.pop('nonce', None)
    if not message or not nonce or time.time() - issued > 300:
        return jsonify(error='Challenge expired or already used.'), 401
    if f'Origin: {request.host}\nChain ID: {settings()["chainId"]}\n' not in message:
        return jsonify(error='Challenge origin or network changed.'), 401
    # Consumption is server-side: an old signed session cookie cannot replay a nonce.
    with connect_db() as db:
        consumed = db.execute('UPDATE auth_challenges SET consumed=1 WHERE nonce=? AND message=? AND issued=? AND consumed=0 AND issued>=?',
            (nonce, message, issued, int(time.time()) - 300)).rowcount
    if consumed != 1:
        return jsonify(error='Challenge expired or already used.'), 401
    try:
        address = Account.recover_message(encode_defunct(text=message), signature=body.get('signature', ''))
    except Exception:
        return jsonify(error='Invalid wallet signature.'), 401
    if address.lower() != str(body.get('address', '')).lower():
        return jsonify(error='Signature does not match the selected wallet.'), 401
    session['address'] = address.lower()
    session['csrf'] = secrets.token_hex(24)
    return jsonify(address=address, csrf=session['csrf'])

@app.post('/api/auth/logout')
def logout():
    session.clear()
    return jsonify(ok=True)

@app.post('/api/metadata/<invoice_id>')
def save_metadata(invoice_id):
    address = session.get('address')
    if not address:
        return jsonify(error='Sign in with the issuer wallet first.'), 401
    if request.headers.get('X-CSRF-Token') != session.get('csrf'):
        return jsonify(error='Invalid request token.'), 403
    if not re.fullmatch(r'0x[0-9a-fA-F]{64}', invoice_id):
        raise ValueError('Invalid invoice ID.')
    body, text, digest = canonical_metadata(request.get_json(silent=True))
    cfg, w3, contract = blockchain()
    inv = contract.functions.getInvoice(invoice_id).call()
    merchant, payer, amount, due, state, chain_digest = inv
    if merchant.lower() != address:
        return jsonify(error='Only the on-chain issuer can attach metadata.'), 403
    ref_hash = Web3.keccak(text=body['reference'])
    expected_id = hx(contract.functions.invoiceId(Web3.to_checksum_address(address), ref_hash).call())
    if (expected_id.lower() != invoice_id.lower() or payer.lower() != body['payer']
        or amount != int(body['amountWei']) or due != int(body['dueAt']) or hx(chain_digest) != digest):
        return jsonify(error='Metadata does not match the immutable on-chain invoice.'), 409
    with connect_db() as db:
        db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?,?,?)', (invoice_id.lower(), address, text, digest))
    return jsonify(ok=True, integrity=True)

@app.get('/api/invoices')
def invoices():
    data = snapshot()
    return jsonify(data)

@app.post('/api/reconcile')
def reconcile():
    # Public, read-only with respect to chain state. Scope is configured, never client-supplied.
    return jsonify(snapshot())

@app.get('/api/account/<address>')
def account(address):
    if not Web3.is_address(address):
        raise ValueError('Invalid wallet address.')
    cfg, w3, contract = blockchain()
    checksum = Web3.to_checksum_address(address)
    return jsonify(creditWei=str(contract.functions.credits(checksum).call()), balanceWei=str(w3.eth.get_balance(checksum)))

@app.get('/api/export.csv')
def export():
    data = snapshot()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Invoice ID','Reference','Merchant','Payer','Amount ETH','Status','Payment transaction','Confirmations','Metadata integrity'])
    for row in data['invoices']:
        # Prevent spreadsheet formula injection in merchant-supplied references.
        reference = row['reference']
        if reference[:1] in '=+-@':
            reference = "'" + reference
        writer.writerow([row['id'],reference,row['merchant'],row['payer'],row['amountEth'],row['status'],row['paymentTx'] or '',row['confirmations'],row['integrity']])
    return Response(buffer.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=invoiceflow-reconciliation.csv'})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5000')), debug=False)
