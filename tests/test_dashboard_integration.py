"""
Integration tests for Flask dashboard routes & real data rendering (Phase 7)
"""

import pytest
from app import app
from src.database import initialize_database


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_dashboard_route_http_200(client):
    """Test GET / returns HTTP 200 and renders real top recommendations."""
    initialize_database()
    response = client.get('/')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    assert "Good Morning, Manager!" in html
    assert "What Needs Attention Today?" in html
    assert "Latest Day Sales" in html
    assert "View Evidence" in html


def test_inventory_route_http_200(client):
    """Test GET /inventory returns HTTP 200 and renders real inventory table."""
    initialize_database()
    response = client.get('/inventory')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    assert "Inventory Intelligence" in html
    assert "Total SKUs" in html
    assert "View Evidence" in html


def test_all_six_routes_load(client):
    """Test all six routes load with HTTP 200."""
    routes = ['/', '/copilot', '/inventory', '/sales', '/simulator', '/history']
    for r in routes:
        resp = client.get(r)
        assert resp.status_code == 200, f"Route {r} failed with status {resp.status_code}"


def test_api_dashboard_endpoint(client):
    """Test GET /api/dashboard returns HTTP 200 and valid JSON data."""
    initialize_database()
    response = client.get('/api/dashboard')
    assert response.status_code == 200
    json_data = response.get_json()
    assert "latest_sales" in json_data
    assert "top_recommendations" in json_data
    assert len(json_data["top_recommendations"]) <= 5
