// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/// @title InvoiceLedger - exact-value invoice settlement with pull withdrawals.
/// @notice No administrator can withdraw merchant funds. Metadata remains off-chain.
contract InvoiceLedger {
    enum Status { Missing, Open, Paid, Cancelled }
    struct Invoice {
        address merchant;
        address payer;
        uint256 amount;
        uint64 dueAt;
        Status status;
        bytes32 documentHash;
    }
    mapping(bytes32 => Invoice) private invoices;
    mapping(address => uint256) public credits;
    uint256 public totalLiability;
    address public immutable administrator;
    bool public paused;
    uint256 private entered = 1;

    error Unauthorized();
    error InvalidInvoice();
    error DuplicateInvoice();
    error InvoiceNotOpen();
    error InvoiceExpired();
    error IncorrectPayment(uint256 expected, uint256 received);
    error NothingToWithdraw();
    error TransferFailed();
    error ReentrantCall();
    error PaymentsPaused();

    event InvoiceCreated(bytes32 indexed id, address indexed merchant, address indexed payer,
        uint256 amount, uint64 dueAt, bytes32 documentHash);
    event InvoicePaid(bytes32 indexed id, address indexed payer, address indexed merchant, uint256 amount);
    event InvoiceCancelled(bytes32 indexed id, address indexed merchant);
    event Withdrawal(address indexed merchant, uint256 amount);
    event PauseChanged(bool paused);

    constructor() { administrator = msg.sender; }
    modifier nonReentrant() {
        if (entered != 1) revert ReentrantCall();
        entered = 2;
        _;
        entered = 1;
    }
    modifier whenNotPaused() {
        if (paused) revert PaymentsPaused();
        _;
    }
    function invoiceId(address merchant, bytes32 referenceHash) public pure returns (bytes32) {
        return keccak256(abi.encode(merchant, referenceHash));
    }
    function createInvoice(bytes32 referenceHash, address payer, uint256 amount,
        uint64 dueAt, bytes32 documentHash) external whenNotPaused returns (bytes32 id) {
        if (referenceHash == bytes32(0) || documentHash == bytes32(0) || payer == address(0)
            || payer == msg.sender || amount == 0 || dueAt <= block.timestamp) revert InvalidInvoice();
        id = invoiceId(msg.sender, referenceHash);
        if (invoices[id].status != Status.Missing) revert DuplicateInvoice();
        invoices[id] = Invoice(msg.sender, payer, amount, dueAt, Status.Open, documentHash);
        emit InvoiceCreated(id, msg.sender, payer, amount, dueAt, documentHash);
    }
    function getInvoice(bytes32 id) external view returns (Invoice memory) { return invoices[id]; }
    function payInvoice(bytes32 id) external payable whenNotPaused {
        Invoice storage inv = invoices[id];
        if (inv.status != Status.Open) revert InvoiceNotOpen();
        if (msg.sender != inv.payer) revert Unauthorized();
        if (block.timestamp > inv.dueAt) revert InvoiceExpired();
        if (msg.value != inv.amount) revert IncorrectPayment(inv.amount, msg.value);
        inv.status = Status.Paid;
        credits[inv.merchant] += msg.value;
        totalLiability += msg.value;
        emit InvoicePaid(id, msg.sender, inv.merchant, msg.value);
    }
    function cancelInvoice(bytes32 id) external {
        Invoice storage inv = invoices[id];
        if (msg.sender != inv.merchant) revert Unauthorized();
        if (inv.status != Status.Open) revert InvoiceNotOpen();
        inv.status = Status.Cancelled;
        emit InvoiceCancelled(id, msg.sender);
    }
    /// @dev Checks-effects-interactions plus a lock. A failed transfer reverts the effects.
    function withdraw() external nonReentrant {
        uint256 amount = credits[msg.sender];
        if (amount == 0) revert NothingToWithdraw();
        credits[msg.sender] = 0;
        totalLiability -= amount;
        (bool success,) = payable(msg.sender).call{value: amount}("");
        if (!success) revert TransferFailed();
        emit Withdrawal(msg.sender, amount);
    }
    /// @notice Pausing never blocks existing merchant withdrawals or invoice cancellation.
    function setPaused(bool value) external {
        if (msg.sender != administrator) revert Unauthorized();
        paused = value;
        emit PauseChanged(value);
    }
}
