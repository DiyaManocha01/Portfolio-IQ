"""Integration tests against the seeded demo portfolio.

These exercise the full stack (API -> services -> DB) rather than mocking,
since PortfolioIQ's value is in how the layers combine. Assumes
`python -m app.data.seed` has already been run against the dev database.
"""


def test_portfolio_summary(client, auth_headers):
    resp = client.get("/portfolio/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["holdings_count"] > 0
    assert body["portfolio_value"] > 0
    assert 0 <= body["health_score"] <= 100


def test_portfolio_holdings_have_valid_pnl_math(client, auth_headers):
    resp = client.get("/portfolio", headers=auth_headers)
    assert resp.status_code == 200
    holdings = resp.json()
    assert len(holdings) > 0
    for h in holdings:
        expected_pnl = round(h["current_value"] - h["invested_value"], 2)
        assert abs(h["pnl"] - expected_pnl) < 0.01


def test_portfolio_risk_metrics_shape(client, auth_headers):
    resp = client.get("/portfolio/risk", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["annualized_volatility"] >= 0
    assert -1 <= body["max_drawdown"] <= 0
    total_risk_contrib = sum(rc["risk_contribution_pct"] for rc in body["risk_contributions"])
    assert 90 <= total_risk_contrib <= 110  # should sum close to 100%


def test_portfolio_health_components_sum_to_overall(client, auth_headers):
    resp = client.get("/portfolio/health", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["components"]) == 5
    avg = sum(c["score"] for c in body["components"]) / 5
    assert abs(avg - body["overall_health"]) < 0.5


def test_portfolio_weaknesses_have_required_fields(client, auth_headers):
    resp = client.get("/portfolio/weaknesses", headers=auth_headers)
    assert resp.status_code == 200
    for w in resp.json()["weaknesses"]:
        assert w["severity"] in {"LOW", "MEDIUM", "HIGH"}
        assert w["explanation"]
        assert w["supporting_metric"]


def test_stock_prediction_endpoint(client, auth_headers):
    resp = client.get("/stocks/TCS/prediction", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] in {"POSITIVE", "NEGATIVE", "NEUTRAL"}
    assert 0 <= body["probability"] <= 1
    assert body["confidence"] in {"LOW", "MEDIUM", "HIGH"}
    assert len(body["important_features"]) > 0
    assert "not" in body["disclaimer"].lower() or "estimate" in body["disclaimer"].lower()


def test_stock_news_and_sentiment(client, auth_headers):
    news = client.get("/stocks/TCS/news", headers=auth_headers)
    assert news.status_code == 200
    assert len(news.json()) > 0
    for item in news.json():
        assert item["sentiment_label"] in {"POSITIVE", "NEUTRAL", "NEGATIVE"}

    sentiment = client.get("/stocks/TCS/sentiment", headers=auth_headers)
    assert sentiment.status_code == 200
    body = sentiment.json()
    total_pct = body["positive_pct"] + body["neutral_pct"] + body["negative_pct"]
    assert 99 <= total_pct <= 101


def test_discover_ranked_by_portfolio_fit(client, auth_headers):
    resp = client.get("/discover?limit=10", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 0
    fit_scores = [item["portfolio_fit"] for item in items]
    assert fit_scores == sorted(fit_scores, reverse=True)


def test_portfolio_fit_endpoint(client, auth_headers):
    resp = client.get("/portfolio-fit/SUNPHARMA", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["fit_score"] <= 100
    assert len(body["factors"]) == 6
    assert abs(sum(body["weights_used"].values()) - 1.0) < 0.01
