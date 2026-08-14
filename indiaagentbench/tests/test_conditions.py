"""Tests for condition generation and its quality gates.

The gates matter more than they look. A mangled PNR in a Hindi task produces an
unsolvable prompt, the agent fails, and the failure is indistinguishable from
the language effect the study is trying to measure -- it would confirm the
hypothesis for entirely the wrong reason. So the checker is tested against
deliberately broken translations, the same way the verifiers are tested against
near-misses.

Run: python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iab.common import DATA, load_json                      # noqa: E402
from iab.script_utils import (digits_in, latin_ratio,        # noqa: E402
                              mixed_script_words, scripts_in)
from iab.translate import clean, prompt_for                  # noqa: E402
from iab.validate_conditions import check, english_ratio     # noqa: E402

EN = ("I need to cancel my train ticket. My PNR is 4501234567. Please cancel all "
      "three passengers and tell me how much money I will get back.")

HI = ("मुझे अपना ट्रेन टिकट रद्द करना है। मेरा PNR 4501234567 है। कृपया तीनों "
      "यात्रियों का टिकट रद्द कर दीजिए और बताइए कि मुझे कितने पैसे वापस मिलेंगे।")

HINGLISH = ("Mujhe apna train ticket cancel karna hai. Mera PNR 4501234567 hai. "
            "Please teeno passengers ka ticket cancel kar dijiye aur batayiye "
            "mujhe kitna refund milega.")

TA = ("எனது ரயில் டிக்கெட்டை ரத்து செய்ய வேண்டும். எனது PNR 4501234567. "
      "மூன்று பயணிகளின் டிக்கெட்டையும் ரத்து செய்து, எவ்வளவு பணம் திரும்பக் "
      "கிடைக்கும் என்று சொல்லுங்கள்.")


def task(condition, text, source="human"):
    return {"task_id": "rail-001", "domain": "rail", "condition": condition,
            "source": source, "user_goal": text, "user_goal_en": EN}


class TestScriptUtils(unittest.TestCase):

    def test_detects_scripts(self):
        self.assertEqual(scripts_in(HI) - {"Latn"}, {"Deva"})
        self.assertEqual(scripts_in(TA) - {"Latn"}, {"Taml"})
        self.assertEqual(scripts_in(HINGLISH), {"Latn"})

    def test_finds_script_mixed_words(self):
        # Tamil word with a Devanagari character spliced in -- the exact bug
        # found in four of the seed aliases
        self.assertTrue(mixed_script_words("மீனா குमाரி"))
        self.assertFalse(mixed_script_words("மீனா குமாரி"))

    def test_latin_and_digits(self):
        self.assertEqual(digits_in(EN), ["4501234567"])
        self.assertEqual(digits_in(HI), ["4501234567"])
        self.assertEqual(latin_ratio(HINGLISH), 1.0)
        self.assertLess(latin_ratio(HI), 0.2)


class TestSeedIsScriptClean(unittest.TestCase):
    """Regression: four seeded aliases once spliced Devanagari into Tamil."""

    def test_no_alias_mixes_scripts(self):
        for c in load_json(DATA / "schemes.json")["citizens"]:
            for alias in c["aliases"]:
                with self.subTest(citizen=c["citizen_id"]):
                    self.assertEqual(
                        mixed_script_words(alias), [],
                        f"{c['citizen_id']} alias is script-mixed")

    def test_every_citizen_has_native_script_aliases(self):
        """Without these, C2-C5 scheme tasks die at the first tool call.

        The lookup database is romanized; a Hindi or Tamil user naming
        themselves would match nothing, zeroing every scheme task at step one
        and flattening the survival curves the study depends on.
        """
        for c in load_json(DATA / "schemes.json")["citizens"]:
            found = set()
            for alias in c["aliases"]:
                found |= scripts_in(alias)
            with self.subTest(citizen=c["citizen_id"]):
                self.assertIn("Deva", found)
                self.assertIn("Taml", found)


class TestGatesAcceptGoodTranslations(unittest.TestCase):

    def test_clean_hindi_passes(self):
        hard, _ = check(task("C2", HI))
        self.assertEqual(hard, [])

    def test_clean_tamil_passes(self):
        hard, _ = check(task("C4", TA))
        self.assertEqual(hard, [])

    def test_clean_hinglish_passes(self):
        hard, soft = check(task("C3", HINGLISH))
        self.assertEqual(hard, [])
        self.assertNotIn("code-mix", " ".join(soft))


class TestGatesRejectBadTranslations(unittest.TestCase):
    """Each of these would otherwise masquerade as a language effect."""

    def test_mangled_pnr_is_caught(self):
        broken = HI.replace("4501234567", "4501234576")
        hard, _ = check(task("C2", broken))
        self.assertTrue(any("digits changed" in h for h in hard))

    def test_spelled_out_number_is_caught(self):
        broken = HI.replace("4501234567", "चार पाँच शून्य एक")
        hard, _ = check(task("C2", broken))
        self.assertTrue(any("digits changed" in h for h in hard))

    def test_wrong_script_is_caught(self):
        hard, _ = check(task("C2", TA))          # Tamil submitted as C2
        self.assertTrue(any("foreign script" in h or "no Deva" in h for h in hard))

    def test_native_script_leaking_into_romanized_condition(self):
        hard, _ = check(task("C3", HI))
        self.assertTrue(any("Latin only" in h for h in hard))

    def test_echoed_english_is_caught(self):
        hard, _ = check(task("C2", EN))
        self.assertTrue(any("identical" in h for h in hard))

    def test_empty_is_caught(self):
        hard, _ = check(task("C2", "   "))
        self.assertTrue(hard)

    def test_script_mixed_word_is_caught(self):
        hard, _ = check(task("C4", TA.replace("மூன்று", "மூन்று")))
        self.assertTrue(any("script-mixed" in h for h in hard))


class TestSoftFlags(unittest.TestCase):

    def test_draft_is_flagged_until_a_human_signs_off(self):
        _, soft = check(task("C2", HI, source="draft"))
        self.assertTrue(any("unvalidated" in s for s in soft))
        _, soft = check(task("C2", HI, source="human"))
        self.assertFalse(any("unvalidated" in s for s in soft))

    def test_word_for_word_transliteration_is_flagged(self):
        """C3 should be code-mixed, not Hindi spelled in Latin letters."""
        pure = ("Mujhe apna rail patra radd karna hai. Mera PNR 4501234567 hai. "
                "Kripya teeno yatriyon ka patra radd kar dijiye.")
        _, soft = check(task("C3", pure))
        self.assertTrue(any("code-mix density" in s for s in soft))

    def test_english_ratio_separates_the_two(self):
        self.assertGreater(english_ratio(HINGLISH), english_ratio(
            "Mujhe apna rail patra radd karna hai kripya"))


class TestPrompts(unittest.TestCase):

    def test_romanized_prompt_forbids_native_script(self):
        p = prompt_for("C3", EN)
        self.assertIn("Latin script only", p)
        self.assertIn("Devanagari", p)

    def test_prompts_pin_numeral_form_in_both_directions(self):
        """Digits must stay digits AND words must stay words.

        Pinning only the digits let the model render "twelve thousand" as
        12000, which preserves the value but changes the numeral form -- a
        second variable moving alongside language, and it made sch-012 easier
        in Hindi than in English.
        """
        for cond in ("C2", "C3"):
            p = prompt_for(cond, EN)
            with self.subTest(condition=cond):
                flat = " ".join(p.split())
                self.assertIn("same digits", flat)
                self.assertIn("stay in words", flat)
                self.assertIn("12000", flat)

    def test_clean_strips_model_preamble(self):
        self.assertEqual(clean('Here is the translation: "नमस्ते"'), "नमस्ते")
        self.assertEqual(clean("  नमस्ते  "), "नमस्ते")


if __name__ == "__main__":
    unittest.main(verbosity=2)
