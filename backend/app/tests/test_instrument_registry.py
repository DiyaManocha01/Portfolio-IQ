from pathlib import Path

from app.services.market_data.instrument_registry import InstrumentRegistry

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "angelone_instruments_sample.json"


def test_is_ready_false_when_file_missing(tmp_path):
    registry = InstrumentRegistry(source_path=tmp_path / "does_not_exist.json")
    assert registry.is_ready() is False


def test_is_ready_true_when_file_present():
    registry = InstrumentRegistry(source_path=FIXTURE_PATH)
    assert registry.is_ready() is True


def test_resolve_known_symbol():
    registry = InstrumentRegistry(source_path=FIXTURE_PATH)
    instrument = registry.resolve("RELIANCE")
    assert instrument is not None
    assert instrument.exchange == "NSE"
    assert instrument.trading_symbol == "RELIANCE-EQ"
    assert instrument.token == "TEST-0001"


def test_resolve_is_case_insensitive():
    registry = InstrumentRegistry(source_path=FIXTURE_PATH)
    assert registry.resolve("reliance") is not None


def test_resolve_unknown_symbol_returns_none_never_fabricates():
    registry = InstrumentRegistry(source_path=FIXTURE_PATH)
    assert registry.resolve("NOTREAL") is None


def test_resolve_all_reports_missing_separately():
    registry = InstrumentRegistry(source_path=FIXTURE_PATH)
    resolved, missing = registry.resolve_all(["RELIANCE", "TCS", "ADANIPORTS"])
    assert set(resolved.keys()) == {"RELIANCE", "TCS"}
    assert missing == ["ADANIPORTS"]


def test_missing_file_resolves_all_as_missing(tmp_path):
    registry = InstrumentRegistry(source_path=tmp_path / "missing.json")
    resolved, missing = registry.resolve_all(["RELIANCE", "TCS"])
    assert resolved == {}
    assert missing == ["RELIANCE", "TCS"]


def test_note_key_is_skipped_not_treated_as_instrument():
    registry = InstrumentRegistry(source_path=FIXTURE_PATH)
    assert registry.resolve("_NOTE") is None


def test_reload_picks_up_file_changes(tmp_path):
    path = tmp_path / "instruments.json"
    path.write_text('{"TCS": {"exchange": "NSE", "tradingsymbol": "TCS-EQ", "symboltoken": "1"}}')
    registry = InstrumentRegistry(source_path=path)
    assert registry.resolve("TCS") is not None
    assert registry.resolve("RELIANCE") is None

    path.write_text(
        '{"TCS": {"exchange": "NSE", "tradingsymbol": "TCS-EQ", "symboltoken": "1"}, '
        '"RELIANCE": {"exchange": "NSE", "tradingsymbol": "RELIANCE-EQ", "symboltoken": "2"}}'
    )
    registry.reload()
    assert registry.resolve("RELIANCE") is not None
