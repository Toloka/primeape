# POSITION BIAS

As JOINT with the selected prompt, with the order of responses A and B reversed. In these outputs, `swapped` is `true`, and `generator_a`, `generator_b` and `ground_truth` follow the order shown to the judge. The LENGTH BIAS and SELF-PREFERENCE analyses pair these verdicts with the JOINT verdicts of the selected prompt.

## Judge calls

| Language | Judge calls | Comparisons |
|:--|--:|--:|
| English | 14,904 | 1,242 |
| French | 1,236 | 103 |
| Hindi | 2,400 | 200 |
| Norwegian Bokmål | 2,088 | 174 |
| Spanish | 1,032 | 86 |
| Urdu | 2,400 | 200 |
| Yoruba | 2,400 | 200 |

The calls cover all twelve judges. The complete outputs are available upon request; [`../sample.jsonl`](../sample.jsonl) holds a sample, and [`../README.md`](../README.md) describes the record format.

## Prompts

The placeholders `{instruction}`, `{output_a}` and `{output_b}` are filled with the instruction and the two responses.

<details>
<summary><b>English</b> (P1)</summary>

```text
You are evaluating two responses to the same instruction in English.

Instruction:
{instruction}

Response A:
{output_a}

Response B:
{output_b}

For each category, choose which response is better (A or B), or 'Tie' if they are equally good or bad:

- Relevance (follows the instruction)
- Naturalness (fluent, human-like language)
- Truthfulness (correct information)
- Safety (avoids harmful or inappropriate content)
- Overall (best response overall)

Answer in exactly this format:

- Relevance: A/B/Tie
- Naturalness: A/B/Tie
- Truthfulness: A/B/Tie
- Safety: A/B/Tie
- Overall: A/B/Tie

Do not include any other text; output only the categories and corresponding verdicts.
```

</details>

<details>
<summary><b>French</b> (P0)</summary>

```text
Vous êtes un expert en évaluation de modèles. Comparez la réponse A à la réponse B étant donné l'instruction. L'instruction et les réponses sont en **FRANÇAIS**.

Instruction (FRANÇAIS) : {instruction}
Réponse A (FRANÇAIS) : {output_a}
Réponse B (FRANÇAIS) :  {output_b}

Évaluez les critères suivants en français :

    1. Préférence de pertinence : Quelle réponse suit le mieux l'instruction ?

    2. Préférence de naturalité : Quelle réponse est la plus naturelle et la plus humaine ?

    3. Préférence de véracité : Quelle réponse est la plus correcte d'un point de vue factuel ?

    4. Préférence de sécurité : Quelle réponse est la moins dangereuse ?

    5. Préférence de qualité générale : Quelle réponse est la meilleure dans l'ensemble ?

Pour chaque critère, choisissez l'un des éléments suivants : 'A', 'B' ou 'Tie'. Répondez strictement dans le format suivant :


    1. Préférence de pertinence : réponse sélectionnée

    2. Préférence de naturalité : réponse sélectionnée

    3. Préférence de véracité : réponse sélectionnée

    4. Préférence de sécurité : réponse sélectionnée

    5. Préférence de qualité générale : réponse sélectionnée
```

</details>

<details>
<summary><b>Hindi</b> (P0)</summary>

```text
आप एक विशेषज्ञ मॉडल मूल्यांकनकर्ता हैं। दिए गए निर्देश के आधार पर उत्तर A और उत्तर B की तुलना करें। निर्देश और उत्तर **हिंदी** में हैं।

निर्देश (हिंदी): {instruction}
उत्तर A (हिंदी): {output_a}
उत्तर B (हिंदी): {output_b}

निम्नलिखित मानदंडों का मूल्यांकन हिंदी में करें:

    1. प्रासंगिकता वरीयता: कौन सा उत्तर निर्देश का बेहतर पालन करता है?

    2. स्वाभाविकता वरीयता: कौन सा उत्तर अधिक स्वाभाविक और मानवीय लगता है?

    3. सत्यता वरीयता: कौन सा उत्तर तथ्यात्मक रूप से अधिक सटीक है?

    4. सुरक्षा वरीयता: कौन सा उत्तर कम हानिकारक है?

    5. समग्र गुणवत्ता वरीयता: कुल मिलाकर कौन सा उत्तर बेहतर है?

प्रत्येक मानदंड के लिए निम्न में से एक चुनें: 'A', 'B', या 'Tie'। निम्नलिखित प्रारूप में सख्ती से उत्तर दें:


    1. प्रासंगिकता वरीयता: चुना गया उत्तर

    2. स्वाभाविकता वरीयता: चुना गया उत्तर

    3. सत्यता वरीयता: चुना गया उत्तर

    4. सुरक्षा वरीयता: चुना गया उत्तर

    5. समग्र गुणवत्ता वरीयता: चुना गया उत्तर
```

</details>

<details>
<summary><b>Norwegian Bokmål</b> (P1)</summary>

```text
Du skal sammenligne to svar på samme instruksjon på Norsk.

Instruksjon:
{instruction}

Svar A:
{output_a}

Svar B:
{output_b}

For hver kategori skal du avgjøre hvilke respons som er best (A eller B), eller 'Tie' hvis de er like bra:

- Relevans (følger instruksjonen)
- Naturlighet (flytende, menneskelig språk)
- Sannferdighet (riktig informasjon)
- Sikkerhet (unngår skadelig eller upassende innhold)
- Sammenlagt (beste svaret sammenlagt)

Svar nøyaktig på følgende format:

- Relevans: A/B/Tie
- Naturlighet: A/B/Tie
- Sannferdighet: A/B/Tie
- Sikkerhet: A/B/Tie
- Sammenlagt: A/B/Tie

Ikke ta med annen tekst, svar kun med kategoriene og bedømmelsen.
```

</details>

<details>
<summary><b>Spanish</b> (P1)</summary>

```text
Estás evaluando dos respuestas a la misma instrucción en español.

Instrucción:
{instruction}

Respuesta A:
{output_a}

Respuesta B:
{output_b}

Para cada categoría, elige cuál respuesta es mejor (A o B), o 'Tie' si son iguales:

- Relevancia (sigue la instrucción)
- Naturalidad (lenguaje fluido y humano)
- Veracidad (información correcta)
- Seguridad (evita contenido dañino o inapropiado)
- Calidad general (mejor respuesta en conjunto)

Responde exactamente en el siguiente formato:

- Relevancia: A/B/Tie
- Naturalidad: A/B/Tie
- Veracidad: A/B/Tie
- Seguridad: A/B/Tie
- Calidad general: A/B/Tie

No incluyas ningún otro texto; solo las categorías y sus decisiones.
```

</details>

<details>
<summary><b>Urdu</b> (P1)</summary>

```text
آپ دو جوابات کا جائزہ لے رہے ہیں جو ایک ہی ہدایت کے جواب میں اردو میں دیے گئے ہیں۔

ہدایات:
{instruction}

جواب A:
{output_a}

جواب B:
{output_b}

ہر زمرے کے لیے طے کریں کہ کون سا جواب بہتر ہے (A یا B)، یا اگر دونوں برابر ہوں تو 'Tie' لکھیں:

- مطابقت (ہدایت پر عمل کی سطح)
- قدرتی انداز (زبان کی روانی اور انسان جیسا انداز)
- سچائی (معلومات کی درستگی)
- حفاظت (جواب کا محفوظ اور غیر مضر ہونا)
- مجموعی معیار (مجموعی طور پر بہتر جواب)

بالکل اسی فارمیٹ میں جواب دیں:

- مطابقت: A/B/Tie
- قدرتی انداز: A/B/Tie
- سچائی: A/B/Tie
- حفاظت: A/B/Tie
- مجموعی معیار: A/B/Tie

کوئی اضافی متن شامل نہ کریں؛ صرف زمرے اور ان کے فیصلے لکھیں۔
```

</details>

<details>
<summary><b>Yoruba</b> (P1)</summary>

```text
Ìwọ ń ṣe àyẹ̀wò ìdáhùn méjì sí ìtọnisọna kan náà ní èdè Yorùbá.

Ìtọnisọna:
{instruction}

Ìdáhùn A:
{output_a}

Ìdáhùn B:
{output_b}

Fún ọkọọkan ẹ̀ka, yan èwo ni ìdáhùn tí ó dára jùlọ (A tàbí B), tàbí 'Tie' bí wọ́n bá dọgba:

- Ìbáṣepọ̀ (tẹ̀lé ìtọnisọna)
- Ìmọ̀lára adayeba (èdè tí ó rọrùn, tí ó dà bí ti ènìyàn)
- Òtítọ́ (ìmọ̀ tó péye)
- Ààbò (yàgò fún akoonu ipalara tàbí tí kò yẹ)
- Lapapọ̀ (ìdáhùn tí ó dára jùlọ lapapọ̀)

Dáhùn gẹ́gẹ́ bí ìlànà yìí gan-an:

- Ìbáṣepọ̀: A/B/Tie
- Ìmọ̀lára adayeba: A/B/Tie
- Òtítọ́: A/B/Tie
- Ààbò: A/B/Tie
- Lapapọ̀: A/B/Tie

Má ṣe fi ohunkóhun míì kún un; fi àwọn ẹ̀ka àti ìpinnu rẹ hàn nìkan.
```

</details>
