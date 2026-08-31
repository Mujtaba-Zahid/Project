"""CSV parsing and data cleaning logic for bank statement imports."""
import csv
import io
from datetime import datetime


def parse_csv(file_content):
    """Parse CSV content and return headers and rows."""
    try:
        text = file_content.decode('utf-8')
    except UnicodeDecodeError:
        text = file_content.decode('latin-1')

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        return [], []

    headers = rows[0]
    data = rows[1:]
    return headers, data


def clean_data(rows, column_mapping):
    """Clean imported data based on column mapping.

    Args:
        rows: List of row lists from CSV
        column_mapping: dict mapping our fields to CSV column indices
            e.g. {'date': 0, 'amount': 3, 'type': 4, 'description': 5}

    Returns:
        cleaned_rows: List of dicts with cleaned data
        errors: List of error messages for skipped rows
    """
    cleaned = []
    errors = []

    for i, row in enumerate(rows, start=2):  # Start at 2 (header is row 1)
        try:
            record = {}

            # Date
            date_idx = column_mapping.get('date')
            if date_idx is not None and date_idx < len(row):
                raw_date = row[date_idx].strip()
                record['date'] = _parse_date(raw_date)
            else:
                errors.append(f'Row {i}: Missing date')
                continue

            # Amount
            amount_idx = column_mapping.get('amount')
            if amount_idx is not None and amount_idx < len(row):
                raw_amount = row[amount_idx].strip().replace(',', '').replace('-', '')
                if not raw_amount:
                    errors.append(f'Row {i}: Empty amount')
                    continue
                record['amount'] = abs(float(raw_amount))
            else:
                errors.append(f'Row {i}: Missing amount')
                continue

            # Type
            type_idx = column_mapping.get('type')
            if type_idx is not None and type_idx < len(row):
                raw_type = row[type_idx].strip().lower()
                if raw_type in ('income', 'credit', 'cr', 'deposit'):
                    record['type'] = 'income'
                else:
                    record['type'] = 'expense'
            else:
                record['type'] = 'expense'  # Default to expense

            # Description
            desc_idx = column_mapping.get('description')
            if desc_idx is not None and desc_idx < len(row):
                record['description'] = row[desc_idx].strip()
            else:
                record['description'] = ''

            cleaned.append(record)

        except (ValueError, IndexError) as e:
            errors.append(f'Row {i}: {str(e)}')

    # Remove duplicates (same date + amount + description)
    seen = set()
    unique = []
    for record in cleaned:
        key = (str(record['date']), str(record['amount']), record['description'])
        if key not in seen:
            seen.add(key)
            unique.append(record)

    return unique, errors


def _parse_date(date_str):
    """Try multiple date formats."""
    formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d']
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Cannot parse date: {date_str}')
