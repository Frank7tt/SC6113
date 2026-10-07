import fs from 'node:fs';
import {JsonRpcProvider,ContractFactory,Wallet} from 'ethers';
const sepolia=process.argv.includes('--sepolia');
const rpc=sepolia?process.env.SEPOLIA_RPC_URL:'http://127.0.0.1:8545';
if(!rpc) throw Error('Set SEPOLIA_RPC_URL.');
const provider=new JsonRpcProvider(rpc);
const chain=Number((await provider.getNetwork()).chainId);
if(chain!==(sepolia?11155111:31337)) throw Error('Wrong network. Deployment aborted.');
const signer=sepolia?new Wallet(process.env.DEPLOYER_PRIVATE_KEY||'',provider):await provider.getSigner(0);
const a=JSON.parse(fs.readFileSync('artifacts/InvoiceLedger.json'));
const contract=await new ContractFactory(a.abi,a.bytecode,signer).deploy();
await contract.waitForDeployment();
const receipt=await contract.deploymentTransaction().wait();
const cfg={chainId:chain,network:sepolia?'Sepolia':'Local development',rpcUrl:rpc,contractAddress:await contract.getAddress(),deploymentBlock:receipt.blockNumber,deploymentTransaction:receipt.hash,confirmations:sepolia?3:1,localDemo:!sepolia};
// Never expose authenticated RPC URLs in the browser config; Flask supplies the public fields.
fs.writeFileSync('deployment.json',JSON.stringify(cfg,null,2));
console.log(JSON.stringify({...cfg,rpcUrl:'[configured]'},null,2));
