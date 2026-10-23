import sys; sys.argv=["x"]
exec(open("/freqtrade/user_data/scripts/btc_research.py").read().split("# ---- candidates")[0])
h = d["high"]
def bo(n_sma, n_hi, n_exit):
    s, hi, ex = c.rolling(n_sma).mean(), h.rolling(n_hi).max().shift(1), c.rolling(n_exit).mean()
    w, cur = [], 0
    for i in range(len(c)):
        if cur == 0 and c.iloc[i] > s.iloc[i] and c.iloc[i] > hi.iloc[i]: cur = 1
        elif cur == 1 and c.iloc[i] < ex.iloc[i]: cur = 0
        w.append(cur)
    return pd.Series(w, index=c.index, dtype=float)
grid = {(a,b,e): bo(a,b,e) for a in (100,200) for b in (20,55) for e in (20,50)}
for k,v in grid.items():
    r=run(v); print(k, "ret %.0f%% dd %.1f%% sh %.2f tr %d" % (r["ret"]*100, r["dd"]*100, r["sharpe"], r["trades"]))
tot_pick=tot_def=1
for y in range(2020, 2027):
    e0 = f"{y+1}-01-01" if y < 2026 else END
    best = max(grid, key=lambda k: run(grid[k], START, f"{y}-01-01")["sharpe"])
    t = run(grid[best], f"{y}-01-01", e0); dft = run(grid[(100,20,50)], f"{y}-01-01", e0); hd = run(pd.Series(1.0,index=c.index), f"{y}-01-01", e0)
    tot_pick*=1+t["ret"]; tot_def*=1+dft["ret"]
    print(y, best, "test %.1f%% dd %.1f%% | default %.1f%% dd %.1f%% | hold %.1f%% dd %.1f%%" % (t["ret"]*100,t["dd"]*100,dft["ret"]*100,dft["dd"]*100,hd["ret"]*100,hd["dd"]*100))
print("wf compound pick %.0f%% default %.0f%%" % ((tot_pick-1)*100,(tot_def-1)*100))
