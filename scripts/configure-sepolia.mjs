// Attach an existing Remix/MetaMask deployment without handling a private key.
import fs from 'node:fs';
import {JsonRpcProvider,Contract,isHexString} from 'ethers';
const txHash=process.argv[2];
if(!isHexString(txHash,32))throw Error('Usage: node scripts/configure-sepolia.mjs DEPLOYMENT_TRANSACTION_HASH');
if(!process.env.SEPOLIA_RPC_URL)throw Error('Set SEPOLIA_RPC_URL. No wallet private key is required.');
const provider=new JsonRpcProvider(process.env.SEPOLIA_RPC_URL);
if(Number((await provider.getNetwork()).chainId)!==11155111)throw Error('RPC must be Ethereum Sepolia.');
const receipt=await provider.getTransactionReceipt(txHash);
if(!receipt||receipt.status!==1||!receipt.contractAddress)throw Error('Expected a successful contract-creation receipt.');
if(await provider.getCode(receipt.contractAddress)==='0x')throw Error('No deployed contract code found.');
const artifact=JSON.parse(fs.readFileSync('artifacts/InvoiceLedger.json'));
const contract=new Contract(receipt.contractAddress,artifact.abi,provider);
await contract.administrator();await contract.totalLiability(); // Basic interface compatibility, not a source audit.
const cfg={chainId:11155111,network:'Sepolia',rpcUrl:process.env.SEPOLIA_RPC_URL,contractAddress:receipt.contractAddress,
 deploymentBlock:receipt.blockNumber,deploymentTransaction:receipt.hash,confirmations:3,localDemo:false};
fs.writeFileSync('deployment.json',JSON.stringify(cfg,null,2));
console.log(`Configured Sepolia contract ${cfg.contractAddress}. Restart Flask; verify the correct source was deployed in Remix.`);
