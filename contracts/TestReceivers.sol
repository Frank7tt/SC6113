// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
import './InvoiceLedger.sol';
/// Test fixture only. Not part of the application deployment.
contract TestMerchant {
    InvoiceLedger public ledger;
    bool public rejectEther;
    bool public tryReentry;
    bool public reentryBlocked;
    constructor(InvoiceLedger l) { ledger = l; }
    function create(bytes32 ref, address payer, uint amount, uint64 due, bytes32 doc) external {
        ledger.createInvoice(ref, payer, amount, due, doc);
    }
    function configure(bool reject_, bool attack_) external { rejectEther = reject_; tryReentry = attack_; }
    function withdraw() external { ledger.withdraw(); }
    receive() external payable {
        require(!rejectEther, 'reject');
        if (tryReentry) {
            try ledger.withdraw() { reentryBlocked = false; }
            catch { reentryBlocked = true; }
        }
    }
}
