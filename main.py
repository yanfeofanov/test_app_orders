import pandas as pd
import requests
import logging
import time
import json
import random
from typing import Dict
from functools import wraps

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('order_processing.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class OrderAPIError(Exception):
    pass


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Декоратор для повторных попыток при ошибках
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"Все попытки ({max_attempts}) не удались для {func.__name__}: {e}")
                        raise
                    logger.warning(f"Попытка {attempt + 1} не удалась, повтор через {current_delay}с: {e}")
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None
        return wrapper
    return decorator


def load_orders(path: str) -> pd.DataFrame:
    try:
        logger.info(f"Загрузка файла: {path}")
        df = pd.read_excel(path)
        
        required_columns = ['order_id', 'sku', 'price', 'qty']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Отсутствуют обязательные колонки: {missing_columns}")
        
        if not pd.api.types.is_numeric_dtype(df['price']):
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            if df['price'].isna().any():
                logger.warning("Обнаружены некорректные цены, заменены на NaN")
        
        if not pd.api.types.is_numeric_dtype(df['qty']):
            df['qty'] = pd.to_numeric(df['qty'], errors='coerce')
            if df['qty'].isna().any():
                logger.warning("Обнаружены некорректные количества, заменены на NaN")
        
        before_count = len(df)
        df = df.dropna(subset=['price', 'qty'])
        after_count = len(df)
        if before_count != after_count:
            logger.warning(f"Удалено {before_count - after_count} строк с некорректными данными")
        
        logger.info(f"Загружено {len(df)} записей")
        return df
        
    except FileNotFoundError:
        logger.error(f"Файл не найден: {path}")
        raise
    except pd.errors.EmptyDataError:
        logger.error(f"Файл пуст: {path}")
        raise
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла {path}: {e}")
        raise


@retry(max_attempts=3, delay=1.0, backoff=2.0)
def get_order_status(order_id: str) -> str:
    """
    Получение статуса заказа с повторными попытками
    """
    statuses = {
        'ORD-1001': 'delivered',
        'ORD-1002': 'delivered',
        'ORD-1003': 'delivered',
        'ORD-1004': 'returned',
        'ORD-1005': 'delivered',
        'ORD-1006': 'delivered',
        'ORD-1007': 'cancelled',
        'ORD-1008': 'delivered',
        'ORD-1009': 'delivered',
        'ORD-1010': 'delivered',
        'ORD-1011': 'delivered',
        'ORD-1012': 'returned',
        'ORD-1013': 'delivered',
        'ORD-1014': 'delivered',
        'ORD-1015': 'delivered',
        'ORD-1016': 'delivered',
        'ORD-1017': 'delivered',
        'ORD-1018': 'cancelled',
        'ORD-1019': 'returned',
        'ORD-1020': 'delivered'
    }
    
    # Симуляция ошибки API (10% вероятность) для демонстрации retry
    if random.random() < 0.1:
        logger.warning(f"Симуляция ошибки API для заказа {order_id}")
        raise requests.RequestException("Симуляция ошибки API")
    
    return statuses.get(order_id, 'unknown')


def calc_revenue_by_sku(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        logger.warning("DataFrame пуст, возвращаем пустой словарь")
        return {}
    
    revenue = {}
    cancelled_count = 0
    api_errors = 0
    
    for i, row in df.iterrows():
        try:
            status = get_order_status(row['order_id'])
            if status == 'cancelled':
                cancelled_count += 1
                continue
            
            sku = str(row['sku'])
            amount = float(row['price']) * float(row['qty'])
            
            if sku in revenue:
                revenue[sku] += amount
            else:
                revenue[sku] = amount
                
        except OrderAPIError as e:
            api_errors += 1
            logger.error(f"Ошибка API для заказа {row['order_id']}: {e}")
            continue
        except Exception as e:
            logger.error(f"Неожиданная ошибка при обработке строки {i}: {e}")
            continue
    
    logger.info(f"Обработано {len(df)} заказов, отменено: {cancelled_count}, ошибок API: {api_errors}")
    return revenue


def main():
    try:
        df = load_orders("orders.xlsx")
        revenue = calc_revenue_by_sku(df)
        
        logger.info("=" * 50)
        logger.info("ВЫРУЧКА ПО ТОВАРАМ:")
        for sku, total in sorted(revenue.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"{sku}: {total:,.2f} руб.")
            
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
