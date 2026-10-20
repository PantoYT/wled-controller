# What rev 1.0 cost

Gross PLN. Allegro and JLC figures are what Panto paid (2026-10-19). TME figures are TME's
catalogue prices on 2026-10-19 for the order quantities in `quickbuy-v1.txt`, not the
invoice. Shipping that is not listed was not known when this was written.

## Everything bought

| Where | Item | Qty | PLN |
|---|---|---|---|
| JLCPCB | rev 1.0 PCB, shipping included | 5 boards | 30.00 |
| Allegro | ESP32-WROOM-32 USB-C CH340 | 1 | 25.00 |
| Allegro | WS2812B 5 V, 30 LEDs/m, IP30, black PCB | 4 m | ~40.00 |
| Allegro | JST SM 3-pin pair | 1 | 3.50 |
| TME | CD74HCT125E | 2 | 9.36 |
| TME | DIP-14 socket 1-2199298-3 | 1 | 1.27 |
| TME | Female header 1x40 ZL262-40SG | 2 | 4.46 |
| TME | 100 nF CC-104/100 | 100 | 17.05 |
| TME | 100 R CF1/4W-100R | 100 | 4.01 |
| TME | Mini blade fuse holder KEYS3568 | 1 | 4.77 |
| TME | Mini blade fuse 3 A 0297003.WXNV | 2 | 3.43 |
| TME | DC jack PC-GK2.1 | 3 | 5.24 |
| TME | Screw terminal 5.08 mm 3-pole | 2 | 3.95 |
| TME | Screw terminal 5.08 mm 2-pole | 5 | 6.59 |
| TME | Male header 1x40 ZL201-40G | 10 | 14.23 |
| | **TME subtotal** | | **74.36** |
| TME | Shipping | | 13.90 |
| Allegro | Shipping (free over 50 PLN) | | 0.00 |
| emaudio | 1000 uF 16 V electrolytic (TME equivalent `EEUFR1C102L`) | 6 | 3.50 |
| | **Total** | | **190.26** |


## What board #1 alone is worth

Parts that ended up on the desk board, at unit price: PCB 6.00 (1/5 of the order), ESP32
25.00, the rest of the electronics 24.75, so **55.75** for the controller. With 72 LEDs
(2.4 m at ~10 PLN/m) and the JST pair: **83.25**. Left over: 4 bare PCBs, 48 LEDs, one
74HCT125, 96 resistors, 99 capacitors, terminals, headers, two DC jacks.

## Rev 2.0 `phi` (6 channels)

Gerbers: `../rev2/old-variants/wled-controller-v2-phi-gerbers.zip` (DRC 0 violations, 0 unconnected,
2026-10-19). New TME parts on top of rev 1.0 leftovers, `old/quickbuy-v2-phi.txt`:
**32.04 PLN** (74HCT245, DIP-20 socket, fuse holder, 2 x 7.5 A fuses, 6 polyfuses,
6 x 3.5 mm terminals, 6 x JST XH sockets). Plus the PCB and shipping, and one
JST SM-to-XH lead per strip. The XY302R terminal is still not checked against the Phoenix
footprint.
