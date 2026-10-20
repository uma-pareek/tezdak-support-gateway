"""Escalation wording v2 (Aug). Adds time expectations and a Hinglish line per reason."""

ESCALATION_V2 = {
    "default": "I have handed this to a colleague. You should hear from them within 24 hours.",
    "ndr": "I have asked the team to check what happened at your door. They will call you today or tomorrow.",
    "not_received": "I have raised this with the team and given them your AWB. They will contact you within 1 working day.",
    "angry": "I am sorry. I am asking a senior colleague to call you, you do not need to repeat everything.",
}

ESCALATION_V2_HINGLISH = {
    "default": "Maine ye aage team ko de diya hai. 24 ghante ke andar aapko call aayega.",
    "ndr": "Maine team se kaha hai ki aapke darwaze par kya hua wo check karein. Aaj ya kal call aayega.",
    "not_received": "Team ko aapka AWB de diya hai. 1 working day me contact karenge.",
    "angry": "Maaf kijiye. Senior colleague aapko call karenge, dobara sab batane ki zarurat nahi.",
}
