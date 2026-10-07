# 用课堂 Remix 和 MetaMask 部署 Sepolia

这个方法不需要把钱包私钥交给 Python、Node.js 或任何人。

1. 准备两个独立测试钱包：商户和客户，切换到 Ethereum Sepolia，并领取测试 ETH。
2. 打开官方 Remix：https://remix.ethereum.org/ 。新建 `InvoiceLedger.sol`，粘贴本项目 `contracts/InvoiceLedger.sol` 的完整内容。不要部署 `TestReceivers.sol`；它只是攻击测试夹具。
3. Solidity Compiler 选择 0.8.26、启用 optimizer 并设置 200 runs、EVM target Shanghai，然后编译。
4. Deploy & Run 选择 Injected Provider / MetaMask，确认 MetaMask 当前网络是 Sepolia。
5. 选择 InvoiceLedger，点击 Deploy，在钱包里确认。等待成功收据，保存部署交易哈希与合约地址。
6. 从你自己的节点服务获取 Sepolia RPC URL。它只用于后端读取，不是钱包私钥。
7. 在项目终端设置 `SEPOLIA_RPC_URL`，执行：

```sh
node scripts/configure-sepolia.mjs YOUR_DEPLOYMENT_TRANSACTION_HASH
```

脚本检查网络、创建收据、链上代码存在和基础接口，再生成配置；它不代替源码验证或审计。

8. 重启 Flask，通过 Connect MetaMask 用商户开票，再切到客户付款。等待三次确认后 Reconcile，最后切回商户提款。
9. 在 `SEPOLIA_VERIFICATION.md` 填写实际交易哈希，并保存钱包弹窗和区块浏览器截图。不得把当前本地视频或测试记录写成 Sepolia 验证。

若以后使用真实资产，必须另行处理安全审计、隐私、法规和生产运维；本作业只使用测试 ETH。
