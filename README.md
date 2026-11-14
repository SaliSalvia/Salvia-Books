```text
             .,.................;,
           ,,.                .:.
          ,.   ,,..........,:,,
        .,    .:.                      .,.:,
        ,.          . ....,,          ,, ,,
         ,,...........    .: :,,,.., .. ,. .:,,,,.:....,...:
                   .:,   ,:..:,,:  ,,. ,  .,,,,:. ,:. ,,,,,
     ................   ,,,..,,, .,,. :.....,,:  ,,  :.
   ,,.                .,.,. ,,,..::,...:;, .,,..,:..:
 .,.  ...,...,,,,,,,,,,. :,,,,,,..,.,.,..,,........,
.;::;:::.  .,,,,,,,,,...,....,;.
         .,.                .:.
        ,,   .,..........,::,       ....          ..
       ,.    ,,........,  .        .,.:.        .:.:.
       ,,      .       .;. ,,,.,, .: ,,,,, .,.:.,:;..,,,.,,
        ,,........:.   .:.::,:: ,;, :.,, ;,,.,;, ,, ::::: :,
     .............,   ,:,,,,:, .;, :. ,. :,.,:, ,,,,,,:, .,
   ,,.            ::,. :::  ;:  ,;.,,  ,,,, ,;,. :,: .:
 ,,.   ............,, .,.,.,,.,,.,.,,  :.,. :.,,,,...,,.,,
;+::;;:,..........
```

<p align="center"><b>Design & Concept by <a href="#"><b>@SaliSalvia</b></a></b></p>

<p align="center">
<a href="#فارسی">فارسی</a> · <a href="#english">English</a>
</p>

<p align="center">
  <a href="https://github.com/SaliSalvia/Salvia-Books/actions/workflows/build-book.yml">
    <img src="https://img.shields.io/badge/Run_workflow-Build_Book-1f6feb?style=for-the-badge&logo=github&logoColor=white" alt="Run workflow — Build Book" height="36">
  </a>
</p>

---

# فارسی

## این پروژه چه کار می‌کند؟

این ریپو یک **کارگاهِ خودکارِ کتاب‌سازی** است. شما چهار چیز می‌دهید و بقیه‌اش را
خودش انجام می‌دهد:

1. **نام کتاب** — به فارسی یا انگلیسی؛ PDF به همان زبانی ساخته می‌شود که تایپ کرده‌اید
2. **کلید Google AI Studio** — برای خواندن، تحلیل، خلاصه‌سازی و ترجمهٔ متن
3. **کلید Cloudflare** — برای تصویرسازیِ رایگان (اختیاری ولی پیشنهادی)
4. **درصد خلاصه‌سازی** — ۰ یعنی متنِ کامل، ۳۰ یعنی کتاب به یک‌سوم فشرده شود

نتیجه: یک **فایل PDF تصویری و حرفه‌ای** از همان کتاب؛ با جلد، فهرست، متنِ خوانا و
تصویرهای سینمایی که برای هر بخش از کتاب ساخته می‌شوند.

## طرز کارش را ساده بگوییم

این ابزار مثل یک استودیوی کوچکِ کتاب‌سازی است که پنج کارمند دارد و هر کدام کار
خودش را بلد است:

| مرحله | کارمندِ خیالی | کاری که واقعاً می‌شود |
|---|---|---|
| ۱ | کتاب‌دار | متنِ کامل کتاب را از منابع آزاد پیدا می‌کند (پروژهٔ گوتنبرگ، آرشیو اینترنت، وب) یا از فایلِ خودتان می‌خواند. اگر متن فارسی نبود، ترجمهٔ تازه می‌سازد. |
| ۲ | خوانندهٔ دقیق | متن را به بخش‌های «دو صفحه‌ای» تقسیم می‌کند و مضمونِ هر بخش را می‌فهمد: چه کسی، کجا، چه ساعتی، با چه حسی. |
| ۳ | تصویرگر | برای هر بخش، صحنه‌ای را که **در همان چند صفحه توصیف شده** به تصویر تبدیل می‌کند — با سبکِ سینمایی و کیفیتِ بالا. |
| ۴ | صفحه‌آرای | متن و تصویرها را در قالبِ چاپی می‌چیند: حاشیهٔ صحافی، سرصفحه، شمارهٔ صفحه، فهرست و متادیتای PDF. |
| ۵ | ناظر | اگر سرویس هوش مصنوعی موقتاً خطا بدهد، صبر می‌کند و دوباره تلاش می‌کند تا کتاب کامل شود. |

نکتهٔ مهم: تصویرها «تصویرسازیِ آزاد» نیستند؛ مدل اول متنِ همان بخش را می‌خواند و
یک لحظهٔ مشخص از آن را با جزئیات (شخصیت‌ها، مکان، نور، زمانِ روز، اشیا) توصیف
می‌کند و بعد آن توصیف را نقاشی می‌کند. برای همین هر تصویر به همان چند صفحه
می‌خورد.

## خروجی چه شکلی است؟

- **صفحهٔ ۱ — جلد:** نامِ کتاب با تایپوگرافیِ بزرگ، یک معرفیِ یک‌دو جمله‌ای، لوگو و
  «Design by: @SaliSalvia»
- **فهرست:** بخش‌ها با شمارهٔ صفحه و شمارهٔ تصویر
- **بدنه:** **دو صفحه متن، یک صفحه تصویر** — همین ریتم تا آخر؛ تصویر تمام‌عرض با
  یک کپشنِ ادبی از همان بخش
- **پشت‌جلد:** توضیح نسخه، لوگو و نشانی سازنده
- فونت‌ها: **وزیرمتن** برای فارسی و **EB Garamond** برای لاتین (همان فونت‌های
  نسخهٔ نمونه)، همه داخلِ ریپو تا ساخت به اینترنت وابسته نباشد

## در سه دقیقه شروع کنید (بدونِ دانش فنی)

**قدم ۱ — کلید API بگیرید.**
یکی از دو مسیر زیر را انتخاب کنید (توضیحِ کامل و لینک‌ها در بخش بعد):

- **مسیر رایگان (پیشنهادی):** یک حساب Cloudflare بسازید و برای Workers AI کلید
  بگیرید.
- **مسیر باکیفیت‌تر (پرداختی):** از Google AI Studio کلید Gemini بگیرید؛ مدل‌های
  تصویریِ Gemini در پلن رایگان در دسترس نیستند.

**قدم ۲ — کلید را در گیت‌هاب ذخیره کنید.**
در صفحهٔ همین ریپو: `Settings` → `Secrets and variables` → `Actions` →
`New repository secret`

| نام Secret | مقدار |
|---|---|
| `GEMINI_API_KEY` | کلید Gemini (اگر مسیر Gemini را انتخاب کردید) |
| `CLOUDFLARE_ACCOUNT_ID` | شناسهٔ حساب Cloudflare |
| `CLOUDFLARE_API_TOKEN` | توکن Workers AI |

**قدم ۳ — کتاب را بسازید.**
روی دکمهٔ **Run workflow** بالای همین صفحه بزنید (یا از تب `Actions` → ورک‌فلوی
[📖 Build Book](https://github.com/SaliSalvia/Salvia-Books/actions/workflows/build-book.yml))
→ `Run workflow` و این چهار فیلد را پر کنید:

| فیلد | مثال | توضیح |
|---|---|---|
| نام کتاب | `شازده کوچولو` | زبانِ PDF همین است |
| کلید Google AI | `AIza...` | متن، تحلیل، خلاصه و ترجمه |
| کلید Cloudflare | `cfut_...` | فقط برای تصویرِ رایگان |
| درصد خلاصه‌سازی | `0` یا `30` | ۰ = کامل، ۱ تا ۹۵ = فشرده‌سازی |

**قدم ۴ — دانلود.**
وقتی اجرا سبز شد، پایینِ همان صفحه در بخش **Artifacts** فایل
`book-<شماره>` را دانلود کنید؛ داخلش PDF نهایی است.

> این کار معمولاً بین ۱۰ تا ۴۰ دقیقه طول می‌کشد (به تعداد تصویرها بستگی دارد).
> عجله نکنید و صفحه را نبندید؛ خودش تا آخر می‌رود.

## زبان، خلاصه‌سازی و نسخهٔ دوزبانه

**زبان با نامِ کتاب تعیین می‌شود.** اگر نام را فارسی بنویسید، PDF فارسی و راست‌به‌چپ
ساخته می‌شود؛ اگر انگلیسی بنویسید، انگلیسی. اگر متنِ پیداشده به آن زبان نباشد
(مثلاً نام فارسی باشد و متنِ آزاد فقط انگلیسی موجود باشد)، همان هوش مصنوعی متن را
ترجمه و پولیش می‌کند و بعد کتاب ساخته می‌شود — نه اینکه زبانِ کتاب عوض شود.

**درصد خلاصه‌سازی** طولِ کتاب را کم می‌کند، نه مضمونش را: متن به همان درصدِ
درخواستی بازنویسی می‌شود، با حفظِ صحنه‌های کلیدی، شخصیت‌ها، گفت‌وگوهای مهم و
ترتیبِ رویدادها. مثلاً برای کتابی که با متنِ کامل ۳۱ صفحه می‌شود، ۳۰ درصد
حدود ۹ صفحه متن و چند تصویر می‌دهد. نتیجه در `_build/<کتاب>/summary-<درصد>.txt`
کش می‌شود تا اجرای دوباره ارزان باشد.

**نسخهٔ دوزبانه:** اگر متغیر `BILINGUAL` را در `Settings → Variables` روی `true`
بگذارید، بعد از هر دو صفحه متنِ فارسی، صفحهٔ متنِ انگلیسیِ همان بخش می‌آید و بعد
تصویر — برای زبان‌آموزها و کتاب‌های دوزبانه عالی است.

## لینک‌های مستقیمِ گرفتنِ کلید

### Google AI Studio (Gemini)

| چه چیزی | لینک |
|---|---|
| **ساخت کلید API** (مستقیم) | https://aistudio.google.com/apikey |
| AI Studio / Playground (امتحانِ مدل‌ها در مرورگر) | https://aistudio.google.com/ |
| مدل‌های تصویری Nano Banana | https://aistudio.google.com/models/nano-banana |
| قیمت و پلن رایگان (همان صفحه‌ای که باید ببینید) | https://ai.google.dev/gemini-api/docs/pricing |

**واقعیتی که باید بدانید:** متن، ترجمه و تحلیلِ مضمون با کلید رایگانِ Gemini
انجام می‌شود، اما **مدل‌های تصویریِ Gemini در پلن رایگان نیستند**؛ خودِ گوگل در
ستونِ Free Tier برای آن‌ها «Not available» نوشته است. اگر با کلید رایگان Gemini
اجرا کنید، کتاب ساخته می‌شود ولی جای تصویرها صفحهٔ جای‌گذار می‌آید. برای تصویرِ
واقعی، یا باید پلن پرداختیِ Gemini داشته باشید یا از مسیر رایگانِ Cloudflare
استفاده کنید.

### Cloudflare Workers AI (رایگان، مناسبِ یک کتاب در روز)

| چه چیزی | لینک |
|---|---|
| ساخت حساب و رفتن به Workers AI | https://dash.cloudflare.com/?to=/:account/ai/workers-ai |
| راهنمای رسمیِ «گرفتن توکن و Account ID» | https://developers.cloudflare.com/workers-ai/get-started/rest-api/ |
| قیمت‌گذاری (سهمیهٔ رایگان) | https://developers.cloudflare.com/workers-ai/platform/pricing |
| مدل FLUX.1 [schnell] که استفاده می‌کنیم | https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/ |

**چرا این مسیر رایگان است؟** هر حساب Cloudflare (حتی پلن رایگان، بدونِ کارت
بانکی) روزی **۱۰٬۰۰۰ neuron** سهمیه دارد؛ با مدل FLUX.1 schnell این حدود
**۵۰ تا ۲۳۰ تصویر در روز** است — یعنی به‌راحتی یک کتابِ کامل در روز. سهمیه هر
روز ساعت ۰۰:۰۰ UTC از نو پر می‌شود.

مسیر گرفتنِ کلید، خیلی خلاصه: وارد `dash.cloudflare.com` شوید → از منو
`AI` → `Workers AI` → دکمهٔ **Use REST API** → **Create a Workers AI API Token** →
توکن را کپی کنید → همان‌جا **Account ID** را هم بردارید. این دو مقدار را در
قدم ۲ به‌عنوان Secret ذخیره کنید.

### اگر خواستید کیفیت را بالاتر ببرید

کد به‌صورتِ پیش‌فرض (`IMAGE_BACKEND=auto`) اول سراغِ Gemini می‌رود و اگر تصویری
برنگشت، خودکار به Cloudflare سقوط می‌کند. با کلیدِ پرداختیِ Gemini، تصویرها
جزئیات و وفاداریِ بیشتری به متن دارند؛ برای بهترین نتیجه از مدل
`gemini-nano-banana-2.1` یا `gemini-3-pro-image` استفاده کنید.

## تصویرها: سینمایی و وفادار به متن

- **سبک:** همهٔ تصویرها با یک «امضای سبک» ثابت ساخته می‌شوند — فریمی از تریلرِ
  یک فیلمِ ادبی، لنزِ عریض ۱۶:۹، نورِ حجمی و دراماتیک، رنگ‌بندیِ سینمایی،
  دانهٔ ظریفِ فیلمِ ۳۵ میلی‌متری.
- **وفاداری:** مدل موظف است فقط از همان بخشِ کتاب استفاده کند؛ شخصیت و مکان و
  شیئی که در آن بخش نیست اضافه نمی‌کند. باید یک لحظهٔ مشخص را انتخاب کند و
  تعدادِ آدم‌ها، لباس، حالتِ چهره، زمانِ روز و هوا را صریح بنویسد.
- **بدونِ نوشتار:** مدل‌های تصویری متنِ خوانا نمی‌نویسند، پس در پرامپت صریح
  خواسته شده تصویر بدونِ حرف و تابلوا و واترمارک باشد؛ نامِ کتاب و نامِ شما با
  تایپوگرافیِ خودِ PDF گذاشته می‌شود (همان کاری که در نسخهٔ نمونه شده).
- **بدونِ بریدگیِ بی‌دلیل:** اگر تصویری ساخته نشود، صفحهٔ جای‌گذار با همان کپشن
  می‌آید و در پاس‌های بعدی دوباره تلاش می‌شود؛ طراحی و شماره‌گذاری کتاب به‌هم
  نمی‌ریزد.

## تنظیم‌های دلخواه (اختیاری)

| متغیر | پیش‌فرض | کار |
|---|---|---|
| `GEMINI_PAGES_PER_IMAGE` | `2` | چند صفحه متن بین دو تصویر |
| `GEMINI_IMAGE_DELAY_SECONDS` | `12` | فاصلهٔ ایمن بین دو درخواست تصویر |
| `GEMINI_IMAGE_RETRY_PASSES` | `2` | چند پاس برای تصویرهای ساخته‌نشده |
| `GEMINI_IMAGE_RETRY_COOLDOWN_SECONDS` | `90` | مکث بین پاس‌های تکرار |
| `IMAGE_BACKEND` | `auto` | `auto` / `gemini` / `cloudflare` |
| `CLOUDFLARE_IMAGE_STEPS` | `4` | ۱ تا ۸؛ بیشتر = کیفیت بالاتر و کندتر |
| `GEMINI_TEXT_MODEL` | خودکار | مدلِ متن/تحلیل |
| `GEMINI_IMAGE_MODEL` | خودکار | مدلِ تصویرِ Gemini |
| `SUMMARY_PERCENT` | `0` | درصدِ خلاصه‌سازی (همان فیلد ورک‌فلو) |
| `BILINGUAL` | `false` | نسخهٔ دوزبانه (متن اصلی + ترجمه) |

همین‌ها را می‌توانید در `Settings → Secrets and variables → Actions → Variables`
هم بگذارید؛ ورک‌فلو خودش می‌خواند.

## متنِ دلخواهِ خودتان

اگر کتاب کپی‌رایت دارد یا ترجمهٔ خاصی را می‌خواهید، فایل متن را اینجا بگذارید و
دوباره اجرا کنید؛ همه‌چیز از همان متن ادامه پیدا می‌کند:

```
manuscripts/<نام-انگلیسی-کتاب>-fa.txt   →  نسخهٔ فارسی
manuscripts/<نام-انگلیسی-کتاب>-en.txt   →  نسخهٔ انگلیسی
```

## پرسش‌های پرتکرار

**آیا هر کتابی را می‌توانم بسازم؟**
متنِ کتاب‌های قدیمی و آزاد (مثل آثار کلاسیک) خودکار پیدا می‌شود. کتاب‌های تازه و
کپی‌رایت‌دار در منابعِ آزاد نیستند؛ برای آن‌ها فایلِ متن را خودتان در
`manuscripts/` بگذارید و مسئولیتِ حقوقی‌اش را هم در نظر بگیرید.

**چرا بعضی تصویرها ساخته نمی‌شوند؟**
معمولاً سهمیهٔ روزانه یا محدودیتِ نرخ. کد فاصله می‌گذارد و دوباره تلاش می‌کند؛
اگر باز هم نشد، اجرای بعدی از همان کش ادامه می‌دهد و فقط تصویرهای ناقص را
می‌سازد.

**هزینه‌اش چقدر است؟**
مسیر Cloudflare در سهمیهٔ روزانه‌اش صفر است. مسیر Gemini برای متن رایگان است و
برای تصویر پرداختی (حدود چند سنت برای هر تصویر، بسته به مدل و اندازه).

**زبانِ کتاب چطور انتخاب می‌شود؟**
خودکار، از روی متنی که پیدا می‌شود. نامِ فارسی → کتابِ فارسی، نامِ انگلیسی →
کتابِ انگلیسی. با `--lang fa` یا `--lang en` می‌توانید اجبار کنید.

## اجرای محلی (برای برنامه‌نویس‌ها)

```bash
pip install -r scripts/requirements.txt
playwright install chromium

export GEMINI_API_KEY="..."
# یا برای مسیر رایگان:
export CLOUDFLARE_ACCOUNT_ID="..."
export CLOUDFLARE_API_TOKEN="..."

python scripts/generate_book.py --title "شازده کوچولو"
```

`--lang` اختیاری است (`auto` پیش‌فرض). خروجی در `output/<slug>-<lang>.pdf` و
گزارشِ ساخت در `_build/<slug>/layout.json` ذخیره می‌شود.

تست‌ها (بدونِ کلید و بدونِ شبکه):

```bash
pip install -r scripts/requirements.txt -r scripts/requirements-dev.txt
pytest              # واحد + سرتاسری تا PDF واقعی
pytest -m live      # تست‌های شبکه (گوتنبرگ/آرشیو/جست‌وجوی وب)
```

## ساختار ریپو

```
.
├── assets/logo.png            ← لوگوی شما
├── assets/fonts/              ← Vazirmatn + EB Garamond (محلی)
├── manuscripts/               ← متن دلخواه شما (اختیاری)
├── scripts/
│   ├── generate_book.py       ← نقطهٔ ورود
│   ├── text_source.py         ← پیدا کردن/ترجمهٔ متن
│   ├── illustrate.py          ← تحلیل بخش + پرامپت + تصویر
│   ├── free_image.py          ← بک‌اندِ رایگانِ Cloudflare Workers AI
│   ├── llm.py                 ← فراخوانی امنِ Gemini (retry، مدل‌های جایگزین)
│   └── render.py              ← صفحه‌آرایی و PDF
├── tests/
└── .github/workflows/build-book.yml
```

## اعتبار

طراحی و ساخت: **SaliSalvia** · [metairani.com](https://metairani.com)
فونت‌ها: Vazirmatn و EB Garamond (هر دو با مجوز SIL OFL).
متن‌های آزاد: [Project Gutenberg](https://www.gutenberg.org) و
[Internet Archive](https://archive.org).

---

# English

## What this project does

This repo is an **automatic book studio**. You provide four things and it does the
rest:

1. **A book title** — in Persian or English; the PDF is built in the language you typed
2. **A Google AI Studio key** — for reading, analyzing, summarizing and translating text
3. **A Cloudflare key** — for free image generation (optional but recommended)
4. **A summary percentage** — 0 means full text, 30 means one-third the length

The result: a polished **illustrated PDF** of that book — cover, table of contents,
readable typography, and cinematic images generated for each passage.

## How it works, in plain words

Think of it as a small book studio with five imaginary staff members:

| Step | The staffer | What actually happens |
|---|---|---|
| 1 | Librarian | Finds the full text in free sources (Project Gutenberg, Internet Archive, the web) or reads your own file. Translates it if the found language differs from the requested one. |
| 2 | Close reader | Splits the text into **two-page sections** and understands each one: who, where, at what hour, in what mood. |
| 3 | Illustrator | Turns the scene **described in that exact section** into an image — cinematic style, high detail. |
| 4 | Typesetter | Lays text and images into a print-ready book: binding margins, running heads, page numbers, contents, PDF metadata. |
| 5 | Supervisor | On temporary API errors, it waits and retries until the book is complete. |

Crucially, the images are not free-form decoration: the model first reads the
passage, picks one concrete moment from it, and describes that moment in detail
(characters, place, light, time of day, objects). Only then is it painted — which
is why each image belongs to its own two pages.

## What the output looks like

- **Page 1 — cover:** large title, a one–two sentence blurb, logo, and
  “Design by: @SaliSalvia”
- **Contents:** sections with their text page and plate number
- **Body:** **two pages of text, then one full-page image**, repeated to the end —
  each image with a short literary caption from its own section
- **Back cover:** edition note, logo, author link
- Typefaces: **Vazirmatn** for Persian and **EB Garamond** for Latin — the sample
  edition’s fonts, vendored in the repo so the build never depends on the network

## Start in three minutes (no technical knowledge needed)

**Step 1 — Get an API key.** Pick one of the two paths (details and links below):

- **Free path (recommended):** create a Cloudflare account and get a Workers AI token.
- **Higher-quality path (paid):** get a Gemini key from Google AI Studio; Gemini’s
  image models are not available on the free tier.

**Step 2 — Store the key on GitHub.**
Go to `Settings` → `Secrets and variables` → `Actions` → `New repository secret`:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | your Gemini key (if you use Gemini) |
| `CLOUDFLARE_ACCOUNT_ID` | your Cloudflare account ID |
| `CLOUDFLARE_API_TOKEN` | your Workers AI token |

**Step 3 — Build the book.**
Click the **Run workflow** button at the top of this page (or open the `Actions` tab →
workflow [📖 Build Book](https://github.com/SaliSalvia/Salvia-Books/actions/workflows/build-book.yml))
→ `Run workflow` and fill in the four fields:

| Field | Example | What it does |
|---|---|---|
| Book title | `The Little Prince` | Sets the PDF language |
| Google AI key | `AIza...` | Text, analysis, summary, translation |
| Cloudflare key | `cfut_...` | Free image generation only |
| Summary percent | `0` or `30` | 0 = full text, 1–95 = condensation |

**Step 4 — Download.**
When the run turns green, download `book-<number>` from the **Artifacts** section at
the bottom of the run page. The PDF is inside.

> A run usually takes 10–40 minutes depending on the number of illustrations. Keep
> the page open; the workflow finishes on its own.

## Language, summarization and bilingual editions

**The title decides the language.** Type the title in Persian and you get a Persian,
right-to-left PDF; type it in English and you get English. If the text that can be
found is in a different language (say, a Persian title but only the English original
is available), the same AI translates and polishes it first — the language you asked
for never silently changes.

**The summary percentage** shortens the book without losing its substance: the text
is rewritten at that ratio while keeping key scenes, characters, important dialogue
and the order of events. A book that would be 31 pages at full length becomes about
9 pages of text at 30%, with fewer plates. The result is cached in
`_build/<book>/summary-<percent>.txt` so re-runs are cheap.

**Bilingual editions:** set the `BILINGUAL` variable to `true` under
`Settings → Variables` and each Persian spread is followed by the English text of
the same section before the plate — useful for language learners and dual-language
editions.

## Direct links for API keys

### Google AI Studio (Gemini)

| What | Link |
|---|---|
| **Create an API key** (direct) | https://aistudio.google.com/apikey |
| AI Studio / Playground (try models in the browser) | https://aistudio.google.com/ |
| Nano Banana image models | https://aistudio.google.com/models/nano-banana |
| Pricing and free tier (the page to check) | https://ai.google.dev/gemini-api/docs/pricing |

**The honest part:** text, translation and thematic analysis work with a free Gemini
key, but **Gemini’s image models are not on the free tier** — Google lists
“Not available” in the Free Tier column. With a free Gemini key the book is built
with placeholder pages where images should be. For real images, either use a paid
Gemini tier or the free Cloudflare path.

### Cloudflare Workers AI (free, enough for one book a day)

| What | Link |
|---|---|
| Create an account and open Workers AI | https://dash.cloudflare.com/?to=/:account/ai/workers-ai |
| Official “get your token and Account ID” guide | https://developers.cloudflare.com/workers-ai/get-started/rest-api/ |
| Pricing (free allocation) | https://developers.cloudflare.com/workers-ai/platform/pricing |
| The FLUX.1 [schnell] model we use | https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/ |

**Why it is free:** every Cloudflare account — even the free plan, no card required —
gets **10,000 neurons per day**, which is roughly **50 to 230 FLUX.1 schnell
images**. That comfortably covers one full book per day. The quota resets at
00:00 UTC.

In short: open `dash.cloudflare.com` → `AI` → `Workers AI` → **Use REST API** →
**Create a Workers AI API Token** → copy the token → copy the **Account ID** shown
on the same page. Save both as the secrets from Step 2.

### Raising the quality ceiling

By default (`IMAGE_BACKEND=auto`) the pipeline tries Gemini first and falls back to
Cloudflare if no image comes back. With a paid Gemini key the plates follow the text
even more faithfully; `gemini-nano-banana-2.1` or `gemini-3-pro-image` give the best
results.

## Images: cinematic and faithful to the passage

- **Style:** every plate shares one fixed style signature — a still from a literary
  film trailer, 16:9 widescreen, dramatic volumetric light, cinematic color grading,
  fine 35 mm grain.
- **Fidelity:** the model must use only that section of the book. It may not add
  characters, places or objects that are not in the passage. It must pick one
  concrete moment and state the number of people, clothing, expressions, time of day
  and weather explicitly.
- **No lettering:** image models do not render reliable text, so prompts explicitly
  forbid letters, signage and watermarks. The title and your name are typeset by the
  PDF itself — exactly what the sample edition does.
- **No silent gaps:** if an image fails, the page keeps its caption as a placeholder
  and the image is retried in later passes, so pagination and numbering stay intact.

## Optional settings

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_PAGES_PER_IMAGE` | `2` | Text pages between two images |
| `GEMINI_IMAGE_DELAY_SECONDS` | `12` | Minimum gap between image requests |
| `GEMINI_IMAGE_RETRY_PASSES` | `2` | Extra passes for failed images |
| `GEMINI_IMAGE_RETRY_COOLDOWN_SECONDS` | `90` | Wait between retry passes |
| `IMAGE_BACKEND` | `auto` | `auto` / `gemini` / `cloudflare` |
| `CLOUDFLARE_IMAGE_STEPS` | `4` | 1–8; higher = better and slower |
| `GEMINI_TEXT_MODEL` | automatic | text/analysis model |
| `GEMINI_IMAGE_MODEL` | automatic | Gemini image model |
| `SUMMARY_PERCENT` | `0` | summary ratio (same as the workflow field) |
| `BILINGUAL` | `false` | dual-language edition (original + translation) |

You can also set these under `Settings → Secrets and variables → Actions → Variables`;
the workflow reads them automatically.

## Your own manuscript

If the book is copyrighted, or you want a specific translation, drop the text in and
run again — everything continues from that file:

```
manuscripts/<english-book-name>-fa.txt   →  Persian edition
manuscripts/<english-book-name>-en.txt   →  English edition
```

## FAQ

**Can I build any book?**
Public-domain classics are found automatically. Recent, copyrighted books are not in
free sources; supply the text in `manuscripts/` and consider the legal side yourself.

**Why are some images missing?**
Usually a daily quota or a rate limit. The pipeline paces itself and retries; the next
run resumes from the cache and only fills in what is missing.

**What does it cost?**
The Cloudflare path is free within its daily allocation. The Gemini path is free for
text and paid for images (a few cents per image depending on model and size).

**How is the book’s language chosen?**
Automatically, from the text that is found: Persian title → Persian book, English
title → English book. Force it with `--lang fa` or `--lang en`.

## Local run (developers)

```bash
pip install -r scripts/requirements.txt
playwright install chromium

export GEMINI_API_KEY="..."
# or the free path:
export CLOUDFLARE_ACCOUNT_ID="..."
export CLOUDFLARE_API_TOKEN="..."

python scripts/generate_book.py --title "The Little Prince"
```

`--lang` is optional (`auto` by default). The PDF lands in
`output/<slug>-<lang>.pdf` and the build report in `_build/<slug>/layout.json`.

Tests (no API key, no network):

```bash
pip install -r scripts/requirements.txt -r scripts/requirements-dev.txt
pytest              # unit + end-to-end up to a real PDF
pytest -m live      # network tests: Gutenberg / archive.org / web search
```

## Repository layout

```
.
├── assets/logo.png            ← your logo
├── assets/fonts/              ← Vazirmatn + EB Garamond (local)
├── manuscripts/               ← your own manuscript (optional)
├── scripts/
│   ├── generate_book.py       ← entry point
│   ├── text_source.py         ← find / translate the text
│   ├── illustrate.py          ← section analysis, prompts, images
│   ├── free_image.py          ← free Cloudflare Workers AI backend
│   ├── llm.py                 ← safe Gemini calls (retry, fallback models)
│   └── render.py              ← layout and PDF
├── tests/
└── .github/workflows/build-book.yml
```

## Credits

Design & build: **SaliSalvia** · [metairani.com](https://metairani.com)
Fonts: Vazirmatn and EB Garamond (both SIL OFL).
Free texts: [Project Gutenberg](https://www.gutenberg.org) and
[Internet Archive](https://archive.org).

---

<p align="center">Design by: <b>@SaliSalvia</b></p>
