"""Tests for analysis routes."""
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
import json


@pytest.fixture
def client():
    """Create test client."""
    from app.api.main import app
    return TestClient(app)


@pytest.fixture
def mock_run_once():
    """Mock the graph_multi.run_once function."""
    return Mock(return_value={
        'run_id': '20260321_120000_AAPL',
        'run_dir': '/tmp/test_run',
        'final_decision': 'Test analysis result',
        'cio_report_path': '/tmp/test_run/cio.json'
    })


class TestAnalyzeStream:
    """Tests for GET /api/analyze/stream endpoint."""

    def test_stream_returns_final_decision(self, client):
        """Test that streaming endpoint returns final_decision in markdown format."""
        mock_result = {
            'run_id': '20260321_120000_TEST',
            'run_dir': '/tmp/test_run',
            'final_decision': '# Test Report\n\nThis is a **test** analysis.',
            'quant_report_obj': {'price': 150.0},
            'news_report_obj': {'sentiment': 'positive'},
            'social_report_obj': {'sentiment': 'bullish'},
            'cio_report_path': '/tmp/test_run/cio.json'
        }

        with patch('app.api.routes.analyze.run_once', return_value=mock_result):
            with client.stream("GET", "/api/analyze/stream?query=TEST") as response:
                assert response.status_code == 200

                # Collect all events
                events = []
                for line in response.iter_lines():
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        events.append(data)

                # Verify we got a result event with final_decision
                result_events = [e for e in events if e.get('type') == 'result']
                assert len(result_events) == 1

                result_data = result_events[0]['data']
                assert result_data['report_id'] == '20260321_120000_TEST'
                assert result_data['status'] == 'completed'
                assert result_data['final_decision'] == '# Test Report\n\nThis is a **test** analysis.'

    def test_stream_handles_errors(self, client):
        """Test that streaming endpoint handles errors gracefully."""
        with patch('app.api.routes.analyze.run_once', side_effect=Exception('Test error')):
            with client.stream("GET", "/api/analyze/stream?query=AAPL") as response:
                assert response.status_code == 200

                # Collect all events
                events = []
                for line in response.iter_lines():
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        events.append(data)

                # Verify we got an error event
                error_events = [e for e in events if e.get('type') == 'error']
                assert len(error_events) == 1
                assert 'Test error' in error_events[0]['message']
