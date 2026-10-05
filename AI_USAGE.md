# שימוש ב-AI

## 1. יצירת נתוני ההתחלה

- **כלי:** Gemini ([להשלים: גרסה]) · **תאריך:** 05/10/2026
- **קובץ:** `data/sample_data.jsonl`, אובייקט JSON אחד בכל שורה.

### הפנייה הסופית

```
Generate 18 lines of JSONL (one JSON object per line, no extra text, no code block)
with synthetic test data for a second-hand consignment sales system called YallaSell.
Use fake data only: no real people, phone numbers or emails.

Every object has these common fields:
- "id": unique integer from 201 upward
- "agreement_id": string like "A-101" (several items can share the same agreement)
- "client_name": a fake first and last name
- "client_city": an Israeli city
- "end_date": agreement end date, format "YYYY-MM-DD", between 2026-10-01 and 2026-12-31
- "category": one of "electronics", "clothing", "furniture"
- "title": short product name
- "condition": one of "new", "like_new", "good", "fair"
- "years_owned": number >= 0 (can be decimal, e.g. 1.5)
- "asking_price": positive number in shekels
- "status": one of "submitted", "listed", "sold", "expired"

Extra fields depending on "category":
- electronics: "brand" (string), "storage_gb" (positive integer)
- clothing: "size" (one of "XS", "S", "M", "L", "XL"), "material" (string)
- furniture: "width_cm" and "height_cm" (positive integers)

Requirements: at least 5 items per category, at least 6 different agreements,
items with all 4 statuses, and a few items sharing the same end_date.
```

### מבנה הרשומה

| שדה | סוג | כלל |
|---|---|---|
| `id` | מספר שלם | ייחודי |
| `agreement_id`, `client_name`, `client_city`, `end_date` | טקסט / תאריך | אותם ערכים לכל המוצרים של אותו הסכם |
| `category` | טקסט | electronics / clothing / furniture |
| `title` | טקסט | |
| `condition` | טקסט | new / like_new / good / fair |
| `years_owned` | מספר | ≥ 0 |
| `asking_price` | מספר | > 0 |
| `status` | טקסט | submitted / listed / sold / expired |
| שדות לפי סוג | | אלקטרוניקה: `brand`, `storage_gb` · ביגוד: `size`, `material` · רהיטים: `width_cm`, `height_cm` |

### אופן הבדיקה

1. כל שורה נקראה עם `json.loads` (בדיקת JSON תקין).
2. בדיקת מזהים כפולים ושדות חסרים.
3. כל רשומה הומרה לאובייקט עם `Item.from_dict`, כך שה-validation של המחלקות (מצב, מחיר, מידה, נפח אחסון ומידות) נבדק על כל הנתונים.
4. בדיקת עקביות עסקית: לכל `agreement_id` אותו לקוח ואותו תאריך סיום, ומוצר בסטטוס `expired` חייב להיות בהסכם שתאריך הסיום שלו כבר עבר.
5. ספירה: 6 מוצרים בכל קטגוריה, 4 סטטוסים, 8 הסכמים, תאריכי סיום משותפים.

### בעיות שנמצאו ותיקונים

ה-JSON, המזהים והשדות היו תקינים, וכל הערכים עברו את ה-validation. נמצאו **3 שגיאות לוגיות** שה-AI לא זיהה:

| מוצר | בעיה | תיקון |
|---|---|---|
| 206 | `expired`, אבל ההסכם A-103 מסתיים ב-30/11/2026 (בעתיד) | הסטטוס שונה ל-`listed` |
| 216 | `expired`, אבל ההסכם A-108 מסתיים ב-15/12/2026 | הסטטוס שונה ל-`listed` |
| 212 | `expired`, אבל ההסכם A-106 מסתיים ב-01/12/2026 | תאריך הסיום של A-106 שונה ל-02/10/2026 |

כדי לשמור על שני מוצרים בסטטוס `expired`, תאריך הסיום של A-105 שונה ל-03/10/2026, והמוצר 210 (שהיה `listed` בהסכם שהסתיים) שונה ל-`expired`.

### שורות לא תקינות שהוספו בכוונה

בסוף הקובץ נוספו 4 שורות שגויות כדי להדגים שהטעינה מזהה אותן, מדווחת עליהן וממשיכה בלי לקרוס:

| מזהה | שגיאה |
|---|---|
| 219 | מידה `XXL` שאינה קיימת |
| 205 | מזהה כפול |
| 220 | חסר השדה `asking_price` |
| 221 | JSON לא תקין (שורה קטועה) |

התוצאה: 18 רשומות תקינות נטענות, 4 נדחות.

## 2. שימושים נוספים ב-AI

- **Claude (Anthropic):** שימש לבחירת הנושא ולניסוח הצעת הפרויקט, לתכנון המחלקות, להסבר מושגים, לכתיבת טיוטות קוד ולבדיקת הנתונים שנוצרו ב-Gemini.
- כל קוד שהוצע הורץ ונבדק (קובץ בדיקה ידני ו-`main.py`), ואני מסוגל להסביר כל חלק בו.
