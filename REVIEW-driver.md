# Review: the driver who wants cheaper fuel today

Reviewed 2026-11-12 on the live site (https://nickeniklas.github.io/fuel-dash/)
at phone size (375×812), default settings: fuel 95, area 15 km. Newest data on
the page was 2026-11-11. I looked only at what a driver would see and tap; no
code was read.

## 1. Verdict

**3 / 10 that I come back tomorrow.** The page answers "where is fuel cheapest?"
with five prices from July and August, so the first thing I act on is wrong.

## 2. The moment I lost trust

Second 5. I open the page, the list is sorted cheapest first, and I read the top
row: **ABC Vuosaari, 1.962 €**. Then the date next to it: **2026-08-22**. That
is almost three months old.

The next four rows are the same story:

| Row | Station | Price | Reported |
|---|---|---|---|
| 1 | ABC, Vuosaari | 1.962 € | 2026-08-22 |
| 2 | Shell, Leppävaara | 1.972 € | 2026-07-25 |
| 3 | ABC Deli, Etu-Töölö | 1.986 € | 2026-07-25 |
| 4 | ShellExpress, Itäväylä | 1.997 € | 2026-08-09 |
| 5 | St1, Herttoniemi | 1.999 € | 2026-08-04 |
| 6 | St1, Konala | 2.073 € | 2026-11-09 |

The real answer is row 6, and it is 11 cents above the price the page led with.
Old prices are cheaper than today's, so sorting by price puts the dead ones at
the top every time.

The old rows are greyed out with a small dot, and that is the page trying to
warn me. On a phone it does not land:

- Grey reads as "less important", not "do not trust this".
- The dot's explanation ("Not seen on the source in over 5 days") only appears
  on mouse hover. There is no hover on a phone.
- About half of the 102 rows are greyed, so the list is mostly warnings.

If I had only glanced at station and price, I would have driven to Vuosaari.

Things that added to it in the same 30 seconds:

- **Nothing tells me what this is.** There is no title on the page. The first
  thing I see is two rows of buttons.
- **"15 km" of what?** It never says where the centre is. I do not know whether
  my home is inside it.
- **The first sentence is not for me:** "137 stations · 2185 reports · 118 days
  of area medians across 130 days (12 days missing)". I do not know what an
  area median is, and "12 days missing" in the first line makes me trust the
  page less before I have read a price.
- **Dates are written `2026-11-09`.** I have to work out how old that is.
- **A column is cut off.** "VS 7D AVG" sits off the right edge of the screen,
  with nothing showing that the table scrolls sideways. I would not know the
  term anyway, and most rows show only "—".
- **Station names carry leftovers** I cannot read: "(E85 1.369) (*E99+)",
  "(*Vpower)", "(Re85 1.649)".
- **The map is about seven screens down**, below all 102 rows. I would never
  reach it. When I do, the dots are green, red and grey with no key.
- **Tapping a station throws me to the bottom of the page** to a line chart of
  that station's history. I wanted to know where it is or how to get there.

I stopped there. I never saw "Area median trend" or "Long-term context", and I
would not have understood the headings.

## 3. Five smallest changes, ranked

1. **Keep dead prices out of the default list.** Rows the page already marks as
   gone from the source (over 5 days) move below the live ones, or behind a
   "Show old prices" checkbox that is off by default. The top row then becomes
   the true cheapest. This alone moves the score most.

2. **Show age, not a date.** "2 days ago", "yesterday", "3 months ago" in place
   of `2026-11-09`. It is shorter, so the cut-off fourth column probably fits
   too. Rename that column to something like "vs last week".

3. **Put the answer in one sentence at the top.** Replace the stations/reports/
   medians line with: "Cheapest 95 right now: St1 Konala, 2.073 €, reported 2
   days ago." Move the coverage numbers to the bottom of the page.

4. **Bring the map within reach.** Show the 10 cheapest rows with a "Show all"
   button so the map is one swipe away, and add a one-line key under it saying
   what green, red and grey mean.

5. **Say what and where.** Add a title ("Fuel prices, Helsinki area") and label
   the area button with its centre ("15 km from Helsinki centre" or whatever
   the centre really is).

Runner-up: make a row tap show the station on the map, with the history chart
as a second step.

## 4. What works and should not be touched

- **Fuel buttons at the top, staying on screen while I scroll.** One tap, the
  list changes at once. This is the right first control.
- **Cheapest-first as the default order.** The order is right; only what is
  allowed into it is wrong.
- **Price and date side by side on every row.** The date is what saved me from
  Vuosaari. Keep it next to the price, just easier to read.
- **Greying old prices.** The instinct is right and should stay for prices a
  few days old. It just cannot be the only defence for months-old ones.
- **Three decimals on prices** (2.073 €). That is how the pump shows them.
- **The sentence above the median chart:** "Helsinki area is 1.3 snt/l below
  the national average for 95E10". Plain words, one number. More of the page
  should talk like this.
- **Favourite stars and the name search.** Once I trust the list, starring my
  two usual stations is the reason I would come back.
- **Speed.** The page loaded and was usable straight away, with no cookie
  banner, sign-up or advert.
