"""Inventory validation and classification rules; no storage or presentation access."""
import math

def number(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f'{label} must be a finite number >= {minimum}')
    return value

def integer(value, label, minimum=0):
    number(value, label, minimum)
    if not isinstance(value, int):
        raise ValueError(f'{label} must be an integer')
    return value

def text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError(f'{label} must be nonempty text (max 500 characters)')
    return value

def location_key(cabinet, drawer, pocket):
    return '|'.join(str(x) for x in (cabinet, drawer, pocket))

def percentage(quantity, full_stock):
    if full_stock is None or full_stock <= 0:
        return None
    return 100 * quantity / full_stock

def classify(quantity, full_stock):
    """Empty=0; Low=(0,50%); Half=[50%,100%); Full>=100%."""
    if quantity == 0:
        return 'Empty'
    pct = percentage(quantity, full_stock)
    if pct is None:
        return 'Unavailable'
    return 'Full' if pct >= 100 else 'Half' if pct >= 50 else 'Low'

def below_threshold(location):
    limit = location.get('threshold')
    if limit is None:
        return None
    value = percentage(location['quantity'], location.get('full_stock')) if location.get('threshold_type') == 'percent' else location['quantity']
    return None if value is None else value <= limit

def validate_snapshot(data):
    if not isinstance(data, dict) or not isinstance(data.get('locations'), list) or not data['locations']:
        raise ValueError('inventory requires a nonempty locations list')
    seen = set()
    for loc in data['locations']:
        if not isinstance(loc, dict):
            raise ValueError('Each location must be an object')
        for key in ('drawer_id', 'pocket_id', 'medication_id', 'name', 'din', 'strength', 'dosage_form'):
            text(loc.get(key), key)
        if '|' in loc['drawer_id'] or '|' in loc['pocket_id']:
            raise ValueError('location identifiers must not contain |')
        key = (loc['drawer_id'], loc['pocket_id'])
        if key in seen:
            raise ValueError('duplicate location within snapshot')
        seen.add(key)
        integer(loc.get('quantity'), 'quantity')
        full = loc.get('full_stock')
        if full is not None:
            number(full, 'full_stock')
        if loc.get('threshold') is not None:
            number(loc['threshold'], 'threshold')
        if loc.get('threshold_type', 'quantity') not in ('quantity', 'percent'):
            raise ValueError('threshold_type must be quantity or percent')

        if loc.get('threshold_type') == 'percent' and loc.get('threshold') is not None and loc['threshold'] > 100:
            raise ValueError('Percentage threshold cannot exceed 100')
