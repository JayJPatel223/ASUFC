const {test}=require('node:test'); const assert=require('node:assert/strict'); const {cents,money,makeApi}=require('../.test-build/api.cjs');
test('exact cents',()=>{assert.equal(cents('250.01'),25001);assert.equal(cents('0.1'),10);assert.equal(cents('0'),0)});
test('invalid monetary amounts',()=>{for(const v of ['-1','1.001','1e3','','10000000001'])assert.throws(()=>cents(v))});
test('CAD format',()=>assert.match(money(25000),/250\.00/));
test('authenticated write request',async()=>{global.fetch=async(url,opts)=>{assert.equal(url,'/api/transactions');assert.equal(opts.method,'POST');assert.equal(opts.headers.Authorization,'Basic '+btoa('staff:example'));assert.deepEqual(JSON.parse(opts.body),{cents:25000});return Response.json({id:1})};assert.deepEqual(await makeApi('staff','example')('/transactions','POST',{cents:25000}),{id:1})});
test('server validation errors surfaced',async()=>{global.fetch=async()=>Response.json({detail:'Insufficient budget'},{status:422});await assert.rejects(makeApi('staff','example')('/transactions'),/Insufficient budget/)});
test('unauthorized response',async()=>{global.fetch=async()=>new Response('',{status:401});await assert.rejects(makeApi('staff','example')('/programs'),/Invalid staff credentials/)});
