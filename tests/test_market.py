from autosell.config import MarketSettings
from autosell.db import Database
from autosell.models import MarketListing, ScrapedListing, Watch
from autosell.market.deals import detect_risks, evaluate_deal, mentions
from autosell.market.pricing import estimate_market, price_suggestions, title_similarity, weighted_percentile


def _listing(i: int, title: str, price: float, **kw) -> MarketListing:
    return MarketListing(
        id=i, platform="sahibinden", external_id=str(1000 + i), url=f"https://x/{i}", title=title, price=price,
        first_seen="2026-09-28T10:00:00+00:00", last_seen="2026-09-28T10:00:00+00:00", **kw,
    )


MARKET = [
    _listing(1, "Apple iPhone 13 128 GB Mavi Temiz", 31000),
    _listing(2, "iPhone 13 128GB Kutulu Faturalı", 32500),
    _listing(3, "Sahibinden iPhone 13 128 GB Gece Yarısı", 30500),
    _listing(4, "iPhone 13 128 GB pil %90", 33000),
    _listing(5, "iphone 13 128gb beyaz hatasız", 31500),
    _listing(6, "iPhone 13 128 GB Yeşil", 29900),
    _listing(7, "iPhone 13 256 GB Pembe", 36000),
    _listing(8, "iPhone 13 Pro 128 GB", 41000),
    _listing(9, "iPhone 12 128 GB", 24000),
    _listing(10, "iPhone 13 Kılıf Şeffaf", 250),
    _listing(11, "iPhone 13 128 GB Kırmızı", 32000),
]


def test_title_similarity_distinguishes_variants_and_accessories():
    base = "iPhone 13 128 GB"
    assert title_similarity(base, "Apple iPhone 13 128GB Mavi Temiz") > 0.7
    assert title_similarity(base, "iPhone 13 256 GB Pembe") < 0.4
    assert title_similarity(base, "iPhone 13 Pro 128 GB") < 0.5
    assert title_similarity(base, "iPhone 12 128 GB") < 0.4
    assert title_similarity(base, "iPhone 13 Kılıf Şeffaf") < 0.3


def test_weighted_percentile_matches_plain_median_for_equal_weights():
    assert weighted_percentile([1, 2, 3, 4, 5], [1, 1, 1, 1, 1], 50) == 3
    assert 1 <= weighted_percentile([1, 100], [10, 0.1], 50) < 5


def test_estimate_uses_only_true_comparables():
    est = estimate_market("iPhone 13 128 GB Siyah", MARKET)
    comp_ids = {c.listing_id for c in est.comps}
    assert {7, 8, 9, 10}.isdisjoint(comp_ids)
    assert est.n == 7
    assert 30500 <= est.median <= 32500
    assert est.p25 <= est.median <= est.p75
    sugg = price_suggestions(est)
    assert sugg["quick"] < sugg["fair"] <= sugg["high"]


def test_deal_scoring_and_risks():
    market = MarketSettings(negotiation_pct=5, commission_pct=0, fixed_cost=0, min_comps=4)
    watch = Watch(id=1, name="iPhone 13", min_profit=2000, min_margin_pct=8)
    cheap = _listing(20, "iPhone 13 128 GB Mavi acil satılık", 25500)
    est = estimate_market(cheap.title, MARKET, exclude_id=20)
    deal = evaluate_deal(cheap, est, market, watch)
    assert deal.is_deal and deal.est_profit > 2000 and deal.score > 50

    scam = _listing(21, "iPhone 13 128 GB kapora ile kargo", 12000)
    deal2 = evaluate_deal(scam, estimate_market(scam.title, MARKET, exclude_id=21), market, watch)
    assert not deal2.is_deal
    assert any(f.level == "yuksek" for f in deal2.risk_flags)

    fair = _listing(22, "iPhone 13 128 GB Siyah", 31500)
    deal3 = evaluate_deal(fair, estimate_market(fair.title, MARKET, exclude_id=22), market, watch)
    assert not deal3.is_deal


def test_risk_negations_are_ignored():
    assert mentions("degisen yok boyasiz", "degisen") is False
    assert mentions("aracta degisensiz tramersiz", "tramer") is False
    assert mentions("icloud kilitli", "kilitli") is True
    assert mentions("hasar kaydi yok", "hasar") is False
    ok = _listing(30, "Clio 1.5 dCi değişensiz boyasız tramersiz", 500000)
    est = estimate_market(ok.title, [])
    assert detect_risks(ok, est) == []


def test_db_tracks_price_drops(tmp_path):
    db = Database(tmp_path / "t.db")
    w = db.save_watch(Watch(name="deneme"))
    item = ScrapedListing(platform="letgo", external_id="55", url="u", title="PS5", price=20000)
    listing, change = db.upsert_listing(item, w.id)
    assert change == "new" and listing.price_drop is None
    item.price = 18000
    listing, change = db.upsert_listing(item, w.id)
    assert change == "price_changed" and listing.price_drop == 2000
    assert [h["price"] for h in db.price_history(listing.id)] == [20000, 18000]
    assert len(db.listings_for_watch(w.id)) == 1
