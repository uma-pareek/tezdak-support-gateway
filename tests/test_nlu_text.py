import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tezdak.nlu import entities, language, normalizer  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 3, 10, 9, 30, tzinfo=IST)  # a Tuesday


class NormalizerTests(unittest.TestCase):
    def test_spelling_variants(self):
        self.assertEqual(normalizer.normalize_text("nahin mila"), "nahi mila")
        self.assertEqual(normalizer.normalize_text("kaha hai"), "kahan hai")
        self.assertEqual(normalizer.normalize_text("milaa nai"), "mila nahi")
        self.assertEqual(normalizer.normalize_text("parsel aya"), "parcel aaya")

    def test_english_words_untouched(self):
        self.assertEqual(normalizer.normalize_text("he is here"), "he is here")
        self.assertEqual(normalizer.normalize_text("rs 50"), "rs 50")

    def test_number_words(self):
        n = normalizer.normalize("teen sau rupaye kat gaye")
        self.assertIn("300", n.text)
        self.assertEqual(n.numbers[0][1], 300)
        self.assertIn("2000", normalizer.normalize_text("do hazar chahiye"))
        self.assertIn("2000", normalizer.normalize_text("2 hazar chahiye"))

    def test_emoji_and_whitespace(self):
        self.assertEqual(normalizer.normalize_text("  where   is it \U0001F621\U0001F621 "), "where is it")
        self.assertEqual(normalizer.normalize_text("nahiiiii!!!"), "nahi!")

    def test_devanagari_table(self):
        self.assertEqual(normalizer.normalize_text("पार्सल कहाँ है"), "parcel kahan hai")

    def test_date_words(self):
        self.assertEqual(normalizer.resolve_date_word("kal", NOW).date(), date(2026, 3, 11))
        self.assertEqual(normalizer.resolve_date_word("parso", NOW).date(), date(2026, 3, 12))
        self.assertEqual(normalizer.resolve_date_word("aaj", NOW).date(), date(2026, 3, 10))
        self.assertEqual(normalizer.resolve_date_word("friday", NOW).date(), date(2026, 3, 13))
        self.assertIsNone(normalizer.resolve_date_word("kal", None))
        self.assertIsNone(normalizer.resolve_date_word("banana", NOW))

    def test_kal_past(self):
        n = normalizer.normalize("kal rider nahi aaya", NOW)
        self.assertEqual(n.dates[0][1], date(2026, 3, 9))
        n2 = normalizer.normalize("kal deliver karo", NOW)
        self.assertEqual(n2.dates[0][1], date(2026, 3, 11))


class EntityTests(unittest.TestCase):
    def test_awb(self):
        self.assertEqual(entities.extract_awbs("my awb tz1234567 and TZ7654321, tz1234567"), ["TZ1234567", "TZ7654321"])
        self.assertEqual(entities.extract_awbs("TZ123"), [])

    def test_pincode_excludes_awb_and_phone(self):
        txt = "TZ1234567 pincode 560001 phone 9876543210"
        self.assertEqual(entities.extract_pincodes(txt), ["560001"])

    def test_phone(self):
        self.assertEqual(entities.extract_phones("call +91 98765 43210"), ["9876543210"])
        self.assertEqual(entities.extract_phones("12345"), [])

    def test_amounts(self):
        self.assertEqual(entities.extract_amounts("Rs.1,200 and 50 rupees and ₹300"), [1200, 50, 300])

    def test_time_of_day(self):
        self.assertEqual(entities.extract_time_of_day("subah ya shaam"), ["morning", "evening"])
        self.assertEqual(entities.extract_clock_times("after 6 pm or 11:30 am"), [(18, 0), (11, 30)])
        self.assertEqual(entities.extract_clock_times("13 pm"), [])

    def test_extract_all(self):
        e = entities.extract("TZ1234567 kal shaam deliver karo, teen sau rupaye", NOW)
        self.assertEqual(e.awb, "TZ1234567")
        self.assertEqual(e.amounts, [300])
        self.assertEqual(e.dates[0][1], date(2026, 3, 11))
        self.assertEqual(e.times_of_day, ["evening"])
        self.assertEqual(e.to_dict()["dates"][0][1], "2026-03-11")


class LanguageTests(unittest.TestCase):
    def test_english(self):
        r = language.detect_language("Where is my parcel? Please update me.")
        self.assertEqual(r.label, "english")
        self.assertGreater(r.confidence, 0.5)

    def test_hinglish(self):
        self.assertEqual(language.detect_language("mera parcel kab aayega").label, "hinglish")
        self.assertEqual(language.detect_language("Rider aaya hi nahi").label, "hinglish")

    def test_hindi(self):
        self.assertEqual(language.detect_language("मेरा पार्सल कहाँ है").label, "hindi")

    def test_mixed(self):
        self.assertEqual(language.detect_language("मेरा parcel कहाँ hai").label, "mixed")

    def test_weak_marker_stays_english(self):
        self.assertEqual(language.detect_language("I want to talk to a manager").label, "english")

    def test_empty(self):
        r = language.detect_language("")
        self.assertEqual((r.label, r.confidence < 0.5), ("english", True))

    def test_reply_language(self):
        self.assertEqual(language.reply_language("hindi"), "hinglish")
        self.assertEqual(language.reply_language("english"), "english")


if __name__ == "__main__":
    unittest.main()
