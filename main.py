import pandas as pd
import requests
import logging
import time
import json
import random
import argparse
from typing import Dict
from functools import wraps
from datetime import datetime

# Настройка логирования
def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('order_processing.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = logging.getLogger(__name__)


class OrderAPIError(Exception):
    pass


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
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
    # Мок для демонстрации
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
            
            # ИСПРАВЛЕНО: суммируем, а не перезаписываем
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


def load_registry(path: str) -> pd.DataFrame:
    try:
        logger.info(f"Загрузка реестра: {path}")
        df = pd.read_excel(path)
        
        required_columns = ['Номер заказа', 'Сумма заказа', 'Кол-во']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Отсутствуют обязательные колонки в реестре: {missing_columns}")
        
        df = df.rename(columns={
            'Номер заказа': 'order_id',
            'Сумма заказа': 'total_amount',
            'Кол-во': 'total_qty'
        })
        
        logger.info(f"Загружено {len(df)} записей из реестра")
        return df
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке реестра: {e}")
        raise


def reconcile_orders(sales_df: pd.DataFrame, registry_df: pd.DataFrame) -> Dict:
    sales_orders = set(sales_df['order_id'].unique())
    registry_orders = set(registry_df['order_id'].unique())
    
    only_in_sales = sales_orders - registry_orders
    only_in_registry = registry_orders - sales_orders
    common_orders = sales_orders & registry_orders
    
    discrepancies = []
    matches = 0
    
    sales_agg = sales_df.groupby('order_id').agg({
        'price': 'sum',
        'qty': 'sum'
    }).reset_index()
    
    for order_id in common_orders:
        sales_row = sales_agg[sales_agg['order_id'] == order_id].iloc[0]
        registry_row = registry_df[registry_df['order_id'] == order_id].iloc[0]
        
        amount_diff = abs(sales_row['price'] - registry_row['total_amount'])
        qty_diff = abs(sales_row['qty'] - registry_row['total_qty'])
        
        if amount_diff > 0.01 or qty_diff > 0:
            discrepancies.append({
                'order_id': order_id,
                'sales_amount': sales_row['price'],
                'registry_amount': registry_row['total_amount'],
                'amount_diff': amount_diff,
                'sales_qty': sales_row['qty'],
                'registry_qty': registry_row['total_qty'],
                'qty_diff': qty_diff
            })
        else:
            matches += 1
    
    return {
        'total_sales_orders': len(sales_orders),
        'total_registry_orders': len(registry_orders),
        'common_orders': len(common_orders),
        'only_in_sales': list(only_in_sales),
        'only_in_registry': list(only_in_registry),
        'matches': matches,
        'discrepancies': discrepancies,
        'discrepancy_count': len(discrepancies)
    }


def calculate_metrics(sales_df: pd.DataFrame, revenue_by_sku: Dict[str, float]) -> Dict:
    metrics = {}
    metrics['total_revenue'] = sum(revenue_by_sku.values())
    
    top_5 = sorted(revenue_by_sku.items(), key=lambda x: x[1], reverse=True)[:5]
    metrics['top_5_by_revenue'] = top_5
    
    returned_orders = []
    for order_id in sales_df['order_id'].unique():
        try:
            if get_order_status(order_id) == 'returned':
                returned_orders.append(order_id)
        except:
            continue
    
    returned_df = sales_df[sales_df['order_id'].isin(returned_orders)]
    metrics['returned_orders_count'] = len(returned_orders)
    metrics['returned_items_count'] = len(returned_df)
    if not returned_df.empty:
        metrics['returned_revenue'] = sum([row['price'] * row['qty'] for _, row in returned_df.iterrows()])
    else:
        metrics['returned_revenue'] = 0
    
    return metrics


def parse_arguments():
    parser = argparse.ArgumentParser(description='Скрипт для сверки данных по заказам и расчета выручки')
    parser.add_argument('-s', '--sales', required=True, help='Путь к файлу с выгрузкой продаж (Excel)')
    parser.add_argument('-r', '--registry', required=True, help='Путь к файлу с реестром заказов (Excel)')
    parser.add_argument('-o', '--output', default='results_summary.txt', help='Путь к файлу для сохранения результатов')
    parser.add_argument('-v', '--verbose', action='store_true', help='Включить подробный вывод')
    return parser.parse_args()


def print_results(revenue_by_sku, reconciliation, metrics, output_file):
    logger.info("=" * 60)
    logger.info("ВЫРУЧКА ПО ТОВАРАМ:")
    for sku, total in sorted(revenue_by_sku.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {sku}: {total:,.2f} руб.")
    
    logger.info("=" * 60)
    logger.info("СВЕРКА ДАННЫХ:")
    logger.info(f"  Всего заказов в выгрузке: {reconciliation['total_sales_orders']}")
    logger.info(f"  Всего заказов в реестре: {reconciliation['total_registry_orders']}")
    logger.info(f"  Общих заказов: {reconciliation['common_orders']}")
    logger.info(f"  Совпавших заказов: {reconciliation['matches']}")
    logger.info(f"  Расхождений: {reconciliation['discrepancy_count']}")
    
    if reconciliation['only_in_sales']:
        logger.warning(f"  Только в выгрузке: {reconciliation['only_in_sales']}")
    
    if reconciliation['only_in_registry']:
        logger.warning(f"  Только в реестре: {reconciliation['only_in_registry']}")
    
    if reconciliation['discrepancies']:
        logger.warning("  Детали расхождений:")
        for disc in reconciliation['discrepancies'][:5]:
            logger.warning(f"    Заказ {disc['order_id']}: сумма {disc['sales_amount']:.2f} vs {disc['registry_amount']:.2f}")
    
    logger.info("=" * 60)
    logger.info("КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ:")
    logger.info(f"  Общая выручка: {metrics['total_revenue']:,.2f} руб.")
    logger.info(f"  Возвратов: {metrics['returned_orders_count']} заказов")
    logger.info(f"  Сумма возвратов: {metrics['returned_revenue']:,.2f} руб.")
    if metrics['total_revenue'] > 0:
        logger.info(f"  Доля возвратов: {(metrics['returned_revenue'] / metrics['total_revenue'] * 100):.1f}%")
    logger.info(f"  Топ-5 товаров по выручке:")
    for sku, amount in metrics['top_5_by_revenue']:
        logger.info(f"    {sku}: {amount:,.2f} руб.")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"Отчет по сверке данных - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        
        f.write("ВЫРУЧКА ПО ТОВАРАМ:\n")
        for sku, total in sorted(revenue_by_sku.items(), key=lambda x: x[1], reverse=True):
            f.write(f"  {sku}: {total:,.2f} руб.\n")
        
        f.write("\nРЕЗУЛЬТАТЫ СВЕРКИ:\n")
        f.write(f"  Совпавших заказов: {reconciliation['matches']}\n")
        f.write(f"  Расхождений: {reconciliation['discrepancy_count']}\n")
        
        if reconciliation['discrepancies']:
            f.write("\nДЕТАЛИ РАСХОЖДЕНИЙ:\n")
            for disc in reconciliation['discrepancies']:
                f.write(f"  Заказ {disc['order_id']}:\n")
                f.write(f"    Выгрузка: сумма {disc['sales_amount']:.2f}, количество {disc['sales_qty']}\n")
                f.write(f"    Реестр: сумма {disc['registry_amount']:.2f}, количество {disc['registry_qty']}\n")
        
        f.write("\nКЛЮЧЕВЫЕ ПОКАЗАТЕЛИ:\n")
        f.write(f"  Общая выручка: {metrics['total_revenue']:,.2f} руб.\n")
        f.write(f"  Возвратов: {metrics['returned_orders_count']} заказов\n")
        f.write(f"  Доля возвратов: {(metrics['returned_revenue'] / metrics['total_revenue'] * 100):.1f}%\n")
        f.write(f"  Топ-5 товаров по выручке:\n")
        for sku, amount in metrics['top_5_by_revenue']:
            f.write(f"    {sku}: {amount:,.2f} руб.\n")
    
    logger.info(f"Результаты сохранены в {output_file}")


def main():
    args = parse_arguments()
    
    global logger
    logger = setup_logging(args.verbose)
    
    logger.info("=" * 60)
    logger.info("Запуск скрипта сверки данных")
    
    try:
        sales_df = load_orders(args.sales)
        registry_df = load_registry(args.registry)
        
        logger.info("Начало расчета выручки по SKU...")
        revenue_by_sku = calc_revenue_by_sku(sales_df)
        
        logger.info("Начало сверки данных...")
        reconciliation = reconcile_orders(sales_df, registry_df)
        
        metrics = calculate_metrics(sales_df, revenue_by_sku)
        
        print_results(revenue_by_sku, reconciliation, metrics, args.output)
        
        logger.info("Скрипт успешно завершен")
        
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
