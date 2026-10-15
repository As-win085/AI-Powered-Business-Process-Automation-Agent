from datetime import date, timedelta
from decimal import Decimal

from app.services.duplicate_detection import (
    DuplicateCandidate,
    detect_duplicates,
    near_duplicate_score,
    normalize_invoice_number,
    normalize_supplier_name,
)


def _cand(cid, supplier=None, number=None, total=None, when=None, lines=None):
    return DuplicateCandidate(
        cid,
        supplier_name=supplier,
        invoice_number=number,
        total_amount=total,
        invoice_date=when,
        line_items=lines or [],
    )


def test_normalize_invoice_number_strips_punctuation_case_and_zeros():
    assert normalize_invoice_number('INV-00123') == 'inv123'
    assert normalize_invoice_number('inv 123') == 'inv123'
    assert normalize_invoice_number('INV00123') == 'inv123'
    assert normalize_invoice_number('000') == '0'
    assert normalize_invoice_number(None) is None


def test_normalize_supplier_name():
    assert normalize_supplier_name('Acme Corp.') == 'acme corp'
    assert normalize_supplier_name('  ACME   CORP  ') == 'acme corp'
    assert normalize_supplier_name(None) is None


def test_exact_file_duplicate():
    inc = _cand('new')
    results = detect_duplicates(
        inc, [_cand('c1')], file_hash='deadbeef', candidate_hashes={'c1': 'deadbeef'}
    )
    assert results and results[0]['kind'] == 'exact'
    assert results[0]['score'] == 100.0
    assert results[0]['matched_invoice_id'] == 'c1'


def test_business_duplicate_normalized():
    inc = _cand('new', supplier='Acme Corp', number='INV-00123')
    cands = [_cand('c1', supplier='ACME CORP.', number='inv-123')]
    results = detect_duplicates(inc, cands)
    assert results and results[0]['kind'] == 'business'
    assert results[0]['matched_invoice_id'] == 'c1'


def test_near_duplicate_similar_supplier_and_amounts():
    inc = _cand(
        'new',
        supplier='Acme Corporation',
        number='INV-999',
        total=Decimal('1100.00'),
        when=date.today(),
        lines=[{'description': 'Widget A'}, {'description': 'Widget B'}],
    )
    cand = _cand(
        'c1',
        supplier='Acme Corp.',
        number='INV-777',
        total=Decimal('1100.00'),
        when=date.today(),
        lines=[{'description': 'Widget A'}, {'description': 'Widget B'}],
    )
    results = detect_duplicates(inc, [cand])
    assert results and results[0]['kind'] == 'near'
    assert results[0]['score'] >= 80.0


def test_unrelated_invoice_is_not_flagged():
    inc = _cand('new', supplier='Acme', number='A-1', total=Decimal('10'), when=date.today())
    cand = _cand(
        'c2',
        supplier='Globex',
        number='G-9',
        total=Decimal('50000'),
        when=date.today() - timedelta(days=365),
    )
    assert detect_duplicates(inc, [cand]) == []


def test_duplicates_are_always_warnings_never_rejections():
    inc = _cand('new', supplier='Acme Corp', number='INV-1')
    cands = [_cand('c1', supplier='Acme Corp', number='INV-1')]
    for result in detect_duplicates(inc, cands):
        assert result['warning'] is True


def test_near_duplicate_score_bounds():
    a = _cand('a', supplier='Acme', total=Decimal('100'), when=date.today())
    b = _cand('b', supplier='Acme', total=Decimal('100'), when=date.today())
    assert near_duplicate_score(a, b) == 100.0
    c = _cand('c', supplier='Zzz', total=Decimal('1'), when=date.today() - timedelta(days=365))
    assert 0.0 <= near_duplicate_score(a, c) < 100.0
