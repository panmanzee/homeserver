-- World + Thailand feeds for the morning infographic (2026-11-16).
-- Without these the Thailand topic was always empty.
INSERT INTO feeds (name, url, category)
SELECT v.name, v.url, v.category
FROM (VALUES
    ('BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml', 'world'),
    ('Bangkok Post Top Stories', 'https://www.bangkokpost.com/rss/data/topstories.xml', 'thailand'),
    ('Khaosod English', 'https://www.khaosodenglish.com/feed/', 'thailand')
) AS v(name, url, category)
WHERE NOT EXISTS (SELECT 1 FROM feeds f WHERE f.url = v.url);
