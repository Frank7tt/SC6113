# Rubric coverage and review guide

This guide maps implemented evidence to the assignment; it does not predict a grade.

| Criterion | Marks | Implemented evidence |
|---|---:|---|
| Problem definition and objectives | 10 | SME accounts-receivable scenario, exact settlement and independent reconciliation objectives; report pages 1–2 |
| Smart contract design | 20 | Immutable invoice struct, namespaced IDs, exact payment, caller authorization, state transitions, pull withdrawal, pause scope, CEI / lock; pages 3–4; contract tests |
| DApp functionality | 25 | Wallet connection, issue, pay, cancel, withdraw, transaction receipt, history, confirmations, reconciliation and CSV; browser screenshots and tests |
| Frontend user interface | 10 | Responsive ledger, role filters, search, validation, modal details, transaction progress, errors; desktop and mobile screenshots |
| Backend integration | 10 | Flask, signature auth, SQLite metadata, digest verification, event indexing, independent chain reads and CSV; integration tests |
| Testing and evaluation | 10 | Contract security tests, real-EVM backend fixtures, browser flow, gas measurements, replay / rollback / tamper / nonce tests; raw evidence |
| Report quality | 10 | 8-page report with all required headings, figures, references and limitations |
| Innovation and creativity | 5 | Combined metadata commitment, independent idempotent reconciliation, block-hash rollback recovery, explicit confirmation policy |

Before submission: fill student details; follow any AI disclosure policy; verify the real MetaMask extension; preferably deploy on the recommended Sepolia testnet; retain screenshots and hashes from that run; inspect the video and its local-network disclosure. Local test outcomes do not establish public-network performance or production security.
