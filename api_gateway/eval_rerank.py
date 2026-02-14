import json
import re
import sys
from math import inf


def parse_price(price_str):
    if not price_str:
        return float('inf')
    try:
        clean_price = re.sub(r'[^\d.]', '', str(price_str))
        return float(clean_price) if clean_price else float('inf')
    except ValueError:
        return float('inf')


def parse_rating(rating_str):
    if not rating_str:
        return 0.0
    try:
        match = re.search(r"(\d+(\.\d+)?)", str(rating_str))
        return float(match.group(1)) if match else 0.0
    except ValueError:
        return 0.0


def parse_reviews(reviews_str):
    if not reviews_str:
        return 0
    try:
        match = re.search(r"(\d[\d,]*)", str(reviews_str))
        if not match:
            return 0
        num = match.group(1).replace(',', '')
        return int(num)
    except Exception:
        return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python eval_rerank.py <path-to-search_results.json>')
        sys.exit(1)

    path = sys.argv[1]

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = data if isinstance(data, list) else data.get('data', [])

    for p in results:
        p['parsed_price'] = parse_price(p.get('price'))
        p['parsed_rating'] = parse_rating(p.get('rating'))
        p['parsed_reviews'] = parse_reviews(p.get('reviews'))

    price_list = [p['parsed_price'] for p in results if p['parsed_price'] != float('inf')]
    min_price = min(price_list) if price_list else None
    max_price = max(price_list) if price_list else None
    max_reviews = max((p['parsed_reviews'] for p in results), default=0)

    for p in results:
        rating_norm = p['parsed_rating'] / 5.0 if p.get('parsed_rating') is not None else 0
        reviews_norm = (p['parsed_reviews'] / max_reviews) if max_reviews > 0 else 0

        if min_price is None or p['parsed_price'] == float('inf'):
            price_norm = 0
        elif max_price == min_price:
            price_norm = 1.0
        else:
            price_norm = 1 - ((p['parsed_price'] - min_price) / (max_price - min_price))

        p['score'] = 0.5 * rating_norm + 0.3 * reviews_norm + 0.2 * price_norm

    sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)

    print('Top 5 after re-ranking:')
    for i, p in enumerate(sorted_results[:5], start=1):
        print(f"{i}. {p.get('title')} | price={p.get('price')} | rating={p.get('rating')} | reviews={p.get('reviews')} | score={p.get('score'):.4f}")
