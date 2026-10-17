"""scripts/nli_measure.py: pairs each card sentence with its quote (or the filing window it rests on) and sets
the NLI flags against an audit round. The model itself is not loaded here; a stand-in scorer is."""

import importlib.util
import json
import pathlib


def _load():
    spec = importlib.util.spec_from_file_location(
        "nli_measure", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "nli_measure.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FILING = ("Mahindra & Mahindra Limited has agreed to acquire 58.96% of the equity share capital of the Company. "
          "The acquisition is subject to receipt of the required statutory approval from the Competition Commission "
          "of India. The Board meeting commenced at 11 am and concluded at 1 pm.")


def test_quoted_sentences_use_their_quote_and_the_rest_the_window_that_matches():
    m = _load()
    card = {"headline": "M&M to acquire 58.96% of SML, CCI approval pending",
            "what_happened": [{"text": "M&M agreed to buy 58.96%.", "quote": "has agreed to acquire 58.96%"}],
            "key_numbers": [{"label": "Stake", "value": "58.96%", "quote": None}]}
    got = m.pairs(card, FILING)
    assert got[0] == ("what_happened", "has agreed to acquire 58.96%", "M&M agreed to buy 58.96%.")
    assert got[1][0] == "key_numbers" and "58.96%" in got[1][1] and got[1][2] == "Stake 58.96%"
    assert got[2][0] == "headline" and "Competition Commission" in got[2][1]


def test_flags_are_set_against_the_audit_and_the_decision_rule_holds(tmp_path):
    m = _load()
    cards = {
        "ok1": {"headline": "M&M agrees to buy 58.96% of SML, subject to CCI approval", "review": {}, "grounding": {}},
        "ok2": {"headline": "M&M agrees to buy 58.96% of SML", "review": {}, "grounding": {}},
        "bad": {"headline": "M&M completes the acquisition of 58.96% of SML", "review": {}, "grounding": {}},
    }
    for news_id, card in cards.items():
        (tmp_path / f"{news_id}.card.json").write_text(json.dumps(card))
        (tmp_path / f"{news_id}.pdf.txt").write_text(FILING)
    verdicts = {"ok1": {"verdict": "OK", "issues": []}, "ok2": {"verdict": "OK", "issues": []},
                "bad": {"verdict": "WRONG", "issues": [{"class": "event_type"}]}}
    entail = lambda premise, claim: 0.1 if "completes" in claim else 0.95   # a model that reads stages right
    result = m.measure(m.load_export(tmp_path), verdicts, entail, 0.5)
    assert result["by_verdict"]["WRONG"]["flagged"] == 1 and result["by_verdict"]["OK"]["flagged"] == 0
    assert result["by_class"]["event_type"]["flagged"] == 1
    useful, why = m.decide(result)
    assert useful and "worth wiring in" in why
    assert "| WRONG | 1 | 1 (100%)" in m.report(result, 0.5)

    lenient = m.measure(m.load_export(tmp_path), verdicts, lambda p, c: 0.95, 0.5)
    assert m.decide(lenient)[0] is False, "a model that flags nothing is not worth wiring in"
