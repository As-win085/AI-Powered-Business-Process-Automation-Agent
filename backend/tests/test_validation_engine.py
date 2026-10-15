def test_validation_engine_stores_all_results():
    from app.services.validation_engine import ValidationEngine

    res = ValidationEngine().validate({})
    assert len(res) == 5
    for r in res:
        assert {"rule", "severity", "details", "pass"}.issubset(r.keys())
