# Kasszas hasznalati utmutato

## Bejelentkezes

Nyisd meg a kassza gepen a bongeszoben a middleware cimet (pl.
`https://loyalty.pelda.hu/login`), add meg a felhasznalonevedet es jelszavadat.

## Vasarlo beolvasasa

1. Kattints a "QR beolvasas" mezobe ( altalaban mar automatikusan oda van
   fokuszalva).
2. Olvasd be a vasarlo UNAS-profiljaban megjeleno QR-kodot a QR-olvasoval.
3. Ha ervenyes a kod, megjelenik a vasarlo neve, a kartya vege es az aktualis
   pontegyenlege.
4. Ha hibauzenet jon ("Ismeretlen vagy ervenytelen QR-kod"), kerd meg a vasarlot,
   hogy probalja ujra, vagy ellenorizze, hogy a profiljaban friss-e a QR-kod.

## Pont jovairasa

1. Ird be a vasarlas vegosszeget forintban.
2. Opcionalisan add meg a nyugtaszamot (ha ures, a rendszer automatikusan general
   egyet).
3. Kattints "Pont jovairasa" - egy megerosito ablak mutatja a regi egyenleget, a
   varhato valtozast es az uj egyenleget.
4. Erositsd meg. Csak sikeres visszajelzes utan tekintsd elvegzettnek a
   muveletet.

## Pont bevaltasa

1. Ird be a bevaltando pontot.
2. Opcionalisan a nyugtaszamot.
3. Kattints "Pont bevaltasa", ellenorizd a megerosito ablakban a reszleteket,
   majd erositsd meg.
4. Ha a vasarlonak nincs eleg pontja, vagy a bevaltas a megengedett hataron
   kivul esik, a rendszer hibauzenettel elutasitja.

## Uj vasarlo beolvasasa

A "Uj vasarlo beolvasasa" gombbal torolheted a kepernyorol az aktualis vasarlo
adatait, es ujra fokuszalodik a beolvaso mezo a kovetkezo vasarlohoz.

## Legutobbi tranzakciok es visszavonas

A jobb oldali panelen lathatod a legutobbi tranzakciokat. Admin jogosultsaggal
minden meg vissza nem vont, sikeres jovairas/bevaltas mellett megjelenik egy
"Visszavonas" gomb - kattintasra egy indoklast kell megadni, majd a rendszer
kompenzalo tranzakciot keszit (az eredetit nem torli, hanem "visszavont"
allapotba teszi).

## Ha valami nem mukodik

- "UNAS kapcsolat nem elerheto" felirat: a szerver nem eri el a UNAS-t, addig
  ne probalj pontot modositani - ertesitsd az uzemeltetot.
- Ha ugyanazt a QR-kodot ketszer egymas utan gyorsan beolvasod, a rendszer a
  masodikat figyelmen kivul hagyja (nincs duplikalt feldolgozas).
- Ugyanazon nyugtaszammal/muvelettel ismetelt probalkozas nem irja jovairja
  ketszer a pontot.
