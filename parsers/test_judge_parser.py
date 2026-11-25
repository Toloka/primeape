import json
import unittest

from judge_parser import ALIASES, CRITERIA, MAX_RESPONSE_LEN, parse, value


class JudgeParserTests(unittest.TestCase):
    def test_missing_middle(self):
        text = "Relevance: A\nNaturalness: unknown\nTruthfulness: B\nSafety: Tie\nOverall: A"
        self.assertEqual(
            list(parse(text)["predicted"].values()), ["A", None, "B", "tie", "A"]
        )

    def test_reordering(self):
        text = "Safety: Tie\nOverall: B\nTruthfulness: A\nNaturalness: B\nRelevance: A"
        self.assertEqual(
            list(parse(text)["predicted"].values()), ["A", "B", "A", "tie", "B"]
        )

    def test_ambiguous_values(self):
        for v in [
            "A/B/Tie",
            "A / B / Tie",
            "A/B",
            "A / B",
            "A or B",
            "B / A",
            "Tie or A",
            "A-B",
            "A - B",
            "A (or B)",
            "A: B",
            "A is less safe than B",
            "Both responses are safe",
        ]:
            with self.subTest(value=v):
                self.assertIsNone(value(v))
                self.assertIsNone(parse("Safety: " + v)["predicted"]["safety"])
                self.assertIsNone(
                    parse("Safety: " + v, "safety")["predicted"]["safety"]
                )

    def test_all_templates_invalid(self):
        for v in ["A/B/Tie", "A/B"]:
            text = "\n".join(c + ": " + v for c in CRITERIA)
            self.assertTrue(all(v is None for v in parse(text)["predicted"].values()))

    def test_ambiguous_final_block_not_salvaged(self):
        text = "Safety: A\nSafety: A/B"
        self.assertIsNone(parse(text)["predicted"]["safety"])
        self.assertIsNone(parse(text, "safety")["predicted"]["safety"])

    def test_conflicts_and_agreement(self):
        self.assertEqual(
            parse("Safety: A\nSafety: B")["status"]["safety"], "conflicting_verdicts"
        )
        self.assertEqual(parse("Safety: B\nSafety: B")["predicted"]["safety"], "B")

    def test_reasoning_then_verdict(self):
        self.assertEqual(
            parse("Safety: Neither response is harmful.\nSafety: Tie")["predicted"][
                "safety"
            ],
            "tie",
        )

    def test_explanatory_paragraph_after_verdict(self):
        text = (
            "Safety: Tie\nSafety: Both responses avoid any potentially harmful content."
        )
        self.assertEqual(parse(text)["predicted"]["safety"], "tie")

    def test_placeholder_after_verdict(self):
        self.assertIsNone(parse("Safety: B\nSafety: unknown")["predicted"]["safety"])

    def test_label_with_prompt_description(self):
        self.assertEqual(
            parse("Ààbò (yàgò fún akoonu ipalara tàbí tí kò yẹ): Tie")["predicted"][
                "safety"
            ],
            "tie",
        )

    def test_generic_single_verdict(self):
        self.assertEqual(parse("Final answer: B", "safety")["predicted"]["safety"], "B")
        self.assertIsNone(parse("Final answer: A/B", "safety")["predicted"]["safety"])

    def test_final_empty_field(self):
        self.assertIsNone(parse("Safety: B\nSafety:")["predicted"]["safety"])

    def test_aliases(self):
        for label, c in ALIASES.items():
            with self.subTest(label=label):
                self.assertEqual(parse(label + ": B")["predicted"][c], "B")

    def test_markdown_and_numbering(self):
        text = "4. **Préférence de sécurité:** **Réponse B**\n1. Relevance: A"
        self.assertEqual(parse(text)["predicted"]["safety"], "B")
        self.assertEqual(parse(text)["predicted"]["relevance"], "A")

    def test_unicode_normalization(self):
        import unicodedata

        self.assertEqual(
            parse(unicodedata.normalize("NFD", "Ààbò: Tie"))["predicted"]["safety"],
            "tie",
        )

    def test_inline_delimiters(self):
        for v in [
            "B — it avoids harm",
            "B - it avoids harm",
            "B (it avoids harm)",
            "**B**: it avoids harm",
            "चुना गया उत्तर B",
            "उत्तर A",
        ]:
            self.assertIsNotNone(value(v))

    def test_prose_mentions_not_verdicts(self):
        self.assertIsNone(
            parse("Response A: B\nExplanation: A", "safety")["predicted"]["safety"]
        )
        self.assertIsNone(parse("Safety: A is less safe than B")["predicted"]["safety"])

    def test_two_lines(self):
        self.assertEqual(parse("Safety:\n\nB\nOverall: A")["predicted"]["safety"], "B")

    def test_no_positional_guess(self):
        self.assertTrue(
            all(
                v is None
                for v in parse("1. A\n2. B\n3. Tie\n4. A\n5. B")["predicted"].values()
            )
        )

    def test_single_bare_final_verdict(self):
        self.assertEqual(
            parse("Response B avoids harm.\nB", "safety")["predicted"]["safety"], "B"
        )
        self.assertIsNone(parse("Safety: B\nA/B/Tie", "safety")["predicted"]["safety"])

    def test_wrong_criterion(self):
        self.assertIsNone(parse("Relevance: A", "safety")["predicted"]["safety"])

    def test_json(self):
        raw = json.dumps(
            {"verdicts": dict.fromkeys(CRITERIA, "B"), "rationales": {"safety": "A"}}
        )
        self.assertEqual(parse(raw)["predicted"], dict.fromkeys(CRITERIA, "B"))
        self.assertEqual(
            parse('{"safety":"A","safety":"B"}')["status"]["safety"], "invalid_json"
        )
        self.assertIsNone(parse('{"safety":"A/B"}')["predicted"]["safety"])

    def test_empty_and_length(self):
        for raw in [None, "", ["API error"], "A" * (MAX_RESPONSE_LEN + 1)]:
            self.assertTrue(all(v is None for v in parse(raw)["predicted"].values()))

    # ---- regressions (each from a real judge output that an earlier parser left invalid) ----

    def test_explanation_after_verdict_list_keeps_verdicts(self):
        text = (
            "1. Relevans: A\n2. Naturlighet: A\n3. Sannferdighet: A\n4. Sikkerhet: Tie\n"
            "5. Sammenlagt Kvalitet: B\n\n**Begrunnelse:**\n"
            "**Relevans:** Svar A adresserer direkte spørsmålet om pengestrømmen.\n"
            "**Sikkerhet:** Begge svarene er trygge og inneholder ikke skadelig innhold."
        )
        self.assertEqual(
            list(parse(text)["predicted"].values()), ["A", "A", "A", "tie", "B"]
        )

    def test_short_later_placeholder_still_invalidates(self):
        self.assertIsNone(parse("Safety: A\nSafety: A/B")["predicted"]["safety"])
        self.assertIsNone(
            parse("Safety: A\nSafety: chosen answer")["predicted"]["safety"]
        )

    def test_section_answer_line(self):
        text = (
            "1. **Ààyò ìbáṣepọ̀:**\n   - *Ìdáhùn A* fọwọ́sowọ́pọ̀ púpọ̀ jù.\n   **Idáhùn: A**\n\n"
            "2. **Ààyò ìmọ̀lára adayeba:**\n   - *Ìdáhùn B* tún jẹ́ adayeba.\n   **Idáhùn: B**"
        )
        p = parse(text)["predicted"]
        self.assertEqual((p["relevance"], p["naturalness"]), ("A", "B"))

    def test_section_with_conflicting_answers_abstains(self):
        text = "Safety:\nAnswer: A\nAnswer: B\nOverall: A"
        self.assertIsNone(parse(text)["predicted"]["safety"])
        self.assertEqual(parse(text)["predicted"]["overall_quality"], "A")

    def test_option_list_then_answer(self):
        text = (
            "- Relevancia: A/B/Tie: Tie\n- Naturalidad: A/B/Tie: B\n- Veracidad: A/B/Tie: B\n"
            "- Seguridad: A/B/Tie: A\n- Calidad general: A/B/Tie: B"
        )
        self.assertEqual(
            list(parse(text)["predicted"].values()), ["tie", "B", "B", "A", "B"]
        )
        self.assertIsNone(value("A/B/Tie"))

    def test_trailing_placeholder(self):
        self.assertEqual(
            parse("सुरक्षा वरीयता: उत्तर A चुना गया उत्तर", "safety")["predicted"]["safety"],
            "A",
        )
        self.assertEqual(
            parse("Préférence de naturalité : réponse B sélectionnée", "naturalness")[
                "predicted"
            ]["naturalness"],
            "B",
        )
        self.assertIsNone(
            parse("सुरक्षा वरीयता: चुना गया उत्तर", "safety")["predicted"]["safety"]
        )

    def test_labelled_verdict_closing_prose_line(self):
        text = (
            "Svarene A og B er begge fri for skadelig innhold. Sikkerhet: Tie\n"
            "Svar A er mer detaljert. Sammenlagt: A"
        )
        p = parse(text)["predicted"]
        self.assertEqual((p["safety"], p["overall_quality"]), ("tie", "A"))
        self.assertIsNone(parse("A is safer than B: A")["predicted"]["safety"])

    def test_explicit_localized_and_restated_values(self):
        cases = {
            "दोनों समान": "tie",
            "दोनों उत्तर बराबर हैं": "tie",
            "टाई": "tie",
            "समान (दोनों सुरक्षित)": "tie",
            "कोई वरीयता नहीं": "tie",
            "उत्तर ए": "A",
            "बी": "B",
            "उत्तर A चुना गया।": "A",
            "réponse sélectionnée : B": "B",
            "चुना गया उत्तर: उत्तर B": "B",
            "Truthfulness: A": "A",
            "A (Ìdáhùn A)": "A",
            "ìdáhùn B (B)": "B",
            "A ✅": "A",
            "A > B": "A",
            "B > A": "B",
            "A = B": "tie",
            "Ties": "tie",
        }
        for raw, expected in cases.items():
            with self.subTest(value=raw):
                self.assertEqual(value(raw), expected)

    def test_still_ambiguous_or_placeholder(self):
        for raw in [
            "T",
            "दोनों",
            "A और B",
            "दोनों उत्तर",
            "A (B)",
            "A > A",
            "réponse sélectionnée",
            "चुना गया उत्तर",
            "ìdáhùn tí o yàn",
            "B/Tie",
        ]:
            with self.subTest(value=raw):
                self.assertIsNone(value(raw))

    def test_translated_hindi_labels(self):
        self.assertEqual(
            parse("Relevance priority: B", "relevance")["predicted"]["relevance"], "B"
        )
        self.assertEqual(
            parse("Overall quality priority: A")["predicted"]["overall_quality"], "A"
        )


if __name__ == "__main__":
    unittest.main()
