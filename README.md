# InvoiceFlow

**SC6113 Individual Assignment: enterprise invoice payment and reconciliation DApp**

InvoiceFlow lets a merchant issue an ETH-denominated invoice to a specified customer wallet, receive an exact-value blockchain payment, independently reconcile its receipt, and withdraw merchant funds. The application uses Solidity, MetaMask / EIP-1193, ethers.js 6, Flask and SQLite.

## Report and documentation

- [8-page assignment report](docs/SC6113_InvoiceFlow_Report.pdf)
- [Chinese usage and submission guide](docs/使用说明与提交清单.md)
- [Dashboard screenshot](evidence/05-populated-dashboard.png)

Validation: 29 contract checks, 19 backend checks and 13 browser checks passed on a local EVM. Actual MetaMask extension and Sepolia validation remain pending. GitHub stores this project; the Flask application requires a separate runtime and persistent storage to run online.

## Quick start

Prerequisites: Node.js 20 or 22 LTS, Python 3.11 or 3.12, a modern browser. No public-network funds are needed for local use.

```sh
npm install --ignore-scripts
npm run compile
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell activate with `.venv\Scripts\Activate.ps1` instead. The shipped `pnpm-lock.yaml` records the original JavaScript dependency resolution; `pnpm install --ignore-scripts` is an alternative to npm. Native acceleration is optional; Ganache falls back to JavaScript.

After installation, the convenience launcher `python scripts/run_local.py` can start the local services. Alternatively, start three terminals in the project directory:

```sh
# Terminal 1: keep running
npm run chain
```

```sh
# Terminal 2: after the chain starts
npm run deploy:local
```

```sh
# Terminal 3: with the virtual environment activated
python app.py
```

Open http://127.0.0.1:5000. Select **Use local test wallets** and use Merchant wallet to issue an invoice to customer `0x70997970C51812dc3A010C7d01b50e0d17dc79C8`. Switch to Customer wallet, pay, reconcile, then switch back to Merchant wallet and withdraw. The explicit local adapter uses public development accounts on chain 31337 only; it is not MetaMask and must never be used with real money.

Restarting the chain resets its state. Run `npm run deploy:local` again; reconciliation detects changed block hashes and rebuilds its cache. The supplied development configuration is a reproducible fixture, not a public deployment.

## MetaMask on the local chain

Use an isolated test wallet. Add RPC `http://127.0.0.1:8545`, chain ID `31337`, symbol `ETH`. Import development accounts only into that isolated test wallet. The mnemonic in `scripts/local-chain.mjs` is public; never fund its derived accounts on a public chain. Select **Connect MetaMask** in the application. MetaMask signs login messages and blockchain transactions; Flask never signs payments or requests private keys.

## Sepolia deployment

A private-key-free classroom workflow is documented in `docs/REMIX_DEPLOYMENT.md`: deploy using Remix + MetaMask, then attach the successful creation transaction with `scripts/configure-sepolia.mjs`. The scripted deployment below is an alternative.

1. Create a dedicated test-only MetaMask wallet and obtain test ETH. Use the current official faucet instructions appropriate to your provider.
2. Set `SEPOLIA_RPC_URL` and `DEPLOYER_PRIVATE_KEY` in your terminal environment. `.env.example` is documentation only; this project does not automatically load `.env`.
3. Run `npm run compile` and `npm run deploy:sepolia`. Deployment rejects a chain other than 11155111.
4. Restart Flask. The browser config omits the server RPC URL and contains ABI, chain ID and contract address. The local adapter is hidden and disabled.
5. Use two separate wallets as merchant and customer; issue, pay, reconcile and withdraw.
6. Save transaction hashes, explorer screenshots, contract address and network in `docs/SEPOLIA_VERIFICATION.md`. Capture the actual MetaMask authorization and transaction dialogs.

The Sepolia policy is three confirmations. Use Refresh / Reconcile after more blocks are mined. “Confirming” and “Settled” are application policy states, not a claim of economic finality.

For HTTPS web hosting, use Gunicorn, set `SECRET_KEY` to a random secret, `COOKIE_SECURE=1`, and `TRUSTED_HOST` to the exact public hostname. Example start command: `gunicorn app:app`. Set the RPC configuration securely on the server; do not commit private keys or credential-bearing deployment files. A persistent SQLite disk is required; multiple-worker indexing and production rate limiting are outside this prototype's scope. Local demo must be false on any public deployment.

## Business rules

- An issuer and customer must be distinct non-zero wallets; amount must be positive, due time in the future.
- ID = keccak256(ABI-encoded merchant address and keccak256 invoice reference). A merchant cannot reuse a reference; different merchants can.
- Only the specified payer can pay an open, unexpired invoice. `msg.value` must match the invoice exactly. Partial payments and overpayments revert.
- Paid and cancelled invoices cannot be paid again. Only the issuer can cancel an open invoice.
- Payments increase merchant credit and total liability. Only the credited merchant can withdraw its balance.
- Withdrawal clears credit before the external call; a reentrancy lock is also applied. A failed transfer rolls back the credit change.
- The administrator can pause creation and payment, but cannot divert merchant funds or block withdrawals / cancellations.
- “Overdue” is derived from blockchain time; it does not automatically submit a transaction.

## Integrity and reconciliation

Invoice descriptions remain in SQLite, not in public contract storage. The immutable invoice stores SHA-256 of fixed-field canonical JSON: reference, description, lowercase payer, integer amountWei string and integer dueAt string. Changes to the stored JSON are detected on read. Off-chain storage is not itself encryption; this prototype uses fictitious descriptions and has no confidential enterprise-data workflow.

Metadata attachment requires a recovered issuer-wallet signature over a single-use, five-minute, origin- and chain-bound challenge, plus a session CSRF token. This is a limited personal-sign authentication scheme, not a full SIWE implementation. Jinja escapes templates; browser-rendered values are escaped; SQL uses bound parameters; CSV prefixes formula-like references.

The backend independently scans logs from the configured contract, checks the RPC chain, stores events uniquely by scope / transaction hash / log index, pins reads to a head block, matches payment events with amount and merchant, and applies a confirmation threshold. A checkpoint block-hash mismatch clears and replays the index. No client-supplied “paid=true” claim is accepted. Browser statuses and missing metadata do not authorize funds.

The cache is incremental, but the prototype reads all indexed invoices per refresh. It is designed for a small coursework dataset, not unbounded enterprise load. A public RPC outage fails closed with a retry message.

## Testing

```sh
npm run compile
npm test
# Requires the local chain running; deploys isolated fixture contracts
python -m pytest tests/test_backend.py -v --junitxml=evidence/backend-tests.xml
# Optional browser suite
npm install --no-save playwright
npx playwright install chromium
node tests/ui.cjs
```

Set `CHROME_PATH` to an existing Chrome executable if using a system Chrome instead. `PLAYWRIGHT_MODULE` optionally points to an installed Playwright module. The browser suite changes only the configured development chain; do not run it against Sepolia.

Evidence contains machine-readable contract, backend and browser results, actual screenshots and CSV export. The recorded run identifies the local EVM and injected-wallet fixtures honestly. A real MetaMask extension and Sepolia live workflow must be verified separately before claiming those tests passed.

## Structure

- `contracts/InvoiceLedger.sol`: application contract; `TestReceivers.sol`: attack / rejection fixture only.
- `app.py`: Flask API, authentication, canonical metadata and blockchain reconciliation.
- `templates/index.html`, `static/styles.css`, `static/app.js`: responsive interface and wallet operations.
- `scripts/`: compiler, deterministic local chain and network-checked deployment.
- `tests/`: contract security / liability invariant, backend integration, browser business flow.
- `artifacts/`: compiler output; `evidence/`: observed test results and screenshots.
- `docs/`: rubric coverage, demonstration script and public-network verification checklist.

## Scope and attribution

This is an ETH payment prototype. It is not an accounting system, legal tax-invoice service, audited custodial product or fiat-settlement platform. It implements no conversion rates, tax calculation, partial payment, invoice amendments, refunds or disputes. Cancellation does not release a paid invoice because payment is final under the selected business rules.

Course foundations: W3–4 Solidity (Owner, Events, Struct, Enum, Ballot, BookMarketplace); W5 Flask / SQLite; W6 access control, input checks, reentrancy and security testing. Dependencies retain their original licenses; ethers.js is vendored for offline browser loading.

Review the course's AI-assistance rules, understand the implementation and accurately disclose assistance if required. Add your own name and student ID to the report, and do not claim work or public deployments you have not verified.
