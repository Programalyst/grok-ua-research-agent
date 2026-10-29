from collections import Counter, defaultdict
from datetime import datetime

from app.models import Category, Insights, IssueCount, Post, Sentiment, SentimentBucket, Spike

SPIKE_FOLLOWERS = 100_000
SPIKE_ENGAGEMENT = 1_000


def build_insights(game_id: str, posts: list[Post]) -> Insights:
    buckets: dict[datetime, SentimentBucket] = defaultdict(lambda: SentimentBucket(bucket_start=datetime.min))
    for p in posts:
        start = p.posted_at.replace(minute=0, second=0, microsecond=0)
        b = buckets[start]
        b.bucket_start = start
        if p.sentiment is Sentiment.POSITIVE:
            b.positive += 1
        elif p.sentiment is Sentiment.NEGATIVE:
            b.negative += 1
        else:
            b.neutral += 1

    issues: dict[str, list[Post]] = defaultdict(list)
    for p in posts:
        if p.category is Category.BUG:
            issues[p.text.split("…")[0][:80]].append(p)
    top_issues = sorted(
        (
            IssueCount(label=label, count=len(ps), example_post_ids=[x.id for x in ps[:3]])
            for label, ps in issues.items()
        ),
        key=lambda i: i.count,
        reverse=True,
    )[:5]

    spikes = [
        Spike(
            post_id=p.id,
            author=p.author,
            engagement=p.engagement,
            reason="influencer" if p.author_followers >= SPIKE_FOLLOWERS else "high engagement",
        )
        for p in posts
        if p.category is Category.INFLUENCER
        or p.author_followers >= SPIKE_FOLLOWERS
        or p.engagement >= SPIKE_ENGAGEMENT
    ]
    spikes.sort(key=lambda s: s.engagement, reverse=True)

    return Insights(
        game_id=game_id,
        total_posts=len(posts),
        sentiment_totals=dict(Counter(p.sentiment.value for p in posts)),
        category_totals=dict(Counter(p.category.value for p in posts)),
        language_totals=dict(Counter(p.language for p in posts)),
        sentiment_over_time=[buckets[k] for k in sorted(buckets)],
        top_issues=top_issues,
        spikes=spikes[:10],
    )
