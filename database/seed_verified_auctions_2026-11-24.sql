-- مرصد المزادات: دفعة مزادات متحققة حتى 2026-11-24
-- آمن لإعادة التشغيل: لا يكرر أي سجل له auction_url موجود.
-- لا يحذف أو يعدّل أي مزاد سابق.
-- كل التواريخ بتوقيت السعودية (+03:00). راجع المصدر قبل المشاركة لأن المواعيد قد تتغير.

WITH seed (
  title, category, source_name, source_url, auction_url, location,
  description, start_date, end_date
) AS (
  VALUES
  (
    'مزاد بدجت (1)',
    'السيارات والمركبات',
    'وصلت للمزادات',
    'https://auction.wasalt.sa/',
    'https://auction.wasalt.sa/auction-group/1176',
    'الرياض',
    'مزاد إلكتروني يضم 17 مركبة متنوعة، منها سوزوكي بالينو وهافال جوليان وBMW 320i وشفروليه تاهو وفورد تورس. المعاينة حسب تعليمات الجهة المنظمة.',
    '2026-11-24 00:00:00+03',
    '2026-11-26 23:59:59+03'
  ),
  (
    'مزاد صفوة المركبات (1)',
    'السيارات والمركبات',
    'وصلت للمزادات',
    'https://auction.wasalt.sa/',
    'https://auction.wasalt.sa/auction-group/1180',
    'الرياض، بريدة',
    'مزاد أفراد إلكتروني يضم 6 مركبات، منها تويوتا كورولا وشفروليه تاهو وسيلفرادو ولاندكروزر وهيونداي سوناتا وسنتافي. مواعيد المعاينة لدى مسؤولي الأصول.',
    '2026-11-27 00:00:00+03',
    '2026-11-27 23:59:59+03'
  ),
  (
    'مزاد نوادر الرياض',
    'العقارات',
    'وصلت للمزادات',
    'https://auction.wasalt.sa/',
    'https://auction.wasalt.sa/auction-group/1158',
    'الرياض',
    'مزاد إلكتروني يضم عمارة سكنية تجارية بحي المرسلات ومستودعًا تجاريًا بحي المناخ.',
    '2026-12-01 00:00:00+03',
    '2026-12-02 23:59:59+03'
  ),
  (
    'مزاد كنوز الرياض',
    'العقارات',
    'وصلت للمزادات',
    'https://auction.wasalt.sa/',
    'https://auction.wasalt.sa/auction-group/1175',
    'الرياض',
    'مزاد إلكتروني يضم مستودعين تجاريين بحي المشاعل، وفيلا سكنية بحي الملز، واستراحة بحي الرمال.',
    '2026-12-10 00:00:00+03',
    '2026-12-12 23:59:59+03'
  ),
  (
    'مزاد تويوتا هايس',
    'السيارات والمركبات',
    'سومتك',
    'https://www.soum.tech/',
    'https://www.soum.tech/auctions/1248/assets',
    'الرياض',
    'مزاد مركبات على سيارة تويوتا هايس فان بضائع موديل 2014. تاريخ فتح المزاد 26 نوفمبر 2026 الساعة 10 صباحًا، بحسب صفحة المزاد.',
    '2026-11-26 10:00:00+03',
    '2026-11-29 23:59:59+03'
  ),
  (
    'مزاد جواهر الرياض',
    'العقارات',
    'سومتك',
    'https://www.soum.tech/',
    'https://www.soum.tech/auctions/1244/assets',
    'الرياض',
    'مزاد عقاري هجين يضم مبنى سكنيًا تجاريًا في الصحافة ومجمع فلل سكنية في الرائد. موعد البدء 29 نوفمبر 2026 الساعة 4 مساءً.',
    '2026-11-29 16:00:00+03',
    '2026-11-29 23:59:59+03'
  ),
  (
    'مزاد العنوان – فرص عقارية بالرياض',
    'العقارات',
    'سومتك',
    'https://www.soum.tech/',
    'https://www.soum.tech/auctions/1246/assets',
    'الرياض',
    'مزاد عقاري هجين يضم 6 أصول تجارية في أحياء الياسمين والصحافة والربوة. موعد البدء 30 نوفمبر 2026 الساعة 4 مساءً.',
    '2026-11-30 16:00:00+03',
    '2026-11-30 23:59:59+03'
  ),
  (
    'مزاد سكراب شاحنات المراعي',
    'السيارات والمركبات',
    'سومتك',
    'https://www.soum.tech/',
    'https://www.soum.tech/auctions/1241/assets',
    'الرياض، الخرج',
    'مزاد يضم 18 أصلًا من الشاحنات والمركبات، منها شاحنات مان وشاحنات إيسوزو ودينات ورؤوس ومركبات توزيع بضائع. يبدأ 3 ديسمبر 2026 الساعة 10 صباحًا.',
    '2026-12-03 10:00:00+03',
    '2026-12-10 23:59:59+03'
  )
)
INSERT INTO public.auctions (
  title, category, source_name, source_url, auction_url, location,
  description, start_date, end_date, status
)
SELECT
  seed.title, seed.category, seed.source_name, seed.source_url, seed.auction_url,
  seed.location, seed.description, seed.start_date::timestamptz,
  seed.end_date::timestamptz, 'published'
FROM seed
WHERE NOT EXISTS (
  SELECT 1
  FROM public.auctions existing
  WHERE existing.auction_url = seed.auction_url
);

-- نتيجة التحقق: يعرض عدد المزادات المنشورة في هذه الدفعة مع روابطها.
SELECT id, title, source_name, start_date, end_date, auction_url, status
FROM public.auctions
WHERE auction_url IN (
  'https://auction.wasalt.sa/auction-group/1176',
  'https://auction.wasalt.sa/auction-group/1180',
  'https://auction.wasalt.sa/auction-group/1158',
  'https://auction.wasalt.sa/auction-group/1175',
  'https://www.soum.tech/auctions/1248/assets',
  'https://www.soum.tech/auctions/1244/assets',
  'https://www.soum.tech/auctions/1246/assets',
  'https://www.soum.tech/auctions/1241/assets'
)
ORDER BY start_date ASC;
