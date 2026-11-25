CRITERIA = ("relevance", "naturalness", "truthfulness", "safety", "overall_quality")
# Selected-prompt labels for all seven languages, plus common English/French forms.
# Extend only using manually verified examples; this is not exhaustive localization.
LABELS = {
    "relevance": [
        "relevance",
        "relevance preference",
        "pertinence",
        "préférence de pertinence",
        "प्रासंगिकता वरीयता",
        "relevans",
        "relevancia",
        "مطابقت",
        "Ìbáṣepọ̀",
    ],
    "naturalness": [
        "naturalness",
        "naturalness preference",
        "naturalité",
        "préférence de naturalité",
        "स्वाभाविकता वरीयता",
        "naturlighet",
        "naturalidad",
        "قدرتی انداز",
        "Ìmọ̀lára adayeba",
    ],
    "truthfulness": [
        "truthfulness",
        "truthfulness preference",
        "véracité",
        "préférence de véracité",
        "सत्यता वरीयता",
        "sannferdighet",
        "veracidad",
        "سچائی",
        "Òtítọ́",
    ],
    "safety": [
        "safety",
        "safety preference",
        "sécurité",
        "préférence de sécurité",
        "सुरक्षा वरीयता",
        "sikkerhet",
        "seguridad",
        "حفاظت",
        "Ààbò",
    ],
    "overall_quality": [
        "overall_quality",
        "overall quality",
        "overall",
        "overall quality preference",
        "qualité générale",
        "préférence de qualité générale",
        "समग्र गुणवत्ता वरीयता",
        "sammenlagt",
        "calidad general",
        "مجموعی معیار",
        "Lapapọ̀",
    ],
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result
