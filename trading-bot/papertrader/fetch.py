import yfinance as yf, pandas as pd, sys
T={"SPY":"SPY","QQQ":"QQQ","IEF":"IEF","EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X","AUDUSD":"AUDUSD=X","XAUUSD":"GC=F"}
for k,t in T.items():
    df=yf.download(t,start="2000-01-01",auto_adjust=True,progress=False,multi_level_index=False)
    df=df[["Open","High","Low","Close"]].dropna(); df.index.name="date"
    df.to_csv(f"data/{k}.csv")
    r=df.Close.pct_change().abs()
    print(k,len(df),df.index[0].date(),df.index[-1].date(),"maxabsret",round(r.max(),3),"at",r.idxmax().date(),"bad_ohlc",int(((df.High<df[["Open","Close"]].max(axis=1)*0.999)|(df.Low>df[["Open","Close"]].min(axis=1)*1.001)).sum()))
