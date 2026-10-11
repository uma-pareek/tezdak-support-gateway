"""Customer-facing sentences used by more than one feature.

Each key has an English and a Hinglish version. Missing Hinglish falls back to
English. Keep sentences short; the model rephrases anyway.
"""

BANK = {
    "ask_awb": ("Could you share your tracking number? It starts with TZ.",
                "Apna tracking number bhej dijiye, woh TZ se shuru hota hai."),
    "ask_vpa": ("Please share the UPI id where you want the refund, like name@upi.",
                "Refund ke liye apna UPI id bhejiye, jaise name@upi."),
    "ask_address": ("Please send the full new address with the pincode.",
                    "Pura naya address pincode ke saath bhejiye."),
    "ask_rating": ("How would you rate the delivery, from 1 to 5?",
                   "Delivery ko 1 se 5 mein kitni rating denge?"),
    "thanks_feedback": ("Thank you, your feedback is saved.", "Shukriya, aapka feedback save ho gaya."),
    "handoff_done": ("I have passed this to a colleague who will contact you soon.",
                     "Maine yeh ek colleague ko de diya hai, woh jaldi aapse baat karenge."),
    "cutoff": ("Same-day slots close at 11:00 AM.", "Aaj ka slot subah 11:00 baje tak hi milta hai."),
    "sorry_delay": ("Sorry for the delay.", "Der ke liye maaf kijiye."),
}


def say(key, language="english", **fmt):
    en, hi = BANK[key]
    text = hi if language == "hinglish" and hi else en
    return text.format(**fmt) if fmt else text


def keys():
    return sorted(BANK)
