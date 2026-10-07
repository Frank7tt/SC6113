import ganache from 'ganache';
// Public development mnemonic. NEVER fund these accounts on a public network.
const server=ganache.server({wallet:{mnemonic:'test test test test test test test test test test test junk',totalAccounts:8,defaultBalance:1000},chain:{chainId:31337,hardfork:'shanghai'},logging:{quiet:true}});
await server.listen(8545,'127.0.0.1');
console.log('Development chain: http://127.0.0.1:8545, chain ID 31337. Public test accounts only.');
process.on('SIGINT',async()=>{await server.close();process.exit(0)});
