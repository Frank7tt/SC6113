# Demonstration script

The delivered video is a narrated local-EVM walkthrough. Voice is generated from this script; no person is impersonated. Use the same sequence to record your own explanation, particularly after verifying MetaMask and Sepolia.

## 00:00 01 / Purpose and scope

This is InvoiceFlow, an enterprise invoice payment and reconciliation application for the SC6113 individual assignment. Small businesses need to know which customer paid which invoice, whether the amount is correct, and whether the payment is actually confirmed. InvoiceFlow connects those business questions to a smart contract and an independently verified ledger. This demonstration uses a local Ethereum compatible blockchain, public development wallets, and test Ether. It does not claim a live Sepolia deployment or a tested MetaMask extension.

## 00:39 02 / System architecture

The interface is built with HTML, CSS, JavaScript, and ethers version six. The Solidity contract stores the issuer, customer, amount, due time, status, and document hash. Flask serves the interface, authenticates issuer signatures, stores invoice descriptions in SQLite, and reads the blockchain for reconciliation. The browser signs transactions through a wallet provider. The backend never holds a customer private key and never treats a client supplied paid flag as proof. The network and contract address are visible in the workspace.

## 01:18 03 / Issue a customer-specific invoice

I select the merchant development wallet and create a new invoice. The reference identifies the invoice within this merchant's account. Another merchant may use the same reference, but this merchant cannot reuse it. I enter a consulting description, the customer's wallet, an Ether amount, and a future due time. The merchant wallet is taken from the transaction sender. The fixed customer wallet prevents an unrelated account from claiming this invoice payment. Descriptions remain off chain, while their content commitment is stored in the contract.

## 01:53 04 / Validate before submitting

First I enter a zero amount. The interface rejects it before a transaction is submitted and explains how to correct the input. This is a usability check, not the security boundary. A caller can bypass a web form, so the smart contract also rejects a zero amount, a zero address, self payment, an invalid due time, or empty hashes. Monetary values are converted to integer wei rather than floating point numbers. I now correct the amount to zero point zero one five Ether.

## 02:27 05 / Commit and authenticate invoice metadata

Creating the invoice requires an issuer login signature and a blockchain transaction. The authentication message includes the origin, chain, a single use nonce, and a five minute expiry. It authorizes metadata editing, not a transfer of funds. After the receipt succeeds, Flask verifies that the signed issuer and canonical metadata match the chain before storing the description. The ledger displays a verified integrity indicator. If upload fails after creation, the browser keeps a recovery copy rather than pretending the chain transaction was undone.

## 03:05 06 / Execute a real payment

I switch to the customer development wallet. The application shows the payment action for invoices payable by this account. I pay the selected invoice. The contract checks that it is open, not expired, and called by the designated customer. The transferred value must equal the invoice amount exactly. Underpayment, overpayment, and repeated payment revert. On success, the invoice becomes paid and the merchant's credit increases. These are actual transactions on the local virtual machine, not simulated paid labels in the web interface.

## 03:42 07 / Independently reconcile settlement

Next I run reconciliation. Flask reads events from the configured contract and compares the payment with the stored invoice amount and merchant. Events are unique by network scope, transaction hash, and log index, so running reconciliation twice does not duplicate them. The local policy requires one confirmation; the Sepolia configuration requires three. A payment below the threshold is shown as confirming. The server pins its reads to one block and detects checkpoint hash changes so an indexed payment can be removed after a chain rollback.

## 04:19 08 / Withdraw merchant funds

Payment settlement creates a withdrawable merchant credit. I return to the merchant wallet and withdraw it. The contract checks the credit, clears it, reduces total liability, and only then transfers Ether to the merchant. A reentrancy lock provides another guard. If the receiving contract rejects Ether, the transaction reverts and the merchant's credit is preserved. The administrator has no function to divert these funds. The payment history remains visible after withdrawal because withdrawing revenue does not undo the paid invoice.

## 04:53 09 / Cancel an unpaid invoice

I also create a second invoice for a cancelled service request. The issuing merchant can cancel it while it is open. After cancellation, a customer cannot pay it and the original reference cannot be reused by that merchant. Paid invoices cannot be cancelled under this prototype's business rules. Overdue status is computed from blockchain time and payments after the due date fail. This project deliberately excludes refunds, invoice amendments, tax calculations, and disputes, so these rules stay explicit and testable.

## 05:28 10 / Testing and evaluation

The evidence includes twenty nine passing contract tests, nineteen backend integration tests, and thirteen browser checks. Contract tests include an actual reverted payment receipt, failed withdrawal rollback, a malicious reentrant receiver, and a liability invariant across twelve multi merchant payments. Backend tests cover signature replay, expiry, unauthorized metadata changes, tampering, confirmation thresholds, chain rollback, and safe CSV export. Browser checks execute invoice creation, payment, withdrawal, cancellation, filters, and a mobile overflow check. The tested wallet rejection is an injected provider fixture, not a claim about the MetaMask extension.

## 06:17 11 / Export and audit trail

The reconciliation CSV links invoice references to merchant and customer wallets, Ether amounts, settlement status, payment hashes, confirmation counts, and integrity results. This makes the prototype useful for accounts receivable review rather than just transferring cryptocurrency. Merchant supplied references that look like spreadsheet formulas are escaped during export. The responsive interface supports desktop and mobile layouts. The history identifies payment and withdrawal as separate events, and the details view exposes the immutable document hash so a reviewer can follow the record back to its contract.

## 06:59 12 / Limitations and next verification

InvoiceFlow demonstrates a complete invoice settlement and reconciliation workflow, but it is a coursework prototype. Ether prices fluctuate, the public chain reveals wallet relationships, and hashing low entropy invoice data does not guarantee privacy. The backend uses a single process SQLite index and is intended for a small dataset. It is not a production accounting system or an audited payment service. The remaining deployment step is to use dedicated test wallets on Sepolia, verify the actual MetaMask dialogs, and save those transaction hashes and screenshots. Thank you for reviewing the implementation and its evidence.

