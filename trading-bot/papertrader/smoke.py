import core
d,fx=core.load('data',core.STOCKS+core.STOCK_EXTRA+core.FX); print('fixes',fx)
idx=core.panel(d,core.STOCKS,'Close').index
for k,f in core.STOCK_STRATS.items():
    s=core.stats(core.simulate(f(d,idx),d,core.COST['stocks']),'2005-01-01'); print(k,{a:round(b,3) for a,b in s.items()})
idx=core.panel(d,core.FX,'Close').index
for k,f in core.FX_STRATS.items():
    s=core.stats(core.simulate(f(d,idx),d,core.COST['forex']),'2008-01-01'); print(k,{a:round(b,3) for a,b in s.items()})
