-- Initial RSS feed list. Apply once against the `newsfeed` database.
-- Edit / add rows later with plain SQL; no restart needed.

INSERT INTO feeds (name, url, category) VALUES
    ('CNBC Top News',           'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114', 'finance'),
    ('MarketWatch Top Stories', 'https://feeds.content.dowjones.io/public/rss/mw_topstories',                            'finance'),
    ('Yahoo Finance',           'https://finance.yahoo.com/news/rssindex',                                              'finance'),
    ('WSJ Markets',             'https://feeds.a.dj.com/rss/RSSMarketsMain.xml',                                        'finance'),
    ('Ars Technica',            'https://feeds.arstechnica.com/arstechnica/index',                                      'tech'),
    ('The Verge',               'https://www.theverge.com/rss/index.xml',                                               'tech'),
    ('TechCrunch',              'https://techcrunch.com/feed/',                                                         'tech')
ON CONFLICT (url) DO NOTHING;

-- Example watchlist seed (optional) -- add the tickers you care about.
-- price_symbol: leave equal to symbol for US listings; for non-US use the
-- provider's format (Twelve Data, e.g. 'SAP:XETR' or a MIC-qualified symbol).
-- INSERT INTO tickers (symbol, name, price_symbol, on_watchlist, watchlist_added_at)
-- VALUES ('AAPL', 'Apple Inc.', 'AAPL', true, now())
-- ON CONFLICT (symbol) DO UPDATE SET on_watchlist = true, watchlist_added_at = now();
