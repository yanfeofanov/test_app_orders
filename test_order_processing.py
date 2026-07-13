import pytest
import pandas as pd
import tempfile
import os
from unittest.mock import patch
import requests
from main import load_orders, calc_revenue_by_sku, retry


@pytest.fixture
def sample_sales_data():
    data = {
        'order_id': ['ORD-001', 'ORD-002', 'ORD-003', 'ORD-004'],
        'sku': ['SKU-A', 'SKU-B', 'SKU-A', 'SKU-C'],
        'price': [100, 200, 100, 300],
        'qty': [1, 2, 1, 1]
    }
    return pd.DataFrame(data)


def test_load_orders_success():
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
        test_data = pd.DataFrame({
            'order_id': ['ORD-001', 'ORD-002'],
            'sku': ['SKU-A', 'SKU-B'],
            'price': [100, 200],
            'qty': [1, 2]
        })
        test_data.to_excel(tmp.name, index=False)
        tmp_path = tmp.name
    
    try:
        result = load_orders(tmp_path)
        assert len(result) == 2
    finally:
        os.unlink(tmp_path)


def test_load_orders_missing_column():
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
        test_data = pd.DataFrame({
            'order_id': ['ORD-001'],
            'sku': ['SKU-A'],
            'price': [100]
        })
        test_data.to_excel(tmp.name, index=False)
        tmp_path = tmp.name
    
    try:
        with pytest.raises(ValueError, match="Отсутствуют обязательные колонки"):
            load_orders(tmp_path)
    finally:
        os.unlink(tmp_path)


def test_load_orders_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_orders("nonexistent_file.xlsx")


def test_calc_revenue_by_sku(sample_sales_data):
    with patch('main.get_order_status') as mock_status:
        mock_status.side_effect = ['delivered', 'cancelled', 'returned', 'delivered']
        result = calc_revenue_by_sku(sample_sales_data)
        expected = {'SKU-A': 200.0, 'SKU-C': 300.0}
        assert result == expected


def test_calc_revenue_by_sku_empty_df():
    empty_df = pd.DataFrame(columns=['order_id', 'sku', 'price', 'qty'])
    result = calc_revenue_by_sku(empty_df)
    assert result == {}


def test_retry_decorator():
    call_count = 0
    
    @retry(max_attempts=3, delay=0.1)
    def failing_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise requests.RequestException("Test error")
        return "success"
    
    result = failing_function()
    assert result == "success"
    assert call_count == 3


def test_retry_decorator_max_attempts():
    @retry(max_attempts=2, delay=0.1)
    def always_fails():
        raise requests.RequestException("Always fails")
    
    with pytest.raises(requests.RequestException):
        always_fails()
